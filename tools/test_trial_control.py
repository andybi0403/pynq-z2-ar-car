"""Trial-specific bounds and revocation tests, no hardware or motor output."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'pynq_fpga/preintegration/host'))
from trial_control import TrialGate, TrialMailbox, TrialOwner


class Clock:
    value = 10.0
    def __call__(self):
        return self.value


class Policy:
    def __init__(self, clock):
        self.clock = clock
        self.intents = []
        self.stops = 0
        self.releases = 0
        self.permit_release = False
        self.tick_duration = 0
    def stop(self):
        self.stops += 1
    def submit_intent(self, *intent):
        self.intents.append(intent)
    def request_release(self):
        if not self.permit_release:
            raise PermissionError('actual PL hold denied')
        self.releases += 1
    def tick(self):
        self.clock.value += self.tick_duration
        return 1, None, {}


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.box = TrialMailbox(self.clock)
        self.gate = TrialGate(self.box, clock=self.clock)
        self.gate.connect('one')
        challenge = self.gate.challenge('one')
        self.gate.message('one', {'type':'sync', 'nonce':challenge['nonce'], 'received_ms':10000, 'sent_ms':10000})
        self.gate.message('one', {'type':'claim', 'client_ms':10000})
        self.box.consume()  # Claim deliberately queues STOP.
        self.policy = Policy(self.clock)
        self.owner = TrialOwner(self.policy, self.box, clock=self.clock)

    def packet(self, kind='intent', seq=1, **fields):
        return {'type':kind, 'seq':seq, 'client_ms':self.clock()*1000, 'left':0, 'right':0, **fields}

    def test_pwm_excess_revokes_and_clears_pending(self):
        self.gate.message('one', self.packet(left=400))
        with self.assertRaises(ValueError):
            self.gate.message('one', self.packet(seq=2, left=401))
        self.assertIsNone(self.gate.owner)
        self.assertEqual(self.box.consume()[0], 'stop')

    def test_release_does_not_bypass_actual_supervisor(self):
        self.gate.message('one', self.packet('release'))
        self.owner.step()
        self.assertEqual(self.policy.releases, 0)
        self.assertGreater(self.policy.stops, 0)
        self.assertIn('actual PL hold denied', self.owner.error)

    def test_release_requires_fresh_owned_ordered_packet(self):
        self.gate.message('one', self.packet('release'))
        self.assertEqual(self.box.consume()[0], 'release')
        with self.assertRaises(ValueError):
            self.gate.message('one', self.packet('release'))
        self.assertEqual(self.box.consume()[0], 'stop')

    def test_expired_release_and_stop_cannot_unlock(self):
        self.gate.message('one', self.packet('release'))
        self.clock.value += .101
        self.assertEqual(self.box.consume()[0], 'stop')
        self.box.request_release()
        self.box.stop()
        self.assertEqual(self.box.consume()[0], 'stop')
        self.assertIsNone(self.box.consume()[0])

    def test_motion_cannot_be_attached_to_release(self):
        with self.assertRaises(ValueError):
            self.gate.message('one', self.packet('release', left=400))
        self.assertEqual(self.box.consume()[0], 'stop')

    def test_disconnect_drops_release(self):
        self.gate.message('one', self.packet('release'))
        self.gate.disconnect('one')
        self.owner.step()
        self.assertEqual(self.policy.releases, 0)

    def test_heartbeat_cannot_lose_or_renew_explicit_release(self):
        self.box.request_release()
        self.box.submit(0, 0)
        self.assertEqual(self.box.consume()[0], 'release')
        self.box.request_release()
        self.clock.value += .101
        self.box.submit(0, 0)
        self.assertEqual(self.box.consume()[0], 'stop')

    def test_burst_limit_is_not_extended_by_heartbeat(self):
        for _ in range(22):
            self.box.submit(400, 400)
            self.owner.step()
            self.clock.value += .05
        self.assertIn('1 秒', self.owner.error)
        self.assertGreater(self.policy.stops, 0)

    def test_burst_limit_without_another_packet(self):
        self.box.submit(400, 400)
        self.owner.step()
        self.clock.value += 1.01
        self.owner.step()
        self.assertGreater(self.policy.stops, 0)

    def test_scheduler_fault_latches_until_restart(self):
        self.owner.step(.101)
        self.box.request_release()
        self.policy.permit_release = True
        self.owner.step()
        self.assertTrue(self.owner.fault)
        self.assertEqual(self.policy.releases, 0)

    def test_slow_sampling_latches_fault(self):
        self.policy.tick_duration = .101
        self.owner.step()
        self.assertTrue(self.owner.fault)
        self.assertGreater(self.policy.stops, 0)


if __name__ == '__main__':
    unittest.main()
