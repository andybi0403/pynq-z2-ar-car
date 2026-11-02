"""PYNQ-side launcher for the integrated task 7/8 candidate overlay.

The module imports PYNQ only inside ``open()`` so contract tests run on the
Windows development host.  It uses the upstream PYNQ AxiVDMA driver and
display helper instead of duplicating register programming.  A real .bit/.hwh
pair is deliberately required; this file never pretends that PC tests are a
board run.
"""

from __future__ import annotations

import argparse
import json
import time
import threading
from dataclasses import dataclass,field
from pathlib import Path

from frame_pipeline import (
    FRAME_BYTES, FrameMetrics, RawFrameSource, build_ffmpeg_command,
    color_bars_bgr0, copy_frame,
)
from hwh_contract import audit_hwh
from overlay_session import DeviceLease, open_verified_overlay
from frame_metadata import prefix_bgr0


EXPECTED_IP = {
    "video_vdma": (0x43000000, 0x10000),
    "car_system": (0x43C00000, 0x1000),
    "hdmi_dynclk": (0x43C10000, 0x10000),
    "hdmi_vtc": (0x43C20000, 0x10000),
    "hdmi_hpd_gpio": (0x41230000, 0x10000),
}


def validate_ip_dict(ip_dict: dict) -> dict[str, dict[str, int]]:
    """Reject a stale/mismatched HWH before any display or DMA operation."""
    if "control_slot_stub" in ip_dict or "osd_slot_stub" in ip_dict:
        raise ValueError("isolated placeholder overlay is not a production candidate")
    checked: dict[str, dict[str, int]] = {}
    for name, (expected_base, expected_range) in EXPECTED_IP.items():
        if name not in ip_dict:
            raise ValueError(f"overlay is missing IP {name}")
        item = ip_dict[name]
        base = int(item.get("phys_addr", -1))
        span = int(item.get("addr_range", 0))
        if base != expected_base or span < expected_range:
            raise ValueError(
                f"{name} address mismatch: got 0x{base:08X}/0x{span:X}, "
                f"expected 0x{expected_base:08X}/at least 0x{expected_range:X}"
            )
        checked[name] = {"phys_addr": base, "addr_range": span}
    return checked


def validate_artifact_pair(bitfile: Path, hwhfile: Path) -> None:
    if not bitfile.is_file() or not hwhfile.is_file():
        raise FileNotFoundError("a real, matching .bit and .hwh pair is required")
    if bitfile.stem != hwhfile.stem:
        raise ValueError("bitstream and HWH must have the same stem")
    audit_hwh(hwhfile, require_placeholder=False)


