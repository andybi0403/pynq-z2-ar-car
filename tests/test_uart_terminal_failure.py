import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pynq_fpga/preintegration/host'))
from wireless_runtime import WirelessRunner
from system_runtime import JointRunner


class TerminalUartTests(unittest.TestCase):
    def runner(self,diagnostic):
        runner=WirelessRunner.__new__(WirelessRunner)
        runner.link=Mock();runner.link.diagnostics.return_value=diagnostic
        runner.link.locked_resync_count=0;runner.control=Mock();runner.intent_mailbox=Mock()
        runner.fail=Mock();runner.record_performance=Mock();return runner
    def test_terminal_write_timeout_cancels_intent_and_ends_session(self):
        runner=self.runner({'running':False,'transport_error':'Write timeout'})
        with patch.object(JointRunner,'step'):runner.step()
        runner.control.stop.assert_called_once();runner.intent_mailbox.stop.assert_called_once()
        runner.fail.assert_called_once_with('STM32 transport worker terminated: Write timeout')
        runner.record_performance.assert_not_called()
    def test_startup_and_live_link_do_not_trigger_recovery(self):
        for diagnostic in ({'running':False,'transport_error':None},{'running':True,'transport_error':None}):
            runner=self.runner(diagnostic)
            with patch.object(JointRunner,'step'):runner.step()
            runner.fail.assert_not_called();runner.control.stop.assert_not_called()

if __name__=='__main__':unittest.main()
