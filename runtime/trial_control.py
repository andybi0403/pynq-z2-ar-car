"""Explicit, limited ground-trial policy. This is not a release approval.

Direct manual driving uses the UART lease and STM32 latch; PL remains telemetry.
There are no nominal calibration defaults and no automatic release/re-arm.
"""
import threading
import time

from wireless_core import ControlGate, IntentMailbox
from control_supervisor import ControlSupervisor

PWM_LIMIT = 2400
MAX_BURST_S = 0.0  # Hold-to-drive; independent intent/MCU leases remain bounded.
DRIVE_LEASE_MS = 500
PACKET_MAX_AGE_MS = 200
SYNC_RTT_MS = 200


class DirectManualControl(ControlSupervisor):
    """Dedicated UART control worker. No MMIO, video or journal operations.

    STM32's flashed 250 mm local obstacle guard remains authoritative. Fresh
    intent, actual feedback and explicit release are required independently.
    """
    LEASE_S = DRIVE_LEASE_MS / 1000

    def __init__(self, link, *, clock=time.monotonic, motion_allowed=False):
        super().__init__(None, link, clock=clock, motion_allowed=motion_allowed,
                         yellow_pwm_limit=PWM_LIMIT)
        self.link.CMD_MAX_AGE = self.LEASE_S

    def stop(self):
        with self._lock:
            self._intent = None
            self._fault_stop_sent = False
            self._stop('operator_stop')

    def request_release(self):
        with self._lock:
            now = self.clock()
            if (not self.motion_allowed or self._phase != 'LOCKED'
                    or self._safe_since is None or now-self._safe_since < self.SAFE_HOLD_S
                    or not self.last or not self.last['safe_hold']
                    or not 0 <= now-self.last['host_monotonic_s'] < .200
                    or self._intent is None or not 0 <= now-self._intent.received_s < self.LEASE_S):
                raise PermissionError('请保持零输出，等待实际回包和 300ms 安全保持')
            self.link.release_request()
            self._phase = 'WAIT_UNLOCK'
            self._release_requested_s = now
            self._release_state_seq = self.link.state_seq
            self._sent_sequence = self._intent.sequence

    def snapshot(self):
        with self._lock:
            value = dict(self.last or {})
            value['phase'] = self._phase
            value['stop_reason'] = self.stop_reason if self._phase == 'LOCKED' else None
            value['release_ready'] = bool(self.motion_allowed and self._phase == 'LOCKED'
                and self._safe_since is not None and self.clock()-self._safe_since >= self.SAFE_HOLD_S
                and value.get('safe_hold'))
            return value

    def tick(self):
        with self._lock:
            car, sequence, received = self.link.status_snapshot()
            # RX may publish while status_snapshot waits for its lock. Compare
            # the returned batch with a time read AFTER acquiring that batch.
            now = self.clock();intent = self._intent
            fresh = intent is not None and 0 <= now-intent.received_s < self.LEASE_S
            car_fresh = car is not None and received is not None and 0 <= now-received < self.CAR_MAX_AGE_S
            sensor = self.link.sensor_snapshot(now)
            valid = bool(sensor and sensor.get('us_valid'))
            mm = int(sensor.get('mm', 0)) if sensor else 0
            ir = int(sensor.get('ir', 0)) if sensor else 0
            stamp = sensor.get('us_sample_s', now) if sensor else now
            self.link.update_sample(valid, mm, ir, stamp)
            self.link.update_control_observation(now)
            near = bool((car_fresh and car.get('fault', 0) & 4) or (valid and mm <= 250))
            forward = bool(fresh and (intent.left > 0 or intent.right > 0))
            transport = getattr(self.link, 'transport_error', None)
            allowed = bool(fresh and car_fresh and not transport and not (near and forward))
            safe_hold = bool(allowed and intent.left == intent.right == 0 and not near
                             and car['left'] == car['right'] == 0)
            if allowed:self._fault_stop_sent = False
            if not allowed:
                reason = ('UART_transport_failed' if transport else
                          'intent_expired_or_missing' if not fresh else
                          'STM32_feedback_expired_or_missing' if not car_fresh else
                          'front_obstacle_250mm')
                self._stop(reason)
            elif self._phase == 'WAIT_UNLOCK':
                if sequence != self._release_state_seq and car['lock'] == 0 and safe_hold:
                    self._phase = 'ARMED';self.stop_reason = None
                elif now-self._release_requested_s >= self.CAR_MAX_AGE_S:
                    self._stop('STM32_unlock_ack_timeout')
            elif self._phase == 'ARMED' and car['lock']:
                self._stop('STM32_latched')
            if self._phase == 'LOCKED':
                if safe_hold and car['lock'] == 1:
                    if self._safe_since is None:self._safe_since = now
                else:self._safe_since = None
            outputs = (intent.left, intent.right) if allowed and self._phase == 'ARMED' else (0, 0)
            if fresh and intent.sequence != self._sent_sequence:
                self.link.update_command(*outputs);self._sent_sequence = intent.sequence
            elif outputs != getattr(self, '_last_outputs', (0, 0)):
                self.link.limit_command(*outputs)
            self._last_outputs = outputs
            self.last = {'host_monotonic_s':now,'phase':self._phase,'intent_fresh':fresh,
                'permit':allowed,'safe_hold':safe_hold,'risk_level':2 if near else 0 if valid else 1,
                'risk_reasons':4 if near else 0,'decision_reasons':[] if allowed else [self.stop_reason],
                'requested_pwm':[intent.left,intent.right] if intent else [0,0],
                'output_pwm':list(outputs),'car_fresh':car_fresh,'car':dict(car) if car_fresh else None,
                'car_received_s':received,'car_sequence':sequence,'stop_reason':self.stop_reason,
                'command_matches':None,'risk_caught_up':None,'pl_guard_applied':False,'control_mode':'direct_manual',
                'obstacle_blocked':near}
            return self.snapshot()


