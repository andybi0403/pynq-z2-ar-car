"""Explicit, limited ground-trial policy. This is not a release approval.

The existing PL decision, UART lease and STM32 latch remain authoritative.
There are no nominal calibration defaults and no automatic release/re-arm.
"""
import threading
import time

from wireless_core import ControlGate, IntentMailbox

PWM_LIMIT = 400
MAX_BURST_S = 1.0


class TrialMailbox(IntentMailbox):
    def request_release(self, age_upper_ms=0):
        with self.lock:
            now = self.clock()
            self.sequence += 1
            self.pending = None
            self.pending_release = (self.sequence, 0, 0, now, now + (100-age_upper_ms)/1000)

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
                return 'stop', None
            return 'intent', value[:3]


class TrialGate(ControlGate):
    def __init__(self, mailbox, **kwargs):
        super().__init__(mailbox, motion_allowed=True, **kwargs)

    def message(self, key, payload):
        with self.lock:
            if isinstance(payload, dict) and payload.get('type') in ('intent', 'release'):
                for name in ('left', 'right'):
                    value = payload.get(name, 0 if payload['type'] == 'release' else None)
                    if type(value) is not int or abs(value) > PWM_LIMIT:
                        if self.owner == key:
                            self.revoke('trial_PWM_limit')
                        raise ValueError('试跑 PWM 上限为 400')
                if payload['type'] == 'release':
                    if payload.get('left', 0) or payload.get('right', 0):
                        self.revoke('nonzero_release')
                        raise ValueError('解锁请求必须为零输出')
                    # Reuse all production owner, sequence, age and sync checks.
                    reply = super().message(key, {**payload, 'type': 'intent', 'left': 0, 'right': 0})
                    sync = self.sessions[key]['sync']
                    age = self.clock()*1000 - (payload['client_ms'] + sync[0])
                    self.mailbox.request_release(max(0, age+sync[1]))
                    return {**reply, 'release_queued': True}
            return super().message(key, payload)


class TrialOwner:
    """Called only by the MMIO owner, never by a web handler."""
    def __init__(self, control, mailbox, *, clock=time.monotonic):
        self.control, self.mailbox, self.clock = control, mailbox, clock
        self.lock = threading.Lock()
        self.error = None
        self.burst_since = None
        self.fault = None

    def stop(self, reason):
        self.control.stop()
        self.mailbox.stop()
        self.error = reason
        self.burst_since = None

    def step(self, lag_s=0):
        if lag_s > .100:
            self.fault = '控制调度延迟超过 100ms；请重启试跑服务'
            self.stop(self.fault)
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
                    elif self.clock() - self.burst_since >= MAX_BURST_S:
                        raise PermissionError('单次试跑已达 1 秒，请松开并重新解锁')
                else:
                    self.burst_since = None
                self.control.submit_intent(*intent)
                if kind == 'release':
                    self.control.request_release()
                    self.error = None
        except (ValueError, PermissionError) as exc:
            self.stop(str(exc))
        # The burst deadline is independent of new messages.
        if self.burst_since is not None and self.clock()-self.burst_since >= MAX_BURST_S:
            self.stop('单次试跑已达 1 秒，请松开并重新解锁')
        before = self.clock()
        result = self.control.tick()
        if self.clock()-before > .100:
            self.fault = '控制采样耗时超过 100ms；请重启试跑服务'
            self.stop(self.fault)
        return result
