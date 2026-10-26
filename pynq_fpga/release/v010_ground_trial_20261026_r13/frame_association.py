"""Associate decoded-frame reception with prior PL snapshots, honestly.

    Timestamps describe host reception, NOT camera exposure or screen scanout.
    A bracketed atomic PL read establishes a clock anchor; PS and PL absolute
    timestamps are never directly subtracted. Future snapshots are excluded.
"""
from collections import deque
import threading
import math


class FrameAssociator:
    def __init__(self, max_age_ms=200, history=128):
        if not math.isfinite(max_age_ms) or max_age_ms <= 0 or history < 2:
            raise ValueError("positive max age and at least two history entries required")
        self.max_age_ns = int(max_age_ms * 1_000_000)
        self.history = deque(maxlen=history)
        self.lock = threading.RLock()

    def publish(self, *, host_before_ns, host_after_ns, pl_ticks64,
                registers, epoch):
        if not 0 <= host_before_ns <= host_after_ns or not 0 <= pl_ticks64 < 1 << 64:
            raise ValueError("invalid clock bracket")
        with self.lock:
            if self.history and host_before_ns < self.history[-1]["host_after_ns"]:
                raise ValueError("clock brackets must be ordered and non-overlapping")
            item = {"host_before_ns": host_before_ns, "host_after_ns": host_after_ns,
                    "host_anchor_ns": (host_before_ns + host_after_ns) // 2,
                    "anchor_uncertainty_ns": (host_after_ns - host_before_ns + 1) // 2,
                    "pl_ticks64": pl_ticks64, "epoch": epoch,
                    "registers": dict(registers)}
            self.history.append(item)
            return item

    def associate(self, frame_id, received_ns, submitted_ns=None):
        if frame_id < 0 or received_ns < 0:
            raise ValueError("invalid frame identifier or time")
        if submitted_ns is not None and submitted_ns < received_ns:
            raise ValueError("frame submission precedes reception")
        result = {"schema": "car-frame-association/v1", "frame_id": frame_id,
                  "received_host_ns": received_ns, "submitted_host_ns": submitted_ns,
                  "receive_to_submit_ms": None if submitted_ns is None else
                      (submitted_ns - received_ns) / 1_000_000,
                  "timestamp_scope": "decoded_frame_reception_not_exposure_or_scanout",
                  "valid": False}
        with self.lock:
            # Brackets are ordered at publish time. Most frames use the most
            # recent bracket; stop there without allocating/filtering history.
            anchor = next((a for a in reversed(self.history)
                           if a["host_after_ns"] <= received_ns), None)
            if anchor is None:
                result["reason"] = "no_prior_snapshot"
                return result
        elapsed_ns = received_ns - anchor["host_anchor_ns"]
        result.update({"epoch": anchor["epoch"],
                       "clock_anchor": {k:v for k,v in anchor.items() if k != "registers"},
                       "snapshot_host_age_ms": elapsed_ns / 1_000_000,
                       "clock_uncertainty_ns": anchor["anchor_uncertainty_ns"],
                       "registers": dict(anchor["registers"])})
        if received_ns - anchor["host_before_ns"] >= self.max_age_ns:
            result["reason"] = "snapshot_stale"
            return result
        estimated_ticks = anchor["pl_ticks64"] + elapsed_ns // 10  # 100 MHz
        result["estimated_frame_pl_ticks64"] = estimated_ticks
        ages = {}
        unavailable = {}
        for name in ("US", "QEI0", "QEI1", "RISK"):
            raw = anchor["registers"].get(name + "_TS")
            if raw is None:
                result["reason"] = "missing_sample_timestamp"
                return result
            anchor_age = ((anchor["pl_ticks64"] & 0xffffffff) - raw) & 0xffffffff
            if anchor_age >= 0x80000000:
                # An explicitly invalid sensor has no usable sample time.
                # Preserve the raw state and its invalid display flag without
                # discarding a correctly clock-associated camera frame.
                meta = anchor["registers"].get(name + "_META")
                if meta is not None and not meta & 0x80000000:
                    ages[name.lower()] = None
                    unavailable[name.lower()] = "invalid_sample_timestamp_ambiguous"
                    continue
                result["reason"] = "ambiguous_sample_timestamp"
                return result
            ages[name.lower()] = (anchor_age * 10 + elapsed_ns) / 1_000_000
        result["sample_age_ms"] = ages
        result["unavailable_sample_ages"] = unavailable
        result["valid"] = True
        result["reason"] = "associated"
        return result
