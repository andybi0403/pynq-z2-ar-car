"""Normal operation must not be confused with fault injection or lease expiry."""
import unittest
from supervisor_c_fixture import SupervisorCFixture


class LongRunTests(unittest.TestCase):
    def test_sixty_seconds_zero_input_does_not_relatch_after_explicit_release(self):
        h=SupervisorCFixture();h.arm();h.advance(60_000)
        self.assertFalse(h.errors);self.assertFalse(h.rejected_intents)
        self.assertTrue(all(row['phase']=='ARMED' for row in h.control_log if row['host_monotonic_s']>=1.2))
        self.assertFalse(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(0,0))
    def test_sixty_seconds_continuous_new_intents_keep_actual_c_pwm(self):
        h=SupervisorCFixture(c_offset=0xfffff000);h.arm();h.drive(700,600);baseline=len(h.c.log);h.advance(60_000)
        self.assertFalse(h.errors);self.assertFalse(h.rejected_intents)
        self.assertTrue(all(row[2] and row[3:5]==(700,600) for row in h.c.log[baseline:]))
        self.assertFalse(h.c.s.latched);self.assertIsNone(h.control.last['stop_reason'])
    def test_fault_and_expiry_have_distinct_readable_reasons(self):
        h=SupervisorCFixture();h.arm();h.heartbeat=False;h.advance(400)
        self.assertEqual(h.control.last['stop_reason'],'intent_expired_or_missing')
        h=SupervisorCFixture();h.arm();h.status_enabled=False;h.advance(900)
        self.assertEqual(h.control.last['stop_reason'],'STM32_feedback_expired_or_missing')
        h=SupervisorCFixture();h.arm();h.pl.level=3;h.pl.reasons=1<<8;h.advance(40)
        self.assertEqual(h.control.last['stop_reason'],'PL_perception_denied')


if __name__=='__main__':unittest.main()
