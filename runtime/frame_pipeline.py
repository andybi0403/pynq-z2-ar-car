"""Dependency-light camera-to-VDMA frame preparation for task 8.

FFmpeg performs UVC decode, resize, rate conversion and BGR0 packing.  The
four bytes in DDR are B,G,R,0 on a little-endian ARM; the existing RTL strips
the high padding byte and presents AXIS[23:16]=R, [15:8]=G, [7:0]=B.  Physical
HDMI lane order still requires the documented color-bar test on the board.
"""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO


WIDTH = 640
HEIGHT = 480
FPS = 30
PIXEL_BYTES = 4
FRAME_BYTES = WIDTH * HEIGHT * PIXEL_BYTES


def build_ffmpeg_command(
    ffmpeg: Path,
    *,
    backend: str,
    device: str,
    width: int = WIDTH,
    height: int = HEIGHT,
    fps: int = FPS,
) -> list[str]:
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("width, height and fps must be positive")
    if backend == "dshow":
        source = ["-f", "dshow", "-i", f"video={device}"]
    elif backend == "v4l2":
        source = ["-f", "v4l2", "-i", device]
    else:
        raise ValueError("backend must be dshow or v4l2")
    return [
        str(ffmpeg), "-hide_banner", "-loglevel", "warning", *source,
        "-an", "-vf", f"scale={width}:{height}:flags=bilinear,fps={fps}",
        "-pix_fmt", "bgr0", "-f", "rawvideo", "pipe:1",
    ]


def read_exact(stream: BinaryIO, size: int) -> bytes | None:
    if size <= 0:
        raise ValueError("size must be positive")
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if remaining == size:
                return None
            raise EOFError(f"truncated raw frame: missing {remaining} bytes")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def copy_frame(frame: bytes, destination) -> None:
    target = memoryview(destination).cast("B")
    if len(frame) != len(target):
        raise ValueError(f"frame/buffer size mismatch: {len(frame)} != {len(target)}")
    target[:] = frame


