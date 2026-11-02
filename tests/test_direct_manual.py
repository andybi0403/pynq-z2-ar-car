"""Direct mode with actual CarLink and compiled production STM32 C; offline."""
from pathlib import Path
import sys,unittest,io,tempfile,threading,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'pynq_fpga/preintegration/host'),str(ROOT/'pynq_fpga/host/tests')]
from supervisor_c_fixture import SupervisorCFixture
from trial_control import DirectManualControl

class DirectTests(unittest.TestCase):
    def fixture(self):
        h=SupervisorCFixture()
        # Local sensor-acquisition fixture, independent of PL reads or video.
        h.link.sensor_snapshot=lambda now=None:{'us_valid':h.pl.valid,'mm':h.pl.mm,
            'ir':h.pl.ir,'us_sample_s':h.clock()}
        h.control=DirectManualControl(h.link,clock=h.clock,motion_allowed=True)
        tick=h.control.tick
        h.control.tick=lambda:(None,None,tick())  # Existing UART/C harness tuple.
        h.control.stop()
        h.pl.command_writes.clear()
        return h

    def test_zero_hold_release_ack_then_new_intent_moves_actual_c(self):
        h=self.fixture();h.arm();h.drive(1600,1600)
        self.assertEqual(h.c.log[-1][3:5],(1600,1600))

    def test_feedback_published_while_snapshot_waits_is_not_from_future(self):
        h=self.fixture();h.arm()
        original=h.link.status_snapshot
        def interleaved():
            h.ms.advance(1)
            car,seq,_=original()
            return car,seq,h.clock()
        h.link.status_snapshot=interleaved
        h.control.tick()
        self.assertTrue(h.control.last['car_fresh'])
        self.assertEqual(h.control._phase,'ARMED')

    def test_no_mmio_calls_even_with_disconnected_or_frozen_pl(self):
        h=self.fixture();h.pl.error=True;h.pl.sampling=False
        h.arm();h.drive();h.advance(1000)
        self.assertFalse(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(900,900))
        self.assertEqual(h.pl.command_writes,[])

    def test_near_obstacle_250_stops_actual_c_and_requires_manual_release(self):
        h=self.fixture();h.arm();h.drive();h.pl.mm=250;h.advance(250)
        self.assertEqual(h.c.log[-1][3:5],(0,0));self.assertEqual(h.control._phase,'LOCKED')
        h.pl.mm=1000;h.intent=(0,0);h.advance(500)
        self.assertTrue(h.c.s.latched);self.assertEqual(h.control._phase,'LOCKED')

    def test_251mm_and_unknown_range_continue(self):
        h=self.fixture();h.pl.mm=251;h.arm();h.drive()
        h.pl.valid=False;h.advance(500)
        self.assertFalse(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(900,900))
        self.assertFalse(h.link._cmd[2])

    def test_frozen_control_worker_stops_through_independent_uart(self):
        h=self.fixture();h.arm();h.drive();h.control_enabled=False;h.advance(400)
        self.assertTrue(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(0,0))

    def test_500ms_intent_lease_not_renewed_by_fresh_feedback(self):
        h=self.fixture();h.arm();h.drive();h.heartbeat=False;h.advance(300)
        self.assertFalse(h.c.s.latched)
        h.advance(300);self.assertTrue(h.c.s.latched)

    def test_feedback_loss_stops_even_if_intents_continue(self):
        h=self.fixture();h.arm();h.drive();h.status_enabled=False;h.advance(900)
        self.assertTrue(h.c.s.latched);self.assertFalse(h.control.last['car_fresh'])

    def test_zero_output_after_key_release_without_reclaim(self):
        h=self.fixture();h.arm();h.drive();h.drive(0,0);h.advance(300)
        self.assertFalse(h.c.s.latched);self.assertEqual(h.control._phase,'ARMED')
        h.drive(-900,-900)

    def test_transport_failure_and_explicit_stop_keep_zero(self):
        for failure in ('transport','operator'):
            h=self.fixture();h.arm();h.drive()
            if failure=='transport':h.link.transport_error='injected serial failure'
            else:h.control.stop()
            h.advance(250)
            self.assertTrue(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(0,0))

if __name__=='__main__':unittest.main()
