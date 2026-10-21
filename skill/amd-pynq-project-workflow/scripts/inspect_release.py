"""Read-only inspection of the current project release and its source delta.

The full candidate build and later software/MCU patch are intentionally separated:
the candidate proves the original build identity, while the release record proves
which host/firmware files changed afterwards and that the FPGA artifacts did not.

No project modules are imported, no hardware is opened, and no files are written.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from inspect_candidate import digest_file, digest_stream, inspect, read_json, within


HASHED_ARTIFACTS = {'bit', 'hwh', 'stm32_hex', 'stm32_bin', 'stm32_elf'}


def source_path(root, name):
    if name.startswith('workspace/'):
        return within(root, name[len('workspace/'):])
    if name.startswith(('pynq_fpga/', 'stm32_')):
        return within(root, name)
    return within(root, str(Path('pynq_fpga') / name))


def canonical_source_name(name):
    if name.startswith('workspace/'):
        return name
    if name.startswith('pynq_fpga/'):
        return name[len('pynq_fpga/'):]
    return name


def expected_source_identity(manifest, failures):
    identity = manifest.get('source_identity')
    if not isinstance(identity, dict) or identity.get('schema') != 'car-build-source/v1':
        raise ValueError('release manifest source identity schema required')
    base = identity.get('sources')
    patches = identity.get('software_patch_sources', {})
    if not isinstance(base, dict) or not base:
        raise ValueError('release manifest source map required')
    if not isinstance(patches, dict):
        raise ValueError('software patch source map must be an object')
    for label, values in (('base', base), ('patch', patches)):
        for name, digest in values.items():
            if not isinstance(name, str) or not isinstance(digest, str):
                raise ValueError(f'invalid {label} source entry')
            if len(digest) != 64 or any(ch not in '0123456789abcdefABCDEF' for ch in digest):
                raise ValueError(f'invalid {label} digest: {name}')
    return identity, base, patches


def verify_current_sources(root, manifest, failures):
    identity, base, patches = expected_source_identity(manifest, failures)
    patch_by_name = {canonical_source_name(name): (name, digest) for name, digest in patches.items()}
    if len(patch_by_name) != len(patches):
        raise ValueError('duplicate normalized software patch source')
    changed = []
    seen = set()
    for name, candidate_digest in base.items():
        path = source_path(root, name)
        if not path.is_file():
            failures.append(f'release source missing: {name}')
            continue
        actual = digest_file(path)
        seen.add(name)
        canonical = canonical_source_name(name)
        if actual == candidate_digest.lower():
            if canonical in patch_by_name and patch_by_name[canonical][1].lower() != actual:
                failures.append(f'equal source has conflicting patch digest: {name}')
            continue
        changed.append(canonical)
        if canonical not in patch_by_name:
            failures.append(f'unrecorded source drift after candidate: {name}')
        elif patch_by_name[canonical][1].lower() != actual:
            failures.append(f'patch digest differs from current source: {name}')
    for name, patch_digest in patches.items():
        path = source_path(root, name)
        if not path.is_file():
            failures.append(f'patch source missing: {name}')
            continue
        actual = digest_file(path)
        if actual != patch_digest.lower():
            failures.append(f'patch source changed: {name}')
        canonical = canonical_source_name(name)
        if canonical not in {canonical_source_name(item) for item in base}:
            changed.append(canonical)
        seen.add(name)
    return identity, sorted(set(changed)), len(seen)


def verify_package(root, package, manifest, candidate_artifacts, failures):
    if not isinstance(manifest.get('runtime_files'), dict) or not manifest['runtime_files']:
        raise ValueError('release runtime map required')
    payloads = {}
    for section in ('runtime_files', 'wireless_files'):
        values = manifest.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f'{section} must be an object')
        for name, digest in values.items():
            if name in payloads and payloads[name]['sha256'] != digest:
                raise ValueError(f'conflicting payload digest: {name}')
            payloads[name] = {'sha256': digest}
    artifacts = manifest.get('artifacts')
    if not isinstance(artifacts, dict) or set(artifacts) != HASHED_ARTIFACTS:
        raise ValueError('release requires bit/hwh and STM32 hex/bin/elf artifacts')
    for kind, record in artifacts.items():
        if not isinstance(record, dict) or not isinstance(record.get('file'), str):
            raise ValueError(f'invalid artifact record: {kind}')
        payloads[record['file']] = record
    for name, expected in payloads.items():
        path = within(root, str(package / name))
        if not path.is_relative_to(package) or not path.is_file():
            failures.append(f'release payload missing or outside package: {name}')
        elif digest_file(path) != expected['sha256'].lower():
            failures.append(f'release payload changed: {name}')
        elif 'bytes' in expected and path.stat().st_size != expected['bytes']:
            failures.append(f'release payload size changed: {name}')
    for kind in ('bit', 'hwh'):
        candidate = candidate_artifacts.get(kind, {})
        current = artifacts.get(kind, {})
        if candidate.get('sha256') != current.get('sha256'):
            failures.append(f'candidate {kind} differs from release {kind}')
    firmware = manifest.get('source_identity', {}).get('stm32_firmware', {})
    for ext in ('hex', 'bin', 'elf'):
        if artifacts['stm32_' + ext].get('sha256') != firmware.get(ext):
            failures.append('firmware source binding differs from package: ' + ext)
    return payloads


def verify_release_archive(root, release, manifest, payloads, failures):
    archive = within(root, release.get('zip_path', ''))
    if digest_file(archive) != release.get('zip_sha256', '').lower():
        failures.append('release ZIP digest differs from record')
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.namelist()
        if len(entries) != len(set(entries)):
            failures.append('release ZIP contains duplicate entries')
        if 'lab_manifest.json' not in entries:
            failures.append('release ZIP lacks lab_manifest.json')
        else:
            package = within(root, release.get('package_dir', ''))
            if bundle.read('lab_manifest.json') != (package / 'lab_manifest.json').read_bytes():
                failures.append('release ZIP manifest differs from unpacked package')
        for name, expected in payloads.items():
            if name not in entries:
                failures.append(f'release ZIP payload missing: {name}')
                continue
            with bundle.open(name) as stream:
                if digest_stream(stream) != expected['sha256'].lower():
                    failures.append(f'release ZIP payload changed: {name}')


def verify_evidence(root, release, manifest, failures):
    evidence = release.get('hardware_evidence', {})
    proof_path = within(root, evidence.get('completion_audit', ''))
    proof = read_json(proof_path)
    if proof.get('schema') != 'uart-goal-completion-audit/v1':
        raise ValueError('unexpected hardware proof schema')
    if proof.get('all_requirements_proved') is not True:
        failures.append('hardware completion audit is not fully proved')
    for item in proof.get('requirements', []):
        if item.get('proved') is not True:
            failures.append('hardware requirement not proved: ' + str(item.get('requirement')))
    for name, expected in proof.get('source_hashes', {}).items():
        path = within(root, name)
        if not path.is_file() or digest_file(path) != expected.lower():
            failures.append(f'hardware proof source changed: {name}')
    runtime_path = within(root, evidence.get('runtime_result', ''))
    runtime = read_json(runtime_path)
    if runtime.get('overall_vehicle_acceptance') != 'NOT_CLAIMED':
        failures.append('runtime evidence must not claim whole-vehicle acceptance')
    if runtime.get('motor_power') != 'disconnected':
        failures.append('runtime evidence must record motor power disconnected')
    for key in ('normal_boot_uart_PL', 'upper_half_IR_regression', 'PYNQ_reboot_uart_PL'):
        if runtime.get(key, {}).get('passed') is not True:
            failures.append('hardware runtime trial not passed: ' + key)
    firmware = manifest.get('artifacts', {}).get('stm32_bin', {}).get('sha256')
    if runtime.get('firmware', {}).get('firmware_sha256') != firmware:
        failures.append('hardware evidence firmware differs from release package')
    return proof_path, runtime_path


def inspect_release(project_root, release_record='release_manifest.json'):
    root = Path(project_root).resolve()
    release_path = within(root, release_record)
    release = read_json(release_path)
    if release.get('schema') != 'pynq-z2-ar-car-release/v1':
        raise ValueError('unsupported release manifest schema')
    failures = []
    candidate_path = within(root, release.get('candidate_record', ''))
    candidate_result = inspect(root, candidate_path, check_current_sources=False)
    failures.extend(candidate_result['failures'])
    candidate = read_json(candidate_path)
    candidate_package = within(root, candidate.get('package_dir', ''))
    candidate_manifest = read_json(candidate_package / 'lab_manifest.json')
    candidate_artifacts = candidate_manifest.get('artifacts', {})
    package = within(root, release.get('package_dir', ''))
    manifest_path = package / 'lab_manifest.json'
    manifest = read_json(manifest_path)
    if manifest.get('integrated_id') != candidate.get('contract_id'):
        failures.append('release contract differs from candidate')
    if manifest.get('classification') != 'LAB_ONLY_NO_MOTOR_NON_RELEASE':
        failures.append('release classification must remain LAB_ONLY_NO_MOTOR_NON_RELEASE')
    contracts = manifest.get('contracts', {})
    if contracts.get('motor_output_allowed') is not False or contracts.get('serial_motion_allowed') is not False:
        failures.append('release motion restrictions missing')
    identity, changed, checked_sources = verify_current_sources(root, manifest, failures)
    if identity.get('integrated_id') != candidate.get('contract_id'):
        failures.append('release source contract differs from candidate')
    declared_changes = release.get('software_patch_sources', [])
    if sorted(declared_changes) != changed:
        failures.append('release patch list differs from actual source delta')
    payloads = verify_package(root, package, manifest, candidate_artifacts, failures)
    verify_release_archive(root, release, manifest, payloads, failures)
    proof_path, runtime_path = verify_evidence(root, release, manifest, failures)
    binding_path = within(root, str(package / 'artifact_source_binding.json'))
    binding = read_json(binding_path)
    if binding.get('source_identity') != manifest.get('source_identity'):
        failures.append('artifact source binding differs from release manifest source identity')
    if binding.get('artifacts') != manifest.get('artifacts'):
        failures.append('artifact source binding differs from release artifacts')
    return {
        'schema': 'skill-release-inspection/v1',
        'consistency_ok': not failures,
        'failures': failures,
        'candidate': candidate.get('name'),
        'release': release.get('name'),
        'contract_id': candidate.get('contract_id'),
        'classification': manifest.get('classification'),
        'candidate_artifacts_reused': True,
        'changed_sources_after_candidate': changed,
        'source_files_checked': checked_sources,
        'package_payloads_checked': len(payloads),
        'hardware_proof': str(proof_path.relative_to(root)),
        'runtime_evidence': str(runtime_path.relative_to(root)),
        'hardware_scope': release.get('hardware_scope'),
        'full_vehicle_acceptance': release.get('full_vehicle_acceptance'),
        'limits': [
            'file identities and recorded evidence only',
            'not a new Vivado, electrical, calibration or motion test',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    parser.add_argument('--release', default='release_manifest.json')
    args = parser.parse_args()
    try:
        result = inspect_release(args.project_root, args.release)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({'consistency_ok': False, 'failures': [str(exc)]}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['consistency_ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
