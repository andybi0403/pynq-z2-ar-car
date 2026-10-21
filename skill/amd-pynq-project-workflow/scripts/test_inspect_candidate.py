"""Synthetic file-consistency counterexamples; no board or project changes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from inspect_candidate import digest_file, inspect


class CandidateInspection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / 'pynq_fpga'
        self.package = self.base / 'lab/candidate'
        self.evidence = self.base / 'preintegration/evidence/test'
        self.build = self.base / 'fpga/build/test'
        for folder in (self.package, self.evidence, self.build, self.base / 'fpga/registers'):
            folder.mkdir(parents=True, exist_ok=True)
        self.write(self.base / 'fpga/registers/register_map.json', {'integrated_id': '0xCAFE'})
        (self.build / 'task7_8_integrated.xpr').write_bytes(b'synthetic project')
        (self.base / 'source.v').write_bytes(b'synthetic source')
        for name in ('app.py', 'test.bit', 'test.hwh'):
            (self.package / name).write_bytes(('synthetic ' + name).encode())
        self.manifest = {'schema': 'car-lab-artifact/v1', 'integrated_id': '0xCAFE',
                         'classification': 'LAB_ONLY_NO_MOTOR_NON_RELEASE',
                         'contracts': {'motor_output_allowed': False, 'serial_motion_allowed': False},
                         'source_identity': {'integrated_id': '0xCAFE', 'sources': {'source.v': digest_file(self.base / 'source.v')}},
                         'runtime_files': {'app.py': digest_file(self.package / 'app.py')},
                         'artifacts': {key: {'file': 'test.' + key, 'bytes': (self.package / ('test.' + key)).stat().st_size,
                                           'sha256': digest_file(self.package / ('test.' + key))} for key in ('bit', 'hwh')}}
        self.write(self.package / 'lab_manifest.json', self.manifest)
        self.record = {'schema': 'car-complete-build/v1', 'name': 'synthetic', 'contract_id': '0xCAFE',
                       'status': 'LAB_ONLY_CANDIDATE', 'hardware': 'PENDING', 'stages': [],
                       'package_dir': str(self.package), 'evidence_dir': str(self.evidence), 'build_dir': str(self.build),
                       'zip_path': str(self.package) + '.zip'}
        for name in ('source_start', 'regression', 'source_after_regression', 'build', 'package', 'source_final'):
            log = self.evidence / (name + '.log')
            log.write_bytes(('synthetic ' + name).encode())
            self.record['stages'].append({'name': name, 'status': 'PASS', 'log_sha256': digest_file(log)})
        self.archive()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def save(self):
        self.write(self.base / 'preintegration/latest_candidate.json', self.record)
        self.write(self.evidence / 'pipeline.json', self.record)

    def archive(self, overrides=None, duplicate=None):
        with zipfile.ZipFile(self.record['zip_path'], 'w') as bundle:
            for path in self.package.iterdir():
                bundle.writestr(path.name, (overrides or {}).get(path.name, path.read_bytes()))
            if duplicate:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    bundle.writestr(duplicate, b'duplicate')
        self.record['zip_sha256'] = digest_file(Path(self.record['zip_path']))
        self.save()

    def assert_rejected(self, expected):
        result = inspect(self.root)
        self.assertFalse(result['consistency_ok'])
        self.assertTrue(any(expected in item for item in result['failures']), result)
        self.assertFalse(result['hardware_checked'])

    def test_matching_fixture_only_proves_files(self):
        before = {str(p): digest_file(p) for p in self.root.rglob('*') if p.is_file()}
        result = inspect(self.root)
        self.assertTrue(result['consistency_ok'])
        self.assertFalse(result['hardware_checked'])
        self.assertEqual(result['reported_hardware_status'], 'PENDING')
        after = {str(p): digest_file(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_stale_source(self):
        (self.base / 'source.v').write_bytes(b'changed')
        self.assert_rejected('source missing or changed')

    def test_contract_mismatch(self):
        self.write(self.base / 'fpga/registers/register_map.json', {'integrated_id': '0xBAD'})
        self.assert_rejected('current register source')

    def test_incomplete_stage(self):
        self.record['stages'][1]['status'] = 'FAILED'; self.save()
        self.assert_rejected('stage not complete')

    def test_missing_required_stage(self):
        self.record['stages'].pop(1); self.save()
        self.assert_rejected('required stages')

    def test_stale_log(self):
        (self.evidence / 'build.log').write_bytes(b'changed')
        self.assert_rejected('stage log missing or changed')

    def test_stale_runtime(self):
        (self.package / 'app.py').write_bytes(b'changed')
        self.assert_rejected('package payload changed')

    def test_missing_bit(self):
        (self.package / 'test.bit').unlink()
        self.assert_rejected('package payload missing')

    def test_zip_runtime_tamper_with_new_archive_digest(self):
        self.archive({'app.py': b'changed'})
        self.assert_rejected('ZIP payload changed')

    def test_zip_duplicate(self):
        self.archive(duplicate='app.py')
        self.assert_rejected('duplicate ZIP entries')

    def test_zip_manifest_mismatch(self):
        self.archive({'lab_manifest.json': b'{}'})
        self.assert_rejected('ZIP manifest differs')

    def test_pointer_outside_root(self):
        self.record['package_dir'] = str(self.root.parent / 'outside'); self.save()
        with self.assertRaisesRegex(ValueError, 'outside project'):
            inspect(self.root)

    def test_missing_identity_map(self):
        self.manifest['runtime_files'] = {}; self.write(self.package / 'lab_manifest.json', self.manifest)
        with self.assertRaisesRegex(ValueError, 'runtime map'):
            inspect(self.root)

    def test_motion_flag_rejected(self):
        self.manifest['contracts']['motor_output_allowed'] = True
        self.write(self.package / 'lab_manifest.json', self.manifest); self.archive()
        self.assert_rejected('motion restrictions')

    def test_cli_failure_is_nonzero(self):
        (self.base / 'source.v').write_bytes(b'changed')
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('inspect_candidate.py')),
                                 '--project-root', str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)['consistency_ok'])


if __name__ == '__main__':
    unittest.main()
