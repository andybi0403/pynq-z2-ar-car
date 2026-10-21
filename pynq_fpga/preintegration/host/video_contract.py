"""Host-side contract for the task 7/8 pre-integration video path."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoMode:
    width: int
    height: int
    fps: float
    # The DDR/VDMA contract uses BGR0 words.  AXIS drops the padding byte later.
    pixel_bytes: int = 4

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("frame dimensions must be positive")
        if not (0 < self.fps <= 120):
            raise ValueError("fps must be in (0, 120]")
        if self.pixel_bytes not in (1, 2, 3, 4):
            raise ValueError("unsupported bytes per pixel")

    @property
    def frame_bytes(self) -> int:
        self.validate()
        return self.width * self.height * self.pixel_bytes

    @property
    def payload_bytes_per_second(self) -> float:
        return self.frame_bytes * self.fps


def aligned_stride(width: int, pixel_bytes: int, alignment: int = 64) -> int:
    if width <= 0 or pixel_bytes <= 0:
        raise ValueError("width and pixel_bytes must be positive")
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    raw = width * pixel_bytes
    return (raw + alignment - 1) & ~(alignment - 1)


def ddr_traffic_bytes_per_second(mode: VideoMode, passes: int = 4) -> float:
    """Conservative memory traffic for capture/copy plus VDMA read.

    The current pipe creates a decoded BGR0 frame, then copies it into a DMA
    buffer.  Four transfers model decoded-frame write, copy read, DMA-buffer
    write and MM2S read.  The streaming OSD itself does not write another frame
    to DDR.  A future zero-copy producer may justify a lower measured value.
    """
    if passes < 1:
        raise ValueError("passes must be at least one")
    return mode.payload_bytes_per_second * passes


@dataclass
class FrameFreshnessGuard:
    timeout_ms: int = 200
    last_sequence: int | None = None
    last_arrival_ms: int | None = None

    def observe(self, sequence: int, arrival_ms: int) -> bool:
        if sequence < 0 or arrival_ms < 0:
            raise ValueError("sequence and time must be non-negative")
        advanced = self.last_sequence is None or sequence != self.last_sequence
        if advanced:
            self.last_sequence = sequence
            self.last_arrival_ms = arrival_ms
        return advanced

    def valid(self, now_ms: int) -> bool:
        if now_ms < 0:
            raise ValueError("time must be non-negative")
        if self.last_arrival_ms is None:
            return False
        return now_ms - self.last_arrival_ms <= self.timeout_ms
