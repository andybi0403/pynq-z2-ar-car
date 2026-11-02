from pathlib import Path
import sys,io,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'pynq_fpga/preintegration/host'),str(ROOT/'pynq_fpga/host')]
from system_runtime import JointRunner
from async_journal import AsyncJournal
class IntegrationTests(unittest.TestCase):
 def test_runner_routes_log_to_worker_and_preserves_critical_transition(self):
  runner=JointRunner(object(),object(),output_dir='unused',identity={})
  runner._journal=io.StringIO();runner._async_journal=AsyncJournal(runner._journal)
  event={'type':'sample','control':{'phase':'LOCKED','requested_pwm':[0,0],'car':{'lock':1,'fault':0}}}
  with patch('system_runtime.json.dumps',side_effect=AssertionError('caller serialized JSON')):
   # json module is shared with worker, so patch only submit boundary here.
   with patch.object(runner._async_journal,'submit',return_value=True) as submit:
    runner.log(event);self.assertTrue(submit.call_args.kwargs['critical'])
    runner.log(event);self.assertFalse(submit.call_args.kwargs['critical'])
  runner.log({'type':'end'});runner._async_journal.close()
  self.assertEqual(runner.journal_status()['written_records'],1)
if __name__=='__main__':unittest.main()
