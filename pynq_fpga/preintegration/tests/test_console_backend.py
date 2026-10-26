"""Integrated console mode transitions, with production supervisor policy."""
import io
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(PROJECT/'host'),str(PROJECT/'preintegration/host'),str(Path(__file__).parent)]
from test_joint_runtime import Client,Link
from console_backend import ConsoleRunner,AuditedSerial
from trial_control import TrialMailbox
from wireless_core import VideoHub
import car_regs as reg


class IO:
    def read32(self,offset):
        return {reg.QEI0_SCALE:6000,reg.QEI1_SCALE:6000,reg.QEI0_ZERO:10000000,reg.QEI1_ZERO:10000000}.get(offset,0)


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.link=Link();self.client=Client(self.link);self.client.io=IO()
        original=self.client.sample_and_decide
        def sample():
            value=original()
            self.link.state_rx_time-=.001  # Already received before this control tick.
            return value
        self.client.sample_and_decide=sample
        self.mail=TrialMailbox()
        self.runner=ConsoleRunner(self.client,self.link,video=None,source=None,native=None,hub=VideoHub(),
            intent_mailbox=self.mail,output_dir=self.tmp.name,identity={'calibration':{'measured':True}},
            hardware=False,motor_disconnected=False,diagnostic_timing=True)
        self.runner._journal=io.StringIO()
        self.runner.control_tick()

    def tearDown(self):self.tmp.cleanup()

    def action(self,kind,value):
        self.runner.enqueue_action(kind,value)
        self.runner.control_tick()
        return self.runner.console_action

    def test_starts_observation_and_never_auto_releases(self):
        self.assertEqual(self.runner.console_mode,'observe')
        self.assertFalse(self.runner.control.motion_allowed)
        self.assertEqual(self.link.commands,[])
        self.assertFalse(self.runner.release_was_sent())

    def test_manual_mode_requires_measured_calibration(self):
        self.runner.calibration_measured=False
        result=self.action('mode',{'mode':'manual'})
        self.assertFalse(result['applied'])
        self.assertIn('实测标定',result['error'])
        self.assertFalse(self.runner.control.motion_allowed)

    def test_manual_mode_requires_connected_motors(self):
        self.runner.motor_disconnected=True
        self.assertFalse(self.action('mode',{'mode':'manual'})['applied'])

    def test_mode_change_stays_locked_and_discards_pending_motion(self):
        self.mail.submit(400,400)
        self.assertTrue(self.action('mode',{'mode':'manual'})['applied'])
        self.assertEqual(self.runner.control._phase,'LOCKED')
        self.assertIsNone(self.runner.control._intent)
        self.assertEqual(self.runner.release_requests,0)

    def test_observation_request_stops_even_without_valid_feedback(self):
        self.action('mode',{'mode':'manual'})
        self.runner.control.last['car_fresh']=False
        result=self.action('mode',{'mode':'observe'})
        self.assertTrue(result['applied'])
        self.assertFalse(self.runner.control.motion_allowed)
        self.assertGreater(self.link.stops,0)

    def test_physical_state_requires_explicit_fact_and_locked_feedback(self):
        with self.assertRaises(ValueError):self.runner.enqueue_action('motor-state',{'disconnected':True})
        self.runner.control.last['car_fresh']=False
        self.assertFalse(self.action('motor-state',{'disconnected':True,'confirmed':True})['applied'])
        self.assertFalse(self.runner.motor_disconnected)

    def test_physical_state_updates_only_in_observation(self):
        self.action('mode',{'mode':'manual'})
        self.assertFalse(self.action('motor-state',{'disconnected':True,'confirmed':True})['applied'])
        self.action('mode',{'mode':'observe'})
        self.assertTrue(self.action('motor-state',{'disconnected':True,'confirmed':True})['applied'])
        self.assertTrue(self.runner.motor_disconnected)

    def test_release_in_observation_is_rejected(self):
        self.mail.request_release();self.runner.control_tick()
        self.assertIn('先切换',self.runner.drive_owner.error)
        self.assertEqual(self.runner.control._phase,'LOCKED')

    def test_driving_timing_failure_latches_stop(self):
        self.action('mode',{'mode':'manual'})
        self.runner.handle_schedule_overrun(.110)
        self.assertTrue(self.runner.drive_owner.fault)
        self.assertEqual(self.runner.control._phase,'LOCKED')
        self.assertFalse(self.runner.release_ready)
        self.assertIn('调度超时',self.runner.drive_owner.fault)

    def test_calibration_is_rejected_in_manual_mode(self):
        self.action('mode',{'mode':'manual'})
        with self.assertRaises(ValueError):self.runner.enqueue_action('calibration',{})

    def test_audit_counts_only_completed_actual_release_writes(self):
        class Serial:
            def write(self,value):return len(value)
        serial=Serial();audit=AuditedSerial(serial)
        audit.write(b'$PSTOP#');audit.write(b'$Q1,session,sequence#')
        self.assertEqual(audit.release_tx,0)
        audit.write(b'$R1,session,sequence#')
        self.assertEqual(audit.release_tx,1)
        serial.write=lambda value:None
        audit.write(b'$R1,session,sequence#')
        self.assertEqual(audit.release_tx,1)
        serial.write=lambda value:len(value)-1
        audit.write(b'$R1,session,sequence#')
        self.assertEqual(audit.release_tx,1)


if __name__=='__main__':unittest.main()
