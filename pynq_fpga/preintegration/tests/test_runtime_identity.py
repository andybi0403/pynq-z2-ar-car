from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
import system_runtime
from runtime_identity import runtime_hashes,session_identity,RUNTIME_FILES,sha256,expected_identity_from_package


class RuntimeIdentityTests(unittest.TestCase):
    def test_offline_identity_checks_all_packaged_sources_and_actual_calibration(self):
        from calibration_config import CalibrationConfig,WheelCalibration
        import car_regs as reg
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            bit=folder/'task7_8_LAB_ONLY.bit';hwh=folder/'task7_8_LAB_ONLY.hwh'
            bit.write_bytes(b'NON_HARDWARE_TEST_BIT');hwh.write_bytes(b'NON_HARDWARE_TEST_HWH')
            for name in RUNTIME_FILES:(folder/name).write_text('# software fixture\n',encoding='utf-8')
            package={'schema':'car-lab-artifact/v1','classification':'LAB_ONLY_NO_MOTOR_NON_RELEASE',
                     'integrated_id':f'0x{reg.INTEGRATED_ID:08X}',
                     'contracts':{'release_gate':'BLOCKED_EXPECTED','motor_output_allowed':False},
                     'artifacts':{key:{'file':file.name,'bytes':file.stat().st_size,'sha256':sha256(file)}
                                  for key,file in [('bit',bit),('hwh',hwh)]},
                     'runtime_files':{name:sha256(folder/name) for name in RUNTIME_FILES}}
            (folder/'lab_manifest.json').write_text(json.dumps(package),encoding='utf-8')
            calibration=CalibrationConfig(WheelCalibration(5362),WheelCalibration(5400),'unit test only',False)
            configuration=folder/'calibration.json';calibration.save(configuration)
            # Only HWH structure is mocked; production manifest/hash/calibration
            # verification runs on every real file in this synthetic package.
            with patch('lab_acceptance.validate_artifact_pair'):
                identity=expected_identity_from_package(folder,configuration)
                self.assertEqual(identity['calibration'],calibration.payload())
                self.assertEqual(identity['runtime_sources'],package['runtime_files'])
                (folder/'pynq_link.py').write_text('# replaced\n',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'runtime source mismatch'):
                    expected_identity_from_package(folder,configuration)

    def test_actual_runtime_sources_have_complete_hash_binding(self):
        code=runtime_hashes()
        self.assertEqual(set(code),set(RUNTIME_FILES))
        for digest in code.values():self.assertRegex(digest,'^[0-9a-f]{64}$')
        self.assertEqual(code['system_runtime.py'],sha256(system_runtime.__file__))

    def test_replaced_runtime_cannot_be_bound_to_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);bit=folder/'x.bit';hwh=folder/'x.hwh';manifest=folder/'manifest.json'
            bit.write_bytes(b'fixture_bit');hwh.write_bytes(b'fixture_hwh')
            manifest.write_text(json.dumps({'runtime_files':{'a.py':'aaa'},'build_parameters':{'REACTION_MS':150}}))
            with patch('runtime_identity.runtime_hashes',return_value={'a.py':'aaa'}):
                identity=session_identity(bit,hwh,manifest,{'fixture':True})
                self.assertEqual(identity['bit_sha256'],sha256(bit))
                self.assertEqual(identity['manifest_sha256'],sha256(manifest))
            with patch('runtime_identity.runtime_hashes',return_value={'a.py':'changed'}):
                with self.assertRaisesRegex(ValueError,'differs'):
                    session_identity(bit,hwh,manifest,{'fixture':True})
