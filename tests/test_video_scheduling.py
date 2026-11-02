import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pynq_fpga/preintegration/host'))
import wireless_runtime as runtime
class SchedulerTests(unittest.TestCase):
 def test_native_worker_quantum_is_scoped_and_restored_on_failure(self):
  previous=sys.getswitchinterval()
  def fail(argv):
   self.assertAlmostEqual(sys.getswitchinterval(),.001)
   raise RuntimeError('startup failure')
  with patch.object(runtime,'PROFILE','wireless360'),patch.object(runtime,'_run_main',side_effect=fail):
   with self.assertRaisesRegex(RuntimeError,'startup failure'):runtime.main([])
  self.assertAlmostEqual(sys.getswitchinterval(),previous)
 def test_hd_profile_preserves_embedding_scheduler(self):
  previous=sys.getswitchinterval()
  with patch.object(runtime,'PROFILE','wireless720'),patch.object(runtime,'_run_main',side_effect=lambda argv:sys.getswitchinterval()):
   self.assertAlmostEqual(runtime.main([]),previous)
  self.assertAlmostEqual(sys.getswitchinterval(),previous)
