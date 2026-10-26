import unittest
from supervisor_c_fixture import SupervisorCFixture


class SupervisorProductionCTests(unittest.TestCase):
    def test_illegal_qei_with_valid_zero_speed_stops_actual_c_and_never_auto_restarts(self):
        import car_regs as reg
        h=self.moving();start=h.ms()
        h.pl.mem[reg.QEI1_INFO]=255<<4
        h.advance(150)
        self.assertTrue(h.c.s.latched)
        self.assertLessEqual(h.first_stop_after(start)-start,130)
        self.assertIn('qei1_illegal_transition',h.control.last['decision_reasons'])
        h.pl.mem[reg.QEI1_INFO]=0;h.intent=(0,0);h.advance(500)
        self.assertTrue(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(0,0))

    def moving(self, **kwargs):
        fixture=SupervisorCFixture(**kwargs);self.fixture=fixture
        fixture.arm();fixture.drive();return fixture

    def test_release_then_fresh_intent_is_required_by_actual_c_outputs(self):
        h=SupervisorCFixture();self.fixture=h;h.advance(200)
        with self.assertRaises(PermissionError):h.control.request_release()
        h.advance(550);h.control.request_release();h.advance(400)
        self.assertFalse(h.c.s.latched)
        self.assertEqual(h.c.log[-1][3:5],(0,0))
        h.drive(700,600)
        self.assertEqual(h.c.log[-1][3:5],(700,600))

    def test_yellow_reduces_actual_c_pwm_and_green_does_not_replay(self):
        h=self.moving();h.heartbeat=False;h.pl.level=1;h.advance(120)
        self.assertEqual(h.c.log[-1][3:5],(400,400))
        h.pl.level=0;h.advance(40)
        self.assertEqual(h.c.log[-1][3:5],(400,400))
        h.heartbeat=True;h.next_intent=h.ms();h.advance(120)
        self.assertEqual(h.c.log[-1][3:5],(900,900))

    def test_red_stops_c_and_cannot_automatically_restart(self):
        h=self.moving();start=h.ms();h.pl.level=2;h.pl.reasons=1<<12;h.advance(150)
        self.assertTrue(h.c.s.latched)
        self.assertLessEqual(h.first_stop_after(start)-start,130)
        h.pl.level=0;h.pl.reasons=0;h.intent=(0,0);h.advance(500)
        self.assertTrue(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(0,0))
        with self.assertRaises(PermissionError):h.control.submit_intent(h.sequence+1,900,900)

    def test_intent_expiry_is_not_renewed_by_sampling_or_uart(self):
        h=self.moving();h.heartbeat=False;intent_time=h.control._intent.received_s*1000
        h.advance(400)
        self.assertTrue(h.c.s.latched)
        self.assertLessEqual(h.first_stop_after(intent_time+249)-intent_time,380)
        self.assertFalse(h.control.last['intent_fresh'])
        self.assertEqual(h.pl.command,0)

    def test_supervisor_stall_with_uart_running_revokes_old_request(self):
        h=self.moving();start=h.ms();h.control_enabled=False;h.advance(500)
        self.assertTrue(h.c.s.latched)
        self.assertLessEqual(h.first_stop_after(start)-start,380)
        self.assertTrue(any(kind=='idle' for t,kind,_ in h.sent if t>=start))

    def test_uart_blackout_actual_c_backstop(self):
        h=self.moving();start=h.ms();h.uart_enabled=False;h.advance(400)
        self.assertTrue(h.c.s.latched)
        self.assertLessEqual(h.first_stop_after(start)-start,240)

    def test_frozen_pl_sample_real_client_and_c_stop(self):
        h=self.moving();start=h.ms();h.pl.sampling=False;h.advance(400)
        self.assertTrue(h.c.s.latched)
        self.assertLessEqual(h.first_stop_after(start)-start,330)

    def test_ir_obstacle_is_visible_without_stopping_actual_c(self):
        h=self.moving();h.pl.ir=1;h.advance(250)
        self.assertFalse(h.c.s.latched)
        self.assertFalse(h.c.s.reason&2)
        self.assertEqual(h.c.s.ir,1)
        self.assertEqual(h.c.log[-1][3:5],(900,900))

    def test_ir_loss_does_not_stop_or_block_explicit_unlock(self):
        h=SupervisorCFixture();self.fixture=h;h.pl.ir=3;h.pl.ir_valid=False
        h.arm();h.drive(900,900);h.advance(250)
        self.assertFalse(h.c.s.latched)
        self.assertEqual(h.c.log[-1][3:5],(900,900))
        self.assertTrue(h.control.last['permit'])
        h.pl.valid=False;h.advance(250)
        self.assertTrue(h.c.s.latched)

    def test_mmio_failure_still_sends_stop_to_c(self):
        h=self.moving();start=h.ms();h.pl.error=True;h.advance(150)
        self.assertTrue(h.errors);self.assertTrue(h.c.s.latched)
        self.assertLessEqual(h.first_stop_after(start)-start,130)
        with self.assertRaises(OSError):h.control.stop()
        self.assertEqual(h.link._decide(h.clock())[0],'stop')

    def test_new_control_restart_cannot_replay_old_nonzero_request(self):
        h=self.moving();h.control.stop();h.advance(120)
        from control_supervisor import ControlSupervisor
        replacement=ControlSupervisor(h.client,h.link,clock=h.clock,motion_allowed=True)
        replacement.submit_intent(1,0,0);replacement.tick();h.advance(120)
        self.assertTrue(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(0,0))
        with self.assertRaises(PermissionError):replacement.submit_intent(2,900,900)

    def test_uint32_c_and_pl_wrap_preserve_hold_and_lease(self):
        h=self.moving(c_offset=0xFFFFFF00)
        self.assertFalse(h.c.s.latched)
        h.heartbeat=False;h.advance(400);self.assertTrue(h.c.s.latched)

    def test_reverse_requests_encode_nonforward_and_reach_actual_c(self):
        h=SupervisorCFixture();self.fixture=h;h.arm();h.drive(-700,-600)
        self.assertEqual(h.pl.command,2)
        self.assertEqual(h.c.log[-1][3:5],(-700,-600))

    def test_missing_unlock_ack_times_out_without_any_motion(self):
        h=SupervisorCFixture();self.fixture=h;h.advance(750)
        h.control.request_release();h.status_enabled=False;h.advance(800)
        self.assertEqual(h.control.last['phase'],'LOCKED')
        self.assertTrue(h.c.s.latched)
        self.assertTrue(all(not entry[2] for entry in h.c.log))
        with self.assertRaises(PermissionError):h.control.submit_intent(h.sequence+1,900,900)

    def test_frozen_car_feedback_stops_even_while_uart_tx_and_pl_are_healthy(self):
        h=self.moving();rx_ms=h.link.state_rx_time*1000;h.status_enabled=False;h.advance(900)
        self.assertTrue(h.c.s.latched)
        self.assertFalse(h.control.last['car_fresh'])
        self.assertLessEqual(h.first_stop_after(rx_ms+699)-rx_ms,830)


if __name__=='__main__':unittest.main()
