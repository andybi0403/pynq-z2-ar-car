from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
import deployment_check


class DeploymentTests(unittest.TestCase):
    def test_wireless_uses_aiohttp_native_without_legacy_ffmpeg_requirement(self):
        with patch('lab_acceptance.verify_package',return_value={'integrated_id':'fixture','video_profile':'wireless720'}), \
             patch('deployment_check.importlib.util.find_spec',return_value=object()), \
             patch('deployment_check.shutil.which',return_value=None):
            result=deployment_check.inspect(Path('fixture'),board=True)
            self.assertNotIn('FFmpeg is missing',result['failures'])
            self.assertIn('aiohttp',result['dependencies'])
            self.assertIn('build pinned ARM libcar_video.so before wireless startup',result['failures'])
    def test_offline_check_verifies_package_without_probing_board(self):
        with patch('lab_acceptance.verify_package',return_value={'integrated_id':'fixture'} ) as verify, \
             patch('deployment_check.subprocess.run',side_effect=AssertionError('unexpected probe')):
            result=deployment_check.inspect(Path('fixture'))
            self.assertTrue(result['passed'])
            self.assertFalse(result['board_prerequisites_checked'])
            self.assertEqual(result['hardware_acceptance'],'PENDING')
            self.assertFalse(result['overlay_loaded']);self.assertFalse(result['serial_opened'])
            self.assertEqual(verify.call_args.args[0],Path('fixture/task7_8_LAB_ONLY.bit'))

    def test_missing_board_dependencies_fail_without_hardware_operations(self):
        with patch('lab_acceptance.verify_package',return_value={'integrated_id':'fixture'}), \
             patch('deployment_check.importlib.util.find_spec',return_value=None), \
             patch('deployment_check.shutil.which',return_value=None):
            result=deployment_check.inspect(Path('fixture'),board=True,camera='missing-camera',uart='missing-uart')
            self.assertFalse(result['passed'])
            self.assertIn('missing board dependency pynq',result['failures'])
            self.assertIn('FFmpeg is missing',result['failures'])
            self.assertFalse(result['overlay_loaded']);self.assertFalse(result['serial_opened'])

    def test_ffmpeg_version_probe_is_bounded(self):
        with patch('lab_acceptance.verify_package',return_value={'integrated_id':'fixture'}), \
             patch('deployment_check.importlib.util.find_spec',return_value=object()), \
             patch('deployment_check.shutil.which',return_value='ffmpeg-fixture'), \
             patch('deployment_check.subprocess.run',side_effect=subprocess.TimeoutExpired('ffmpeg-fixture',3)) as probe:
            result=deployment_check.inspect(Path('fixture'),board=True,camera='missing-camera',uart='missing-uart')
            self.assertFalse(result['passed'])
            self.assertIn('FFmpeg version probe failed or timed out',result['failures'])
            self.assertEqual(probe.call_args.kwargs['timeout'],3)
