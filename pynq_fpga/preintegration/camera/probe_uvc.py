"""Parse UVC capabilities and optionally run a short, non-recording smoke test.

The command intentionally writes no camera image. On Windows it uses FFmpeg's
DirectShow device interface. On PYNQ Linux the same JSON schema can be filled
from v4l2-ctl output after the camera is moved to the board.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


MODE_RE = re.compile(
    r"pixel_format=(?P<format>\w+)\s+min s=(?P<width>\d+)x(?P<height>\d+)\s+fps=(?P<fps>[0-9.]+)"
)


def parse_dshow_modes(text: str) -> list[dict[str, object]]:
    modes = []
    for match in MODE_RE.finditer(text):
        modes.append(
            {
                "pixel_format": match.group("format"),
                "width": int(match.group("width")),
                "height": int(match.group("height")),
                "fps": float(match.group("fps")),
            }
        )
    return modes


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True, type=Path)
    parser.add_argument("--device", default="Logi C270 HD WebCam")
    parser.add_argument("--smoke-seconds", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    query = run(
        [
            str(args.ffmpeg), "-hide_banner", "-list_options", "true",
            "-f", "dshow", "-i", f"video={args.device}",
        ]
    )
    combined = query.stdout + query.stderr
    modes = parse_dshow_modes(combined)
    result: dict[str, object] = {
        "device_name": args.device,
        "backend": "DirectShow",
        "modes": modes,
        "capability_query_exit": query.returncode,
    }
    smoke_ok = None
    if args.smoke_seconds > 0 and modes:
        mode = modes[0]
        smoke = run(
            [
                str(args.ffmpeg), "-hide_banner", "-f", "dshow",
                "-video_size", f"{mode['width']}x{mode['height']}",
                "-framerate", str(mode["fps"]), "-pixel_format",
                str(mode["pixel_format"]), "-i", f"video={args.device}",
                "-t", str(args.smoke_seconds), "-an", "-f", "null", "-",
            ]
        )
        smoke_text = smoke.stdout + smoke.stderr
        frame_matches = re.findall(r"frame=\s*(\d+)", smoke_text)
        smoke_ok = smoke.returncode == 0 and bool(frame_matches)
        result["smoke"] = {
            "seconds": args.smoke_seconds,
            "exit": smoke.returncode,
            "last_reported_frame": int(frame_matches[-1]) if frame_matches else 0,
            "ok": smoke_ok,
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if modes and smoke_ok is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())

