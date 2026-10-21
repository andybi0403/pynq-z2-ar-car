import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "host"))
sys.path.insert(0, str(PROJECT.parent / "stm32预备程序" / "pc"))
from control_supervisor import ControlSupervisor
from perception_client import Sample
from pynq_link import CarLink, MockSerial, parse_car


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.now = 1.0
        self.level = 0
        self.error = False
        self.mm = 1000
        self.calls = []
        owner = self
        class Client:
            state = 0
            command_ts = 100_000_000
            def set_command(inner, *, forward, valid):
                inner.state = int(forward) | (int(valid) << 1)
                inner.command_ts = int(owner.now * 100_000_000)
                owner.calls.append((owner.now, forward, valid))
            def sample_and_decide(inner):
                if owner.error:
                    raise RuntimeError("MMIO disconnected")
                ticks = int(owner.now * 100_000_000)
                s = Sample(0, ticks, True, 1)
                shot = SimpleNamespace(
                    epoch=1, ultrasonic=Sample(owner.mm, ticks, True, 1),
                    infrared=Sample(4, ticks, True, 1),
                    qei0_velocity_q16=0, qei1_velocity_q16=0,
                    risk_state=owner.level << 1, risk=s,
                    command_state=inner.state, command_timestamp=inner.command_ts,
                )
                return ticks, shot, SimpleNamespace(permit=inner.state & 2 != 0,
                                                    reasons=())
        self.client = Client()
        self.link = CarLink("unused", ser=MockSerial(), clock_fn=lambda: self.now)
        self.link.state = {"left": 0, "right": 0, "lock": 1, "fault": 1, "mm":1000, "ir":0}
        self.link.state_rx_time = self.now
        self.link.state_seq = 1
        self.control = ControlSupervisor(self.client, self.link,
                                        clock=lambda: self.now, motion_allowed=True)
        self.seq = 0

    def heartbeat(self, left=0, right=0):
        self.seq += 1
        self.link.state_rx_time = self.now
        self.control.submit_intent(self.seq, left, right)
        return self.control.tick()[2]

    def arm(self):
        self.heartbeat()
        for _ in range(4):
            self.now += 0.1
            self.heartbeat()
        self.control.request_release()
        kind, _ = self.link._decide(self.now)
        self.assertEqual(kind, "rel")
        self.link.state_seq += 1
        self.link.state["lock"] = 0
        self.link.state_rx_time = self.now
        self.assertEqual(self.control.tick()[2]["phase"], "ARMED")

    def test_release_requires_real_safe_hold_and_new_motion(self):
        with self.assertRaises(PermissionError):
            self.control.submit_intent(1, 100, 100)
        self.heartbeat()
        with self.assertRaises(PermissionError):
            self.control.request_release()
        self.arm()
        self.assertEqual(self.link._cmd[:2], (0, 0))
        result = self.heartbeat(600, 600)
        self.assertEqual(result["output_pwm"], [600, 600])

    def test_sensor_poll_does_not_renew_request(self):
        self.arm()
        self.heartbeat(600, 600)
        command_time = self.link._cmd_ms
        self.now += 0.2
        self.control.tick()
        self.assertEqual(self.link._cmd_ms, command_time)
        self.now += 0.050001
        result = self.control.tick()[2]
        self.assertFalse(result["intent_fresh"])
        self.assertEqual(result["output_pwm"], [0, 0])
        self.assertFalse(self.calls[-1][2])
        self.assertEqual(self.link._decide(self.now)[0], "stop")

    def test_stalled_supervisor_uart_thread_revokes_at_250ms(self):
        self.arm()
        self.heartbeat(600, 600)
        self.assertEqual(self.link._decide(self.now)[0], "drive")
        self.now += .250001
        self.assertEqual(self.link._decide(self.now)[0], "idle")

    def test_release_rejects_old_poll_even_with_new_zero_intent(self):
        self.heartbeat()
        for _ in range(4):
            self.now += .1
            self.heartbeat()
        self.now += .15
        self.seq += 1
        self.control.submit_intent(self.seq, 0, 0)
        with self.assertRaises(PermissionError):
            self.control.request_release()

    def test_yellow_reduction_never_restores_old_pwm(self):
        self.arm()
        self.heartbeat(900, 900)
        command_time = self.link._cmd_ms
        self.level = 1
        self.now += 0.01
        self.assertEqual(self.control.tick()[2]["output_pwm"], [400, 400])
        self.assertEqual(self.link._cmd_ms, command_time)
        self.level = 0
        self.now += 0.01
        self.assertEqual(self.control.tick()[2]["output_pwm"], [400, 400])
        self.assertEqual(self.heartbeat(900, 900)["output_pwm"], [900, 900])

    def test_no_prel_or_motion_in_lab_mode(self):
        self.control.motion_allowed = False
        with self.assertRaises(PermissionError):
            self.control.submit_intent(1, 1, 1)
        with self.assertRaises(PermissionError):
            self.control.request_release()

    def test_old_intent_and_stale_car_rejected(self):
        self.arm()
        self.heartbeat(600, 600)
        with self.assertRaises(ValueError):
            self.control.submit_intent(self.seq, 600, 600)
        self.link.state_rx_time = self.now - 0.701
        self.assertEqual(self.control.tick()[2]["phase"], "LOCKED")

    def test_mmio_failure_invalidates_pl_and_requests_stop(self):
        self.arm()
        self.heartbeat(600, 600)
        self.error = True
        with self.assertRaises(RuntimeError):
            self.control.tick()
        self.assertFalse(self.calls[-1][2])
        self.assertEqual(self.link._decide(self.now)[0], "stop")

    def test_limit_api_cannot_renew_or_increase(self):
        self.link.update_command(600, -600)
        initial = self.link._cmd_ms
        self.now += 0.1
        self.link.limit_command(300, -200)
        self.assertEqual(self.link._cmd_ms, initial)
        with self.assertRaises(ValueError): self.link.limit_command(400, -200)
        with self.assertRaises(ValueError): self.link.limit_command(-100, -100)

    def test_corrupt_status_cannot_claim_unlocked_state(self):
        for frame in (b'$CAR,0,0,2,0,1000,0,0#',
                      b'$CAR,0,0,0,-1,1000,0,0#',
                      b'$CAR,0,0,0,0,1000,4,0#',
                      b'$CAR,0,0,0,0,1000,0,-1#',
                      b'$CAR,0,0,0,0,1000,0,\xff0#'):
            self.assertIsNone(parse_car(frame), frame)
        self.assertIsNotNone(parse_car(b'$CAR,-2400,2400,1,65535,9999,3,4294967295#'))

    def test_missing_c_side_safe_distance_cannot_start_release_hold(self):
        self.link.state['mm']=0
        self.heartbeat()
        for _ in range(4):self.now+=.1;self.heartbeat()
        with self.assertRaises(PermissionError):self.control.request_release()

    def test_explicit_stop_requests_uart_even_if_mmio_write_fails(self):
        self.arm()
        def broken(**kwargs):raise OSError('MMIO unavailable')
        self.client.set_command=broken
        with self.assertRaises(OSError):self.control.stop()
        self.assertEqual(self.link._decide(self.now)[0],'stop')

    def test_uart_failure_revokes_permission_immediately(self):
        self.arm();self.heartbeat(600,600)
        self.link.transport_error='write timeout'
        with self.assertRaisesRegex(RuntimeError,'UART transport'):
            self.control.tick()
        self.assertEqual(self.link._decide(self.now)[0],'stop')

    def test_bad_clock_cannot_release(self):
        self.heartbeat()
        for _ in range(4):self.now+=.1;self.heartbeat()
        self.now=float('nan')
        with self.assertRaises(PermissionError):self.control.request_release()


if __name__ == "__main__":
    unittest.main()
