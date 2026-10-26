"""Coordinate PL risk and the authoritative CarLink; never replace STM32.

    Only submit_intent renews the upstream 250 ms lease. Polling sensors,
    video, status and UART heartbeats cannot make an old intent new.
    Motion defaults disabled; simulation may enable it explicitly.
"""
import math
import threading
import time
from dataclasses import dataclass

try:
    from .perception_client import snapshot_to_link_sample, elapsed32
except ImportError:
    from perception_client import snapshot_to_link_sample, elapsed32


@dataclass(frozen=True)
class DriveIntent:
    sequence: int
    left: int
    right: int
    received_s: float


class ControlSupervisor:
    LEASE_S = 0.250
    SAFE_HOLD_S = 0.300
    CAR_MAX_AGE_S = 0.700  # $CAR is published every 300 ms.

    def __init__(self, client, link, *, clock=time.monotonic,
                 motion_allowed=False, yellow_pwm_limit=400):
        if type(yellow_pwm_limit) is not int or not 0 <= yellow_pwm_limit <= 2400:
            raise ValueError("yellow PWM limit must be in [0,2400]")
        self.client, self.link, self.clock = client, link, clock
        if hasattr(link, "CMD_MAX_AGE"):
            # A stalled supervisor must not leave the independent UART thread
            # refreshing a request for the legacy 500ms client timeout.
            link.CMD_MAX_AGE = min(link.CMD_MAX_AGE, self.LEASE_S)
        self.motion_allowed = bool(motion_allowed)
        self.yellow_pwm_limit = yellow_pwm_limit
        self._lock = threading.RLock()
        self._intent = None
        self._last_sequence = -1
        self._sent_sequence = -1
        self._pl_write_s = -math.inf
        self._phase = "LOCKED"
        self._safe_since = None
        self._release_requested_s = None
        self._release_state_seq = None
        self._fault_stop_sent = False
        self.last = None
        self.stop_reason = 'startup_locked'

    def submit_intent(self, sequence, left, right):
        """Accept monotonically numbered *new* requests, including zero.

        A mixed-sign turn is conservative: any positive wheel requests
        forward clearance. PL may reject the negative wheel direction;
        unsupported manoeuvres never bypass its direction safety check.
        """
        with self._lock:
            for value in (sequence, left, right):
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError("intent fields must be integers")
            if sequence <= self._last_sequence:
                raise ValueError("replayed or out-of-order intent")
            if not all(-2400 <= v <= 2400 for v in (left, right)):
                raise ValueError("PWM outside [-2400,2400]")
            if not self.motion_allowed and (left or right):
                raise PermissionError("this session permits zero commands only")
            if self._phase != "ARMED" and (left or right):
                raise PermissionError("explicit release and fresh unlocked status required")
            now = self.clock()
            if not math.isfinite(now):
                raise ValueError("invalid clock")
            self._last_sequence = sequence
            self._intent = DriveIntent(sequence, left, right, now)

    def _stop(self, reason='safety_guard'):
        self.stop_reason = reason
        self._phase = "LOCKED"
        self._safe_since = None
        self._release_requested_s = None
        if not self._fault_stop_sent:
            self.link.stop_request()
            self._fault_stop_sent = True

    def stop(self):
        """Explicit STOP discards every cached motion request."""
        with self._lock:
            self._intent = None
            try:
                self.client.set_command(forward=False, valid=False)
            finally:
                self._fault_stop_sent = False
                self._stop('operator_stop')

    def request_release(self):
        with self._lock:
            now = self.clock()
            if not self.motion_allowed:
                raise PermissionError("LAB_ONLY cannot send PREL")
            if not math.isfinite(now):
                raise PermissionError("release requires a valid monotonic clock")
            if (self._phase != "LOCKED" or self._safe_since is None
                    or now - self._safe_since < self.SAFE_HOLD_S
                    or self.last is None or not self.last["safe_hold"]
                    or not 0 <= now - self.last["host_monotonic_s"] < 0.100
                    or self._intent is None
                    or not 0 <= now - self._intent.received_s < self.LEASE_S):
                raise PermissionError("fresh valid zero-speed safe hold of 300ms required")
            self.link.release_request()
            self._phase = "WAIT_UNLOCK"
            self._release_requested_s = now
            self._release_state_seq = self.link.state_seq
            # Requests from before release can never drive afterwards.
            self._sent_sequence = self._intent.sequence

    def tick(self):
        with self._lock:
            now = self.clock()
            intent = self._intent
            fresh = (intent is not None and math.isfinite(now)
                     and 0 <= now - intent.received_s < self.LEASE_S)
            forward = bool(fresh and (intent.left > 0 or intent.right > 0))
            # Lease maintenance is bounded by the original request lifetime.
            # No renewal after expiry, even if samples continue to arrive.
            try:
                if getattr(self.link, "transport_error", None) is not None:
                    raise RuntimeError("UART transport failed: " + self.link.transport_error)
                if not fresh or now - self._pl_write_s >= 0.100 \
                        or intent.sequence != self._sent_sequence:
                    self.client.set_command(forward=forward, valid=fresh)
                    self._pl_write_s = now
                ticks, shot, decision = self.client.sample_and_decide()
                sample = snapshot_to_link_sample(shot, ticks)
                # Translate age only as a duration in the PL clock domain.
                sample_s = now - elapsed32(ticks, shot.ultrasonic.timestamp) / 100_000_000
                self.link.update_sample(sample.valid, sample.distance_mm,
                                        sample.infrared_mask, sample_s)
                if hasattr(self.link, "status_snapshot"):
                    car, car_sequence, car_time = self.link.status_snapshot()
                else:
                    car, car_sequence, car_time = (self.link.state, self.link.state_seq,
                                                    self.link.state_rx_time)
                car_fresh = (car is not None and car_time is not None
                             and 0 <= now - car_time < self.CAR_MAX_AGE_S)
                command_matches = (shot.command_state & 3) == (int(forward) | (int(fresh) << 1))
                # Do not act on a green result evaluated before this command.
                risk_caught_up = elapsed32(shot.risk.timestamp, shot.command_timestamp) < 0x80000000
                allowed = fresh and decision.permit and command_matches and risk_caught_up
                safe_hold = bool(allowed and intent.left == 0 and intent.right == 0
                                 and sample.distance_mm >= 250
                                 and shot.qei0_velocity_q16 == 0
                                 and shot.qei1_velocity_q16 == 0
                                 and car_fresh and car["left"] == 0 and car["right"] == 0
                                 and car.get("mm", 0) >= 250)
                if allowed and car_fresh:
                    self._fault_stop_sent = False
                if not allowed or not car_fresh:
                    reason = ('intent_expired_or_missing' if not fresh else
                              'PL_command_not_matched' if not command_matches else
                              'PL_risk_not_caught_up' if not risk_caught_up else
                              'PL_perception_denied' if not decision.permit else
                              'STM32_feedback_expired_or_missing')
                    self._stop(reason)
                elif self._phase == "WAIT_UNLOCK":
                    if (car_sequence != self._release_state_seq
                            and car["lock"] == 0 and safe_hold):
                        self._phase = "ARMED"
                        self.stop_reason = None
                    elif now - self._release_requested_s >= self.CAR_MAX_AGE_S:
                        self._stop('STM32_unlock_ack_timeout')
                elif self._phase == "ARMED" and car["lock"]:
                    self._stop('STM32_latched')

                if self._phase == "LOCKED":
                    if safe_hold and car["lock"] == 1:
                        if self._safe_since is None:
                            self._safe_since = now
                    else:
                        self._safe_since = None

                outputs = (0, 0)
                level = (shot.risk_state >> 1) & 3
                if allowed and self._phase == "ARMED" and intent is not None:
                    outputs = (intent.left, intent.right)
                    if level == 1:
                        limit = self.yellow_pwm_limit
                        outputs = tuple(max(-limit, min(limit, v)) for v in outputs)
                    if intent.sequence == self._sent_sequence:
                        # Removing a warning cannot restore an old high PWM.
                        previous = getattr(self, "_last_outputs", (0, 0))
                        outputs = tuple((1 if v >= 0 else -1) * min(abs(v), abs(old))
                                        if v * old >= 0 else 0
                                        for v, old in zip(outputs, previous))
                # Only newly received requests enter CarLink's request API.
                # Risk limiting updates may retract a request without renewal.
                if fresh and intent.sequence != self._sent_sequence:
                    self.link.update_command(*outputs)
                    self._sent_sequence = intent.sequence
                elif outputs != getattr(self, "_last_outputs", (0, 0)):
                    self.link.limit_command(*outputs)
                self._last_outputs = outputs
                self.last = {
                    "host_monotonic_s": now, "pl_ticks": ticks,
                    "epoch": shot.epoch, "phase": self._phase,
                    "intent_fresh": fresh, "permit": bool(allowed),
                    "safe_hold": safe_hold, "risk_level": level,
                    "risk_reasons": (shot.risk_state >> 16) & 0xffff,
                    "decision_reasons": list(decision.reasons),
                    "requested_pwm": [intent.left, intent.right] if intent else [0, 0],
                    "output_pwm": list(outputs), "car_fresh": car_fresh,
                    "car": dict(car) if car_fresh else None,
                    "stop_reason": self.stop_reason if self._phase == 'LOCKED' else None,
                    "command_matches": command_matches, "risk_caught_up": risk_caught_up,
                }
                return ticks, shot, self.last
            except Exception as exc:
                self._intent = None
                try:
                    self.client.set_command(forward=False, valid=False)
                finally:
                    self._stop('control_exception: '+type(exc).__name__+': '+str(exc))
                raise
