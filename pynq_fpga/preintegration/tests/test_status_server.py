import json
from pathlib import Path
import sys
import tempfile
import time
import re
import shutil
import subprocess
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from status_server import StatusServer, PAGE
from test_joint_runtime import Client, Link
from system_runtime import JointRunner
from calibration_config import CalibrationConfig, WheelCalibration


class StatusServerTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is unavailable for JS syntax validation')
    def test_actual_page_javascript_parses(self):
        script=re.search(r'<script>(.*?)</script>',PAGE,re.S).group(1)
        subprocess.run(['node','-e','new Function(require("fs").readFileSync(0,"utf8"));'],
                       input=script,text=True,check=True,capture_output=True)
    def test_real_http_auth_queue_logs_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=Link();runner=JointRunner(Client(link),link,output_dir=tmp,identity={})
            runner._journal=open(Path(tmp)/'joint.jsonl','w',encoding='utf-8')
            try:
                with StatusServer(runner) as server:
                    base=f'http://127.0.0.1:{server.port}'
                    def request(path,body=None,authorized=True):
                        headers={'Authorization':'Bearer '+server.token} if authorized else {}
                        data=None if body is None else json.dumps(body).encode()
                        return urlopen(Request(base+path,data=data,headers=headers),timeout=2)
                    with request('/') as response:
                        self.assertIn('STM32实际锁存',response.read().decode())
                    with self.assertRaises(HTTPError) as missing:
                        request('/api/status',authorized=False)
                    self.assertEqual(missing.exception.code,401)
                    missing.exception.close()
                    with request('/api/status') as response:
                        self.assertTrue(json.load(response)['running'])
                    config=CalibrationConfig(WheelCalibration(5362),WheelCalibration(5400),'measured test',True)
                    with request('/api/calibration',config.payload()) as response:
                        self.assertEqual(response.status,202)
                    queued=runner.actions.get_nowait()
                    self.assertEqual(queued['config'],config)
                    self.assertEqual(link.commands,[]) # HTTP did not write hardware.
                    with self.assertRaises(HTTPError) as malformed:
                        request('/api/calibration',{'left':{'scale':1}})
                    self.assertEqual(malformed.exception.code,400)
                    malformed.exception.close()
                    with request('/api/stop',{}) as response:
                        self.assertEqual(response.status,202)
                    self.assertEqual(runner.actions.get_nowait()['kind'],'stop')
                    runner.log({'type':'fixture','hardware':False})
                    with request('/api/log/joint.jsonl') as response:
                        self.assertFalse(json.loads(response.read())['hardware'])
                    with self.assertRaises(HTTPError) as missing_log:
                        request('/api/log/../../secret')
                    missing_log.exception.close()
                self.assertFalse(server.thread.is_alive())
            finally:runner._journal.close()

    def test_stalled_control_cannot_leave_green_status_on_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=Link();runner=JointRunner(Client(link),link,output_dir=tmp,identity={})
            now=time.monotonic_ns()
            runner.latest={'status':{'published_monotonic_ns':now-300_000_000,
                                    'distance_valid':True,'speed_valid':True,
                                    'odometry_valid':True,'car_valid':True,
                                    'car_age_s':.6,'pl_stop':False}}
            status=runner.status_snapshot()
            self.assertFalse(status['telemetry_fresh'])
            self.assertFalse(status['latest']['status']['car_valid'])
            self.assertFalse(status['latest']['status']['odometry_valid'])
            self.assertIsNone(status['latest']['status']['pl_stop'])
            # Consumer cannot mutate the actual control snapshot.
            self.assertTrue(runner.latest['status']['car_valid'])

    def test_invalid_calibration_never_enters_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=Link();runner=JointRunner(Client(link),link,output_dir=tmp,identity={})
            with self.assertRaisesRegex(RuntimeError,'not running'):
                runner.enqueue_action('stop')
            runner._journal=object()
            with self.assertRaises(ValueError):
                runner.enqueue_action('calibration',{})
            self.assertTrue(runner.actions.empty())
            self.assertIn("join('\\n')", PAGE)


if __name__=='__main__':unittest.main()
