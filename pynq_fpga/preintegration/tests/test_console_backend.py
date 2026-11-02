"""Integrated console mode transitions, with production supervisor policy."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
import threading
import time
from types import SimpleNamespace

PROJECT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(PROJECT/'host'),str(PROJECT/'preintegration/host'),str(Path(__file__).parent)]
from test_joint_runtime import Client,Link
from console_backend import ConsoleRunner,ConsoleServer,AuditedSerial
from trial_control import TrialMailbox
from wireless_core import VideoHub
import car_regs as reg


class IO:
    def read32(self,offset):
        return {reg.QEI0_SCALE:0,reg.QEI1_SCALE:0,reg.QEI0_ZERO:10000000,reg.QEI1_ZERO:10000000}.get(offset,0)


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.link=Link();self.client=Client(self.link);self.client.io=IO()
        self.link.status_snapshot=lambda:(self.link.state,self.link.state_seq,self.link.state_rx_time)
        self.link.sensor_snapshot=lambda now=None:({'us_valid':True,'mm':1000,'ir':0,'us_sample_s':time.monotonic()} if self.link.state else None)
        self.link.update_control_observation=lambda stamp:None
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
        self.runner.drive_owner.step()

    def tearDown(self):self.tmp.cleanup()

    def action(self,kind,value):
        self.runner.enqueue_action(kind,value)
        self.runner.control_tick()
        return self.runner.console_action

    def test_connected_start_has_single_workflow_but_remains_locked(self):
        self.assertTrue(self.runner.control.motion_allowed)
        self.assertEqual(self.runner.control._phase,'LOCKED')
        self.assertFalse(self.runner.release_was_sent())
        self.assertEqual(self.runner.release_requests,0)
        console=self.runner.status_snapshot()['console']
        self.assertNotIn('mode',console)
        self.assertFalse(console['operation_mode_required'])
        self.assertEqual(console['control_flow'],'claim_release')
        self.assertEqual(console['pwm_limit'],2400)
        self.assertEqual(console['default_pwm'],1800)
        self.assertEqual(self.runner.control.LEASE_S,.5)
        self.assertEqual(self.runner.control.yellow_pwm_limit,2400)

    def test_old_tabs_cannot_switch_back_to_observe_or_revoke_new_intent(self):
        self.mail.submit(200,200)
        with self.assertRaisesRegex(ValueError,'运行方式已取消'):
            self.runner.enqueue_action('mode',{'mode':'observe'})
        self.assertTrue(self.runner.control.motion_allowed)
        self.assertEqual(self.mail.consume()[0],'intent')

    def test_no_encoder_calibration_is_required(self):
        self.runner.calibration_measured=False
        self.assertTrue(self.runner.control.motion_allowed)
        self.assertEqual(self.runner.console_scales,[0,0])

    def test_physical_state_requires_explicit_fact_and_locked_feedback(self):
        with self.assertRaises(ValueError):self.runner.enqueue_action('motor-state',{'disconnected':True})
        self.runner.control.last['car_fresh']=False
        self.assertFalse(self.action('motor-state',{'disconnected':True,'confirmed':True})['applied'])
        self.assertFalse(self.runner.motor_disconnected)

    def test_physical_disconnect_discards_motion_and_disables_release(self):
        self.mail.submit(400,400)
        self.assertTrue(self.action('motor-state',{'disconnected':True,'confirmed':True})['applied'])
        self.assertFalse(self.runner.control.motion_allowed)
        self.assertIsNone(self.runner.control._intent)
        self.mail.request_release();self.runner.control_tick()
        self.assertEqual(self.runner.control._phase,'LOCKED')
        self.assertFalse(self.runner.release_was_sent())

    def test_reconnect_enables_explicit_workflow_without_release(self):
        self.action('motor-state',{'disconnected':True,'confirmed':True})
        self.assertTrue(self.action('motor-state',{'disconnected':False,'confirmed':True})['applied'])
        self.assertTrue(self.runner.control.motion_allowed)
        self.assertEqual(self.runner.release_requests,0)
        self.assertEqual(self.runner.control._phase,'LOCKED')

    def test_110ms_jitter_preserves_current_intent_without_renewal(self):
        self.mail.submit(200,200);stops=self.link.stops
        self.runner.handle_schedule_overrun(.110)
        self.assertEqual(self.link.stops,stops)
        self.assertEqual(self.runner.schedule_jitter_count,1)
        self.assertEqual(self.mail.consume()[0],'intent')

    def test_telemetry_delay_does_not_stop_dedicated_drive_worker(self):
        stops=self.link.stops
        self.runner.handle_schedule_overrun(.200)
        self.assertIsNone(self.runner.drive_owner.fault)
        self.assertEqual(self.link.stops,stops)
        self.assertIsNone(self.runner.drive_owner.error)

    def test_real_worker_consumes_new_intents_while_mmio_thread_is_blocked(self):
        entered=threading.Event();resume=threading.Event()
        original=self.client.sample_and_decide
        def stalled_sample():
            entered.set();resume.wait(2);return original()
        self.client.sample_and_decide=stalled_sample
        worker=threading.Thread(target=self.runner._direct_loop)
        display=threading.Thread(target=self.runner.control_tick)
        worker.start();display.start()
        try:
            self.assertTrue(entered.wait(1))
            start_sequence=self.runner.control._last_sequence
            for _ in range(5):self.mail.submit(0,0);time.sleep(.04)
            self.assertGreater(self.runner.control._last_sequence,start_sequence+2)
            self.assertTrue(self.runner.control.snapshot()['intent_fresh'])
            stops=self.link.stops;self.runner.handle_schedule_overrun(.8)
            self.assertEqual(self.link.stops,stops)
        finally:
            self.runner.stop_event.set();resume.set();worker.join(1);display.join(1)
        self.assertFalse(worker.is_alive() or display.is_alive())

    def test_calibration_is_rejected(self):
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


class RetiredModeHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_mode_endpoint_returns_410_without_retracting_new_owner(self):
        import aiohttp
        mailbox=TrialMailbox(clock=lambda:0);hub=VideoHub()  # HTTP route behavior, independent of real scheduling.
        runner=SimpleNamespace(control=SimpleNamespace(motion_allowed=True),
                               status_snapshot=lambda:{'running':True})
        server=ConsoleServer(runner,hub,mailbox,host='127.0.0.1',port=0)
        await server.start_async()
        try:
            import time
            server.gate.connect('current')
            challenge=server.gate.challenge('current')
            stamp=time.monotonic()*1000
            server.gate.message('current',dict(type='sync',nonce=challenge['nonce'],received_ms=stamp,sent_ms=stamp))
            server.gate.message('current',dict(type='claim',client_ms=time.monotonic()*1000))
            mailbox.consume()
            mailbox.submit(200,200)
            async with aiohttp.ClientSession() as client:
                async with client.post(f'http://127.0.0.1:{server.port}/api/console/mode',
                        json={'mode':'observe'},headers={'Authorization':'Bearer '+server.token}) as response:
                    self.assertEqual(response.status,410)
            self.assertEqual(server.gate.owner,'current')
            self.assertEqual(mailbox.consume()[0],'intent')
        finally:
            await server.stop_async()

if __name__=='__main__':unittest.main()