class TrialMailbox(IntentMailbox):
    def __init__(self,clock=time.monotonic):
        super().__init__(clock=clock,packet_max_age_ms=PACKET_MAX_AGE_MS)

    def request_release(self, age_upper_ms=0):
        with self.lock:
            now = self.clock()
            self.sequence += 1
            self.pending = None
            self.pending_release = (self.sequence, 0, 0, now, now + (self.packet_max_age_ms-age_upper_ms)/1000)

    def stop(self):
        with self.lock:
            self.pending = None
            self.stop_pending = True
            self.pending_release = None

    def consume(self):
        with self.lock:
            if self.stop_pending:
                self.stop_pending = False
                self.pending = None
                self.pending_release = None
                return 'stop', None
            release = getattr(self, 'pending_release', None)
            self.pending_release = None
            if release is not None:
                # Later heartbeats cannot renew the explicit release deadline.
                # Discard pre-release motion, even if it arrived in this tick.
                self.pending = None
                if self.clock() >= release[4]:
                    return 'stop', None
                return 'release', release[:3]
            value = self.pending
            self.pending = None
            if value is None:
                return None, None
            if self.clock() >= value[4]:
                return None, None  # Discard a delayed packet; original intent lease still expires.
            return 'intent', value[:3]


class TrialGate(ControlGate):
    def __init__(self, mailbox, **kwargs):
        super().__init__(mailbox, motion_allowed=True, packet_max_age_ms=PACKET_MAX_AGE_MS, sync_rtt_ms=SYNC_RTT_MS, intent_lease_ms=DRIVE_LEASE_MS, tolerate_timing_jitter=True, **kwargs)

    def message(self, key, payload):
        with self.lock:
            if isinstance(payload, dict) and payload.get('type') in ('intent', 'release'):
                for name in ('left', 'right'):
                    value = payload.get(name, 0 if payload['type'] == 'release' else None)
                    if type(value) is not int or abs(value) > PWM_LIMIT:
                        if self.owner == key:
                            self.revoke('trial_PWM_limit')
                        raise ValueError('驾驶 PWM 上限为 2400')
                if payload['type'] == 'release':
                    if payload.get('left', 0) or payload.get('right', 0):
                        self.revoke('nonzero_release')
                        raise ValueError('解锁请求必须为零输出')
                    # Reuse all production owner, sequence, age and sync checks.
                    reply = super().message(key, {**payload, 'type': 'intent', 'left': 0, 'right': 0})
                    if reply.get('type') != 'ack':return reply
                    sync = self.sessions[key]['sync']
                    age = self.clock()*1000 - (payload['client_ms'] + sync[0])
                    self.mailbox.request_release(max(0, age+sync[1]))
                    return {**reply, 'release_queued': True}
            return super().message(key, payload)


class TrialOwner:
    """Called by the control worker, never by a web handler."""
    def __init__(self, control, mailbox, *, clock=time.monotonic):
        self.control, self.mailbox, self.clock = control, mailbox, clock
        self.lock = threading.Lock()
        self.error = None
        self.burst_since = None
        self.fault = None
        self.jitter_count = 0

    def stop(self, reason):
        self.control.stop()
        self.mailbox.stop()
        self.error = reason
        self.burst_since = None

    def step(self, lag_s=0):
        if lag_s >= .200:
            self.stop('控制调度中断，已停车；恢复后可手动解锁')
        elif lag_s > .100:
            self.jitter_count += 1
        if self.fault:
            self.mailbox.stop()
        kind, intent = self.mailbox.consume()
        try:
            if kind == 'stop':
                self.control.stop()
                self.burst_since = None
            elif kind in ('intent', 'release'):
                if any(abs(v) > PWM_LIMIT for v in intent[1:]):
                    raise ValueError('试跑 PWM 超限')
                moving = bool(intent[1] or intent[2])
                if moving:
                    if self.burst_since is None:
                        self.burst_since = self.clock()
                    elif MAX_BURST_S and self.clock() - self.burst_since >= MAX_BURST_S:
                        raise PermissionError('连续驾驶已达 30 秒，请松开并重新解锁')
                else:
                    self.burst_since = None
                self.control.submit_intent(*intent)
                if kind == 'release':
                    self.control.request_release()
                    self.error = None
        except (ValueError, PermissionError) as exc:
            self.stop(str(exc))
        # The burst deadline is independent of new messages.
        if MAX_BURST_S and self.burst_since is not None and self.clock()-self.burst_since >= MAX_BURST_S:
            self.stop('连续驾驶已达 30 秒，请松开并重新解锁')
        before = self.clock()
        result = self.control.tick()
        elapsed = self.clock()-before
        if elapsed >= .200:
            self.stop('控制采样中断，已停车；恢复后可手动解锁')
        elif elapsed > .100:
            self.jitter_count += 1
        return result
