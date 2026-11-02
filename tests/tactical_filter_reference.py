"""Independent integer reference for the planned PL display-only filter.

Ticks are 100 MHz modulo 2**32; no output from this module controls motors.
"""
from collections import deque

MASK = (1 << 32) - 1
HALF = 1 << 31
MS = 100_000


def age(now, stamp):
    value = (now - stamp) & MASK
    return value if value < HALF else None


class TacticalFilter:
    def __init__(self):
        self.window = deque(maxlen=3)
        self.history = deque(maxlen=8)
        self.last_seq = None
        self.trend = 'unknown'
        self.pending = None
        self.pending_count = 0

    def clear(self):
        self.window.clear()
        self.history.clear()
        self.trend = 'unknown'
        self.pending = None
        self.pending_count = 0

    def observe(self, now):
        if self.window:
            latest = age(now, self.window[-1][1])
            oldest = age(now, self.window[0][1])
            if latest is None or oldest is None or latest >= 200 * MS or oldest >= 500 * MS:
                self.clear()
        return self.result()

    def result(self):
        ready = len(self.window) == 3
        return {'valid': ready, 'filtered_mm': sorted(x[0] for x in self.window)[1] if ready else None,
                'trend': self.trend, 'samples': len(self.window)}

    def accept(self, seq, stamp, mm, valid, now):
        if not 0 <= seq <= 65535 or not 0 <= mm <= 4095:
            raise ValueError('sample outside protocol range')
        self.observe(now)
        sample_age = age(now, stamp)
        if not valid or sample_age is None or sample_age >= 200 * MS:
            self.clear()
            return self.result()
        if self.last_seq is not None:
            delta = (seq - self.last_seq) & 65535
            if delta == 0:
                return self.result()
            if delta >= 32768:
                self.clear()
                return self.result()
        if self.window:
            interval = age(stamp, self.window[-1][1])
            if interval is None or not 20 * MS <= interval <= 200 * MS:
                self.clear()
        self.last_seq = seq
        self.window.append((mm, stamp))
        if len(self.window) < 3:
            return self.result()
        filtered = sorted(x[0] for x in self.window)[1]
        candidates = [(abs(dt - 500 * MS), -dt, d, dt) for d, t in self.history
                      if (dt := age(stamp, t)) is not None and 400 * MS <= dt <= 600 * MS]
        if candidates:
            _, _, previous, dt = min(candidates)
            change = previous - filtered
            magnitude = abs(change) * 100_000_000
            candidate = ('approaching' if change > 0 else 'receding') if magnitude >= 50 * dt else (
                'stable' if magnitude <= 20 * dt else None)
            if candidate is None:
                self.pending, self.pending_count = None, 0
            else:
                self.pending_count = self.pending_count + 1 if self.pending == candidate else 1
                self.pending = candidate
                if self.pending_count >= 2:
                    self.trend = candidate
        self.history.append((filtered, stamp))
        return self.result()
