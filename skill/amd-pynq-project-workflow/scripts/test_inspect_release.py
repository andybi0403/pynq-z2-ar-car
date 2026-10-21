"""Synthetic release counterexamples; no board or project changes."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from inspect_candidate import digest_file
from inspect_release import inspect_release


class ReleaseInspection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'pynq_fpga'
        self.candidate_package = self.base / 'lab/candidate'
        self.release_package = self.base / 'release/current'
        self.evidence = self.base / 'preintegration/evidence/candidate'
        self.build = self.base / 'fpga/build/candidate'
        for folder in (
            self.candidate_package,
            self.release_package,
            self.evidence,
            self.build,
            self.base / 'fpga/registers',
            self.base / 'host',
            self.root / 'fw',
            self.root / 'work/proof',
        ):
            folder.mkdir(parents=True, exist_ok=True)
        self.write(self.base / 'fpga/registers/register_map.json', {'integrated_id': '0xCAFE'})
        (self.build / 'task7_8_integrated.xpr').write_bytes(b'synthetic project')
        (self.base / 'host/app.py').write_bytes(b'old app.py')
        self.write(self.root / 'fw/main.c', value=b'firmware source')
        self.candidate_sources = {
            'host/app.py': digest_file(self.base / 'host/app.py'),
            'workspace/fw/main.c': digest_file(self.root / 'fw/main.c'),
        }
        for name in ('task7_8_LAB_ONLY.bit', 'task7_8_LAB_ONLY.hwh', 'stm32_hybrid_v3.hex',
                     'stm32_hybrid_v3.bin', 'stm32_hybrid_v3.elf', 'app.py'):
            (self.candidate_package / name).write_bytes(('candidate ' + name).encode())
        candidate_artifacts = self.artifacts_for(self.candidate_package)
        self.candidate_firmware = {
            ext: candidate_artifacts['stm32_' + ext]['sha256'] for ext in ('hex', 'bin', 'elf')
        }
        self.candidate_manifest = {
            'schema': 'car-lab-artifact/v1',
            'integrated_id': '0xCAFE',
            'classification': 'LAB_ONLY_NO_MOTOR_NON_RELEASE',
            'contracts': {'motor_output_allowed': False, 'serial_motion_allowed': False},
            'sensor_source': 'stm32_uart_v3',
            'source_identity': {
                'schema': 'car-build-source/v1',
                'integrated_id': '0xCAFE',
                'sensor_source': 'stm32_uart_v3',
                'stm32_firmware': self.candidate_firmware,
                'sources': self.candidate_sources,
            },
            'runtime_files': {'app.py': digest_file(self.candidate_package / 'app.py')},
            'artifacts': candidate_artifacts,
        }
        self.write(self.candidate_package / 'lab_manifest.json', self.candidate_manifest)
        self.candidate = {
            'schema': 'car-complete-build/v1',
            'name': 'synthetic-candidate',
            'contract_id': '0xCAFE',
            'status': 'LAB_ONLY_CANDIDATE',
            'hardware': 'PENDING',
            'stages': [],
            'package_dir': str(self.candidate_package),
            'evidence_dir': str(self.evidence),
            'build_dir': str(self.build),
            'zip_path': str(self.candidate_package) + '.zip',
        }
        for name in ('wireless_native', 'stm32_firmware', 'source_start', 'regression',
                     'source_after_regression', 'build', 'package', 'source_final'):
            log = self.evidence / (name + '.log')
            log.write_bytes(('synthetic ' + name).encode())
            self.candidate['stages'].append(
                {'name': name, 'status': 'PASS', 'log_sha256': digest_file(log)}
            )
        self.candidate['video_profile'] = 'wireless720'
        self.archive_candidate()

        for path in self.candidate_package.iterdir():
            if path.is_file():
                shutil.copy2(path, self.release_package / path.name)
        (self.base / 'host/app.py').write_bytes(b'new app.py')
        (self.release_package / 'app.py').write_bytes(b'release app.py')
        for ext in ('hex', 'bin', 'elf'):
            (self.release_package / ('stm32_hybrid_v3.' + ext)).write_bytes(('release ' + ext).encode())
        artifacts = self.artifacts_for(self.release_package)
        release_firmware = {
            ext: artifacts['stm32_' + ext]['sha256'] for ext in ('hex', 'bin', 'elf')
        }
        self.release_manifest = {
            **self.candidate_manifest,
            'source_identity': {
                **self.candidate_manifest['source_identity'],
                'stm32_firmware': release_firmware,
                'software_patch_sources': {
                    'pynq_fpga/host/app.py': digest_file(self.base / 'host/app.py'),
                },
            },
            'runtime_files': {'app.py': digest_file(self.release_package / 'app.py')},
            'artifacts': artifacts,
        }
        self.write(self.release_package / 'lab_manifest.json', self.release_manifest)
        self.write(self.release_package / 'artifact_source_binding.json', {
            'schema': 'car-built-artifacts/v1',
            'source_identity': self.release_manifest['source_identity'],
            'artifacts': artifacts,
        })
        self.proof = self.root / 'work/proof/completion_audit.json'
        self.runtime_result = self.release_package / 'UART_ROLE_FIX_RESULT.json'
        self.write(self.proof, {
            'schema': 'uart-goal-completion-audit/v1',
            'all_requirements_proved': True,
            'requirements': [{'requirement': 'synthetic', 'proved': True}],
            'source_hashes': {
                'pynq_fpga/host/app.py': digest_file(self.base / 'host/app.py'),
            },
        })
        self.write(self.runtime_result, {
            'overall_vehicle_acceptance': 'NOT_CLAIMED',
            'motor_power': 'disconnected',
            'firmware': {'firmware_sha256': release_firmware['bin']},
            'normal_boot_uart_PL': {'passed': True},
            'upper_half_IR_regression': {'passed': True},
            'PYNQ_reboot_uart_PL': {'passed': True},
        })
        self.release = {
            'schema': 'pynq-z2-ar-car-release/v1',
            'name': 'synthetic-release',
            'candidate_record': 'pynq_fpga/preintegration/latest_candidate.json',
            'package_dir': str(self.release_package),
            'zip_path': str(self.release_package) + '.zip',
            'software_patch_sources': ['host/app.py'],
            'hardware_evidence': {
                'completion_audit': 'work/proof/completion_audit.json',
                'runtime_result': str(self.runtime_result.relative_to(self.root)),
            },
            'hardware_scope': 'locked no-motor bench',
            'full_vehicle_acceptance': 'NOT_CLAIMED',
        }
        self.archive_release()

    @staticmethod
    def write(path, value):
        text = json.dumps(value) if isinstance(value, dict) else value
        if isinstance(text, str):
            text = text.encode()
        path.write_bytes(text)

    @staticmethod
    def artifacts_for(package):
        def record(path):
            return {'file': path.name, 'bytes': path.stat().st_size, 'sha256': digest_file(path)}

        return {
            'bit': record(package / 'task7_8_LAB_ONLY.bit'),
            'hwh': record(package / 'task7_8_LAB_ONLY.hwh'),
            'stm32_hex': record(package / 'stm32_hybrid_v3.hex'),
            'stm32_bin': record(package / 'stm32_hybrid_v3.bin'),
            'stm32_elf': record(package / 'stm32_hybrid_v3.elf'),
        }

    def archive_candidate(self):
        with zipfile.ZipFile(self.candidate['zip_path'], 'w') as bundle:
            for path in self.candidate_package.iterdir():
                if path.is_file():
                    bundle.write(path, path.name)
        self.candidate['zip_sha256'] = digest_file(Path(self.candidate['zip_path']))
        self.write(self.base / 'preintegration/latest_candidate.json', self.candidate)
        self.write(self.evidence / 'pipeline.json', self.candidate)

    def archive_release(self):
        with zipfile.ZipFile(self.release['zip_path'], 'w') as bundle:
            for path in self.release_package.iterdir():
                if path.is_file():
                    bundle.write(path, path.name)
        self.release['zip_sha256'] = digest_file(Path(self.release['zip_path']))
        self.write(self.root / 'release_manifest.json', self.release)

    def assert_rejected(self, expected):
        result = inspect_release(self.root)
        self.assertFalse(result['consistency_ok'])
        self.assertTrue(any(expected in item for item in result['failures']), result)

    def test_matching_release_fixture(self):
        before = {str(p): digest_file(p) for p in self.root.rglob('*') if p.is_file()}
        result = inspect_release(self.root)
        self.assertTrue(result['consistency_ok'], result)
        self.assertEqual(result['changed_sources_after_candidate'], ['host/app.py'])
        self.assertEqual(result['full_vehicle_acceptance'], 'NOT_CLAIMED')
        after = {str(p): digest_file(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_unrecorded_source_drift(self):
        (self.root / 'fw/main.c').write_bytes(b'changed without patch')
        self.assert_rejected('unrecorded source drift')

    def test_patch_list_differs_from_actual_delta(self):
        self.release['software_patch_sources'] = []
        self.archive_release()
        self.assert_rejected('patch list differs')

    def test_release_artifact_changed(self):
        (self.release_package / 'task7_8_LAB_ONLY.bit').write_bytes(b'changed bit')
        self.assert_rejected('release payload changed')

    def test_firmware_identity_mismatch(self):
        self.release_manifest['artifacts']['stm32_bin']['sha256'] = '0' * 64
        self.write(self.release_package / 'lab_manifest.json', self.release_manifest)
        self.archive_release()
        self.assert_rejected('firmware source binding differs')

    def test_hardware_claim_false(self):
        proof = json.loads(self.proof.read_text())
        proof['all_requirements_proved'] = False
        self.write(self.proof, proof)
        self.assert_rejected('hardware completion audit is not fully proved')

    def test_whole_vehicle_claim_rejected(self):
        runtime = json.loads(self.runtime_result.read_text())
        runtime['overall_vehicle_acceptance'] = 'PASS'
        self.write(self.runtime_result, runtime)
        self.archive_release()
        self.assert_rejected('must not claim whole-vehicle acceptance')

    def test_zip_payload_tamper_rejected(self):
        with zipfile.ZipFile(self.release['zip_path'], 'w') as bundle:
            for path in self.release_package.iterdir():
                if path.is_file():
                    payload = b'{}' if path.name == 'lab_manifest.json' else path.read_bytes()
                    bundle.writestr(path.name, payload)
        self.release['zip_sha256'] = digest_file(Path(self.release['zip_path']))
        self.write(self.root / 'release_manifest.json', self.release)
        self.assert_rejected('release ZIP')


if __name__ == '__main__':
    unittest.main()
