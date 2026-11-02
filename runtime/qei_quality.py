"""QEI quality checks and display-only smoothing; never modify raw samples.

An illegal edge makes distance unknowable. A computed/fresh velocity alone
does not restore trust. Counters are retained until explicit hardware rearm.
"""
from collections import deque
from dataclasses import dataclass

BENCH_FILTER_TICKS = 1000  # 10 us at 100 MHz; LAB candidate, motion pending.
MAX_AGE_TICKS = 20_000_000


def fault_reasons(info, odometry_fault, velocity_q16):
    reasons = []
    illegal = (info >> 4) & 255
    if illegal:
        reasons.append('illegal_transition')
    if illegal == 255:
        reasons.append('diagnostic_saturated')
    overrun = (info >> 12) & 255
    if overrun:
        reasons.append('velocity_overrun')
    if overrun == 255:
        reasons.append('overrun_diagnostic_saturated')
    if odometry_fault:
        reasons.append('odometry_fault')
    if velocity_q16 in (-0x80000000, 0x7fffffff):
        reasons.append('velocity_saturated')
    return tuple(reasons)


def snapshot_fault_reasons(shot, channel):
    return fault_reasons(getattr(shot, f'qei{channel}_info'),
                         getattr(shot, f'odometry{channel}').fault,
                         getattr(shot, f'qei{channel}_velocity_q16'))


def raw_fault_reasons(raw, channel):
    prefix = f'QEI{channel}_'
    velocity = raw[prefix+'VEL'] & 0xffffffff
    if velocity & 0x80000000:
        velocity -= 1 << 32
    return fault_reasons(raw[prefix+'INFO'],
                         bool(raw[f'ODOM{channel}_META'] & 0x40000000), velocity)


@dataclass(frozen=True)
class DisplaySpeed:
    value_q16: int | None
    source_timestamp: int | None
    latest_timestamp: int
    valid: bool
    reasons: tuple[str, ...]


class QeiDisplayFilter:
    """Median of three distinct clean batches, never a control input.

    Repeated host reads do not add observations or refresh sample timestamps.
    Invalid/stale/faulted input immediately clears history. The output carries
    the timestamp of the selected median, rather than pretending it is new.
    """
    def __init__(self):
        self._history = [deque(maxlen=3), deque(maxlen=3)]
        self._last = [None, None]
        self._epoch = [None, None]
        self._direction = [0, 0]

    def reset(self):
        self.__init__()

    def update(self, shot, now_ticks):
        results = []
        for channel in (0, 1):
            sample = getattr(shot, f'qei{channel}')
            odo = getattr(shot, f'odometry{channel}')
            history = self._history[channel]
            if self._epoch[channel] != odo.epoch:
                history.clear()
                self._last[channel] = None
                self._epoch[channel] = odo.epoch
                self._direction[channel] = 0
            reasons = list(snapshot_fault_reasons(shot, channel))
            if not sample.valid:
                reasons.append('invalid')
            elif (now_ticks - sample.timestamp) & 0xffffffff >= MAX_AGE_TICKS:
                reasons.append('stale')
            token = (sample.sequence, sample.timestamp)
            previous = self._last[channel]
            if not reasons and token != previous:
                if previous is not None and (not 0 < ((sample.sequence-previous[0]) & 0xffff) < 0x8000 or
                        not 0 < ((sample.timestamp-previous[1]) & 0xffffffff) < 0x80000000):
                    reasons.append('batch_identity_invalid')
                else:
                    value = getattr(shot, f'qei{channel}_velocity_q16')
                    direction = (value > 0) - (value < 0)
                    # Long unobserved gaps and a real reversal start a fresh
                    # display window. Never publish the old direction while
                    # the newest clean observation has the opposite sign.
                    if previous is not None and ((sample.timestamp-previous[1]) & 0xffffffff) >= MAX_AGE_TICKS:
                        history.clear()
                        self._direction[channel] = 0
                    if direction and self._direction[channel] and direction != self._direction[channel]:
                        history.clear()
                    if direction:
                        self._direction[channel] = direction
                    history.append((value, sample.timestamp))
                    self._last[channel] = token
            if reasons:
                history.clear()
                self._last[channel] = None
                self._direction[channel] = 0
                results.append(DisplaySpeed(None, None, sample.timestamp, False, tuple(reasons)))
                continue
            if len(history) < 3:
                results.append(DisplaySpeed(None, None, sample.timestamp, False, ('warming_up',)))
                continue
            selected = sorted(history, key=lambda entry: entry[0])[1]
            if (now_ticks-selected[1]) & 0xffffffff >= MAX_AGE_TICKS:
                results.append(DisplaySpeed(None, selected[1], sample.timestamp, False, ('filtered_sample_stale',)))
            else:
                results.append(DisplaySpeed(selected[0], selected[1], sample.timestamp, True, ()))
        return tuple(results)