@dataclass
class Task78BoardRuntime:
    overlay: object
    vdma: object
    display: object
    hpd_gpio: object
    video_mode_type: type
    running: bool = False
    _lifecycle_lock: object = field(default_factory=threading.RLock,repr=False,compare=False)

    @classmethod
    def open(cls, bitfile: Path, hwhfile: Path, *, download=None):
        validate_artifact_pair(bitfile, hwhfile)
        overlay = open_verified_overlay(bitfile, hwhfile, download=download)
        return cls.from_overlay(overlay)

    @classmethod
    def from_overlay(cls, overlay):
        """Use the session's existing Overlay without a second download."""
        try:
            import pynq.lib._video as pynq_video
            from pynq.lib.video import VideoMode
        except ImportError as exc:
            raise RuntimeError(
                "PYNQ runtime is unavailable; run this launcher on the PYNQ-Z2 image"
            ) from exc

        validate_ip_dict(overlay.ip_dict)
        vdma = getattr(overlay, "video_vdma")
        hpd_gpio = getattr(overlay, "hdmi_hpd_gpio")
        display = pynq_video._display(0x43C20000, 0x43C10000, 1)
        return cls(overlay, vdma, display, hpd_gpio, VideoMode)

    @property
    def monitor_connected(self) -> bool:
        # Local schematic sheet 6: HDMI pin 19 drives a 2N7002; the FPGA net
        # HDMI_TX_HPDN is pulled up and therefore active-low.
        return (int(self.hpd_gpio.channel1.read()) & 1) == 0

    def start(self, *, require_monitor: bool = True) -> None:
        with self._lifecycle_lock:
            if self.running:
                raise RuntimeError("video runtime is already started")
            if require_monitor and not self.monitor_connected:
                raise RuntimeError("HDMI monitor not detected on active-low HPDN")
            self.display.mode(0)  # PYNQ upstream table: 640x480
            self.vdma.writechannel.mode = self.video_mode_type(640, 480, 32, fps=30)
            try:
                self.display.start()
                self.vdma.writechannel.start()
            except Exception:
                try:
                    self.vdma.writechannel.stop()
                finally:
                    self.display.stop()
                raise
            self.running = True

    def newframe(self):
        if not self.running:
            raise RuntimeError("video runtime is not started")
        return self.vdma.writechannel.newframe()

    def write_bytes(self, raw_bgr0: bytes) -> None:
        self._submit_bytes(raw_bgr0)

    def write_associated(self, raw_bgr0: bytes, metadata_words) -> None:
        """Copy once into the owned DMA frame, then stamp its 18-pixel prefix.

        Source bytes remain immutable. PYNQ writeframe performs cache flush
        and takes ownership; the submitted frame is never modified again.
        """
        self._submit_bytes(raw_bgr0, prefix_bgr0(metadata_words))

    def _submit_bytes(self, raw_bgr0: bytes, prefix=b'') -> None:
        if len(raw_bgr0) != FRAME_BYTES:
            raise ValueError(f"expected {FRAME_BYTES} BGR0 bytes")
        frame = self.newframe()
        try:
            copy_frame(raw_bgr0, frame)
            if prefix:
                memoryview(frame).cast('B')[:len(prefix)] = prefix
        except Exception:
            if hasattr(frame, "freebuffer"):
                frame.freebuffer()
            raise
        self.vdma.writechannel.writeframe(frame)

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self.running:
                try:
                    self.vdma.writechannel.stop()
                finally:
                    try:
                        self.display.stop()
                    finally:
                        self.running = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bit", required=True, type=Path)
    parser.add_argument("--hwh", required=True, type=Path)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--reload", action="store_true",
                        help="explicitly reload PL; resets calibration and commands")
    parser.add_argument("--allow-no-monitor", action="store_true")
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--camera-device")
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--metrics", type=Path)
    args = parser.parse_args(argv)
    if bool(args.ffmpeg) != bool(args.camera_device):
        parser.error("--ffmpeg and --camera-device must be provided together")
    if args.frames < 1:
        parser.error("--frames must be positive")
    if args.no_download and args.reload:
        parser.error("--no-download and --reload are mutually exclusive")
    runtime = None
    lease = None
    status = 0
    try:
        lease = DeviceLease()
        lease.__enter__()
        runtime = Task78BoardRuntime.open(
            args.bit, args.hwh,
            download=False if args.no_download else True if args.reload else None,
        )
        runtime.start(require_monitor=not args.allow_no_monitor)
        if args.camera_device:
            command = build_ffmpeg_command(
                args.ffmpeg, backend="v4l2", device=args.camera_device
            )
            metrics = FrameMetrics()
            with RawFrameSource(command) as source:
                for _ in range(args.frames):
                    frame = source.read()
                    if frame is None:
                        raise EOFError("camera stream ended before requested frame count")
                    runtime.write_bytes(frame)
                    metrics.observe(time.monotonic_ns())
            evidence = metrics.summary()
            evidence.update({"hardware": True, "source": args.camera_device})
            if args.metrics:
                args.metrics.parent.mkdir(parents=True, exist_ok=True)
                args.metrics.write_text(
                    json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            print("TASK7_8_BOARD_CAMERA_PASS " + json.dumps(evidence, sort_keys=True))
        else:
            runtime.write_bytes(color_bars_bgr0())
            evidence = {
                "hardware": True,
                "mode": "640x480@30",
                "ddr_format": "BGR0",
                "monitor_connected": runtime.monitor_connected,
                "test_frame": "red-green-blue-bars",
            }
            print("TASK7_8_BOARD_COLOR_BARS_STARTED " + json.dumps(evidence, sort_keys=True))
            input("Press Enter to stop HDMI output...")
    except (OSError, EOFError, ValueError, RuntimeError, AttributeError) as exc:
        print(f"TASK7_8_BOARD_START_FAIL: {exc}")
        status = 1
    except KeyboardInterrupt:
        print("TASK7_8_BOARD_INTERRUPTED")
        status = 130
    finally:
        if runtime is not None:
            try:
                runtime.stop()
            except (OSError, RuntimeError, AttributeError) as exc:
                print(f"TASK7_8_BOARD_CLEANUP_FAIL: {exc}")
                status = 1
        if lease is not None:
            lease.__exit__(None, None, None)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