def color_bars_bgr0(width: int = WIDTH, height: int = HEIGHT) -> bytes:
    if width < 3 or height <= 0:
        raise ValueError("color bars require width>=3 and positive height")
    colors = ((0, 0, 255, 0), (0, 255, 0, 0), (255, 0, 0, 0))
    row = bytearray(width * 4)
    for x in range(width):
        bar = min(2, (x * 3) // width)
        row[x * 4:x * 4 + 4] = bytes(colors[bar])
    return bytes(row) * height


@dataclass
class FrameMetrics:
    expected_fps: float = FPS
    frames: int = 0
    inferred_drops: int = 0
    first_ns: int | None = None
    last_ns: int | None = None
    intervals_ns: deque[int] = field(default_factory=lambda:deque(maxlen=8192))

    def __post_init__(self) -> None:
        if self.expected_fps <= 0:
            raise ValueError("expected_fps must be positive")

    def observe(self, arrival_ns: int) -> None:
        if arrival_ns < 0:
            raise ValueError("arrival_ns must be non-negative")
        if self.last_ns is not None:
            if arrival_ns < self.last_ns:
                raise ValueError("arrival time moved backwards")
            interval = arrival_ns - self.last_ns
            self.intervals_ns.append(interval)
            nominal = 1_000_000_000 / self.expected_fps
            self.inferred_drops += max(0, round(interval / nominal) - 1)
        else:
            self.first_ns = arrival_ns
        self.last_ns = arrival_ns
        self.frames += 1

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = round((len(ordered) - 1) * percentile)
        return ordered[index] / 1_000_000

    def summary(self) -> dict[str, int | float | str | None]:
        # Windowed quantiles use bounded storage; totals/FPS remain cumulative.
        ordered = sorted(self.intervals_ns)
        quantiles = {
            f"interval_p{p}_ms": (ordered[round((len(ordered)-1)*p/100)] / 1_000_000
                                  if ordered else None)
            for p in (50, 95, 99)
        }
        elapsed_s = None
        measured_fps = None
        if self.first_ns is not None and self.last_ns is not None:
            elapsed_s = (self.last_ns - self.first_ns) / 1_000_000_000
            if elapsed_s > 0 and self.frames > 1:
                measured_fps = (self.frames - 1) / elapsed_s
        return {
            "frames": self.frames,
            "inferred_drops": self.inferred_drops,
            "elapsed_s": elapsed_s,
            "measured_fps": measured_fps,
            "interval_scope": "last_8192_intervals; FPS and frame totals cumulative",
            **quantiles,
        }


class TripleBufferQueue:
    """Three-buffer ownership model for a producer and VDMA consumer.

    A buffer moves FREE -> READY -> DISPLAYING -> FREE.  The producer cannot
    overwrite a ready or displayed frame.  On PYNQ, ``release_display`` must be
    called only after the matching VDMA frame-complete event; this class does
    not pretend that such an interrupt occurred on the development PC.
    """

    def __init__(self, frame_bytes: int = FRAME_BYTES):
        if frame_bytes <= 0:
            raise ValueError("frame_bytes must be positive")
        self.frame_bytes = frame_bytes
        self.buffers = [bytearray(frame_bytes) for _ in range(3)]
        self._state = ["FREE"] * 3
        self._sequence = [-1] * 3
        self._ready: deque[int] = deque()
        self._next_sequence = 0

    def submit(self, frame: bytes) -> tuple[int, int]:
        try:
            index = self._state.index("FREE")
        except ValueError as exc:
            raise BufferError("all three frame buffers are owned") from exc
        copy_frame(frame, self.buffers[index])
        sequence = self._next_sequence
        self._next_sequence += 1
        self._sequence[index] = sequence
        self._state[index] = "READY"
        self._ready.append(index)
        return index, sequence

    def acquire_display(self) -> tuple[int, int, memoryview] | None:
        if not self._ready:
            return None
        index = self._ready.popleft()
        if self._state[index] != "READY":
            raise RuntimeError("triple-buffer ownership is corrupt")
        self._state[index] = "DISPLAYING"
        return index, self._sequence[index], memoryview(self.buffers[index])

    def release_display(self, index: int) -> None:
        if index not in range(3) or self._state[index] != "DISPLAYING":
            raise ValueError("buffer is not owned by the display")
        self._state[index] = "FREE"

    def states(self) -> tuple[str, str, str]:
        return tuple(self._state)


class RawFrameSource:
    """Bounded producer with a deadline per frame and drained stderr.

    The stdout worker may block in an OS read, but the caller never does.
    Closing terminates the child before joining workers, unblocking both pipes.
    At most two completed frames and 64 KiB of diagnostic text are retained.
    """
    def __init__(self, command: list[str], frame_bytes: int = FRAME_BYTES,
                 timeout_s: float = 2.0):
        if not command or frame_bytes < 1:
            raise ValueError("command and positive frame_bytes are required")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("frame timeout must be positive and finite")
        self.command = list(command)
        self.frame_bytes = frame_bytes
        self.timeout_s = timeout_s
        self.process: subprocess.Popen | None = None
        self._frames = queue.Queue(maxsize=2)
        self._cancel = threading.Event()
        self._stderr = deque(maxlen=64)
        self._stderr_lock = threading.Lock()
        self._workers = []
        self._ended = False
        self.last_received_ns = None
        self.frame_sequence = -1

    @property
    def diagnostics(self) -> str:
        with self._stderr_lock:
            return b"".join(self._stderr).decode("utf-8", errors="replace")

    def _publish(self, value):
        while not self._cancel.is_set():
            try:
                self._frames.put(value, timeout=0.1)
                return
            except queue.Full:
                pass

    def _read_frames(self):
        try:
            while not self._cancel.is_set():
                frame = read_exact(self.process.stdout, self.frame_bytes)
                self._publish((frame, time.monotonic_ns()) if frame is not None else None)
                if frame is None:
                    return
        except (OSError, ValueError, EOFError) as exc:
            self._publish(exc)

    def _drain_stderr(self):
        try:
            while not self._cancel.is_set():
                chunk = self.process.stderr.read(1024)
                if not chunk:
                    return
                with self._stderr_lock:
                    self._stderr.append(chunk)
        except (OSError, ValueError):
            # Pipe closure during shutdown is expected; stdout controls success.
            return

    def __enter__(self):
        if self.process is not None:
            raise RuntimeError("frame source cannot be opened twice")
        self.process = subprocess.Popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        for target in (self._read_frames, self._drain_stderr):
            worker = threading.Thread(target=target, daemon=True)
            self._workers.append(worker)
            worker.start()
        return self

    def read(self) -> bytes | None:
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("frame source is not open")
        if self._cancel.is_set():
            raise RuntimeError("frame source is closed")
        if self._ended:
            return None
        try:
            result = self._frames.get(timeout=self.timeout_s)
        except queue.Empty as exc:
            raise TimeoutError(
                f"camera frame deadline exceeded ({self.timeout_s:g}s); "
                f"stderr tail: {self.diagnostics}"
            ) from exc
        if isinstance(result, Exception):
            raise type(result)(f"{result}; stderr tail: {self.diagnostics}")
        if result is None:
            self._ended = True
            # EOF is not success if the decoder itself failed.
            try:
                code = self.process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                code = None
            if code not in (None, 0):
                for worker in self._workers:
                    worker.join(timeout=0.25)
                raise RuntimeError(
                    f"camera process exited {code}; stderr tail: {self.diagnostics}"
                )
        else:
            result, self.last_received_ns = result
            self.frame_sequence += 1
        return result

    def close(self):
        self._cancel.set()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            for worker in self._workers:
                worker.join(timeout=2)
            for pipe in (self.process.stdout, self.process.stderr):
                if pipe is not None:
                    pipe.close()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True, type=Path)
    parser.add_argument("--backend", choices=("dshow", "v4l2"), required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--metrics", type=Path)
    args = parser.parse_args(argv)
    if args.frames < 1:
        parser.error("--frames must be positive")
    command = build_ffmpeg_command(args.ffmpeg, backend=args.backend, device=args.device)
    metrics = FrameMetrics()
    try:
        with RawFrameSource(command) as source:
            for _ in range(args.frames):
                if source.read() is None:
                    raise EOFError("camera stream ended before requested frame count")
                metrics.observe(time.monotonic_ns())
    except (OSError, EOFError, RuntimeError, ValueError) as exc:
        print(f"FRAME_PIPELINE_FAIL backend={args.backend} device={args.device}: {exc}")
        return 1
    result = {
        "schema": "car-video-metrics/v1", "backend": args.backend,
        "device": args.device, "width": WIDTH, "height": HEIGHT,
        "fps_target": FPS, "pixel_format": "bgr0", **metrics.summary(),
    }
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if args.metrics:
        args.metrics.write_text(rendered + "\n", encoding="utf-8")
    print("FRAME_PIPELINE_PASS " + rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
