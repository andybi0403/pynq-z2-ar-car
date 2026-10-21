"""Read-only consistency inspection for this car project's candidate schema.

No project modules imported, no hardware opened, no files written.
This checks declared file identities, not semantic correctness or physical safety.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


def digest_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()


def digest_file(path):
    with path.open('rb') as stream:
        return digest_stream(stream)


def read_json(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'JSON object required: {path}')
    return value


def within(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError('nonempty file path required')
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f'path outside project; migrate explicitly: {value}')
    return path


def hashed_map(value, label):
    if not isinstance(value, dict) or not value:
        raise ValueError(f'nonempty {label} map required')
    for name, digest in value.items():
        if not isinstance(name, str) or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise ValueError(f'invalid {label} entry: {name}')
    return value


def inspect(project_root, candidate=None, check_current_sources=True):
    root = Path(project_root).resolve()
    record_path = within(root, str(candidate or 'pynq_fpga/preintegration/latest_candidate.json'))
    record = read_json(record_path)
    if record.get('schema') != 'car-complete-build/v1':
        raise ValueError('unsupported candidate schema')
    failures = []
    spec = read_json(root / 'pynq_fpga/fpga/registers/register_map.json')
    if record.get('contract_id') != spec.get('integrated_id'):
        failures.append('candidate contract differs from current register source')
    if record.get('status') != 'LAB_ONLY_CANDIDATE':
        failures.append('candidate is not a completed LAB_ONLY_CANDIDATE')
    package = within(root, record.get('package_dir'))
    evidence = within(root, record.get('evidence_dir'))
    build = within(root, record.get('build_dir'))
    if not (build / 'task7_8_integrated.xpr').is_file():
        failures.append('candidate Vivado project missing')
    if read_json(evidence / 'pipeline.json') != record:
        failures.append('latest record differs from its evidence pipeline')
    stages = record.get('stages')
    if not isinstance(stages, list) or any(not isinstance(item, dict) for item in stages):
        raise ValueError('stage list required')
    names = [item.get('name') for item in stages]
    required = ['source_start', 'regression', 'source_after_regression', 'build', 'package', 'source_final']
    if 'stm32_firmware' in names:
        required.insert(0, 'stm32_firmware')
    if record.get('video_profile') == 'wireless720':
        required.insert(0, 'wireless_native')
    if names != required or len(names) != len(set(names)):
        failures.append('required stages missing, reordered or duplicated')
    for stage in stages:
        name = stage.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_]+', name):
            raise ValueError('invalid stage name')
        if stage.get('status') != 'PASS':
            failures.append(f'stage not complete: {name}')
        path = within(root, str(evidence / (name + '.log')))
        if not path.is_file() or digest_file(path) != stage.get('log_sha256'):
            failures.append(f'stage log missing or changed: {name}')
    manifest_path = package / 'lab_manifest.json'
    manifest = read_json(manifest_path)
    if manifest.get('schema') != 'car-lab-artifact/v1':
        raise ValueError('unsupported package manifest schema')
    if manifest.get('integrated_id') != record.get('contract_id'):
        failures.append('package contract differs from candidate')
    if manifest.get('classification') != 'LAB_ONLY_NO_MOTOR_NON_RELEASE':
        failures.append('unexpected package classification')
    contracts = manifest.get('contracts', {})
    if contracts.get('motor_output_allowed') is not False or contracts.get('serial_motion_allowed') is not False:
        failures.append('LAB_ONLY motion restrictions missing')
    source = manifest.get('source_identity', {})
    if source.get('integrated_id') != record.get('contract_id'):
        failures.append('source identity differs from candidate')
    sources = hashed_map(source.get('sources'), 'source')
    if check_current_sources:
        for name, expected in sources.items():
            base = root if name.startswith('workspace/') else root / 'pynq_fpga'
            relative = name[len('workspace/'):] if name.startswith('workspace/') else name
            path = within(root, str(base / relative))
            if not path.is_file() or digest_file(path) != expected.lower():
                failures.append(f'declared source missing or changed: {name}')
    runtime = hashed_map(manifest.get('runtime_files'), 'runtime')
    payloads = {name: {'sha256': value} for name, value in runtime.items()}
    if manifest.get('wireless_files'):
        for name, value in hashed_map(manifest['wireless_files'], 'wireless').items():
            if name in payloads and payloads[name]['sha256'] != value:
                raise ValueError('conflicting runtime and wireless identity')
            payloads[name] = {'sha256': value}
    artifacts = manifest.get('artifacts')
    expected_artifacts = {'bit', 'hwh'}
    if source.get('sensor_source') == 'stm32_uart_v3':
        expected_artifacts.update({'stm32_hex', 'stm32_bin', 'stm32_elf'})
        if 'stm32_firmware' not in names:
            failures.append('hybrid candidate missing firmware build stage')
        if manifest.get('sensor_source') != source.get('sensor_source'):
            failures.append('sensor source differs from build identity')
        firmware = source.get('stm32_firmware', {})
        for extension in ('hex', 'bin', 'elf'):
            if (artifacts or {}).get('stm32_' + extension, {}).get('sha256') != firmware.get(extension):
                failures.append('firmware differs from source binding: ' + extension)
    if not isinstance(artifacts, dict) or set(artifacts) != expected_artifacts:
        raise ValueError('matching FPGA and firmware artifact records required')
    for artifact in artifacts.values():
        if not isinstance(artifact, dict) or not isinstance(artifact.get('file'), str):
            raise ValueError('invalid artifact record')
        if artifact['file'] in payloads:
            raise ValueError('duplicate payload identity')
        hashed_map({artifact['file']: artifact.get('sha256')}, 'artifact')
        if type(artifact.get('bytes')) is not int or artifact['bytes'] <= 0:
            raise ValueError('positive artifact byte count required')
        payloads[artifact['file']] = artifact
    for name, expected in payloads.items():
        path = within(root, str(package / name))
        if not path.is_relative_to(package) or not path.is_file():
            failures.append(f'package payload missing or outside package: {name}')
        elif digest_file(path) != expected['sha256'].lower() or ('bytes' in expected and path.stat().st_size != expected['bytes']):
            failures.append(f'package payload changed: {name}')
    archive = within(root, record.get('zip_path'))
    if digest_file(archive) != record.get('zip_sha256'):
        failures.append('ZIP differs from candidate digest')
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.namelist()
        if len(entries) != len(set(entries)):
            failures.append('duplicate ZIP entries')
        if 'lab_manifest.json' not in entries or bundle.read('lab_manifest.json') != manifest_path.read_bytes():
            failures.append('ZIP manifest differs from unpacked package')
        for name, expected in payloads.items():
            if name not in entries:
                failures.append(f'ZIP payload missing: {name}')
                continue
            with bundle.open(name) as stream:
                digest = digest_stream(stream)
            if digest != expected['sha256'].lower():
                failures.append(f'ZIP payload changed: {name}')
    return {'schema': 'skill-candidate-inspection/v1', 'consistency_ok': not failures,
            'failures': failures, 'name': record.get('name'), 'contract_id': record.get('contract_id'),
            'classification': manifest.get('classification'), 'reported_hardware_status': record.get('hardware'),
            'hardware_checked': False, 'declared_sources_checked': len(sources),
            'runtime_files_checked': len(runtime), 'stages_checked': len(stages),
            'package_payloads_checked': len(payloads),
            'limits': ['declared identities only; use source_provenance.py for full input-set check',
                       'not semantic HWH, timing, board, calibration or motion acceptance']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    parser.add_argument('--candidate', type=Path, help='explicit candidate record inside project')
    parser.add_argument('--skip-current-sources', action='store_true',
                        help='validate the immutable candidate only; use inspect_release.py for source state')
    args = parser.parse_args()
    try:
        result = inspect(args.project_root, args.candidate, not args.skip_current_sources)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({'consistency_ok': False, 'hardware_checked': False, 'failures': [str(exc)]}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['consistency_ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
