# -*- coding: utf-8 -*-
"""Compare the real RTL 640x480 dump and emit an actual-output PNG."""
import argparse
import sys
from pathlib import Path

from compare_osd import write_png, write_rgb
from osd_ref_render import render

W, H = 640, 480


def read_rgb(path):
    values = [int(line, 16) for line in Path(path).read_text().splitlines()
              if line.strip()]
    if len(values) != W * H:
        raise ValueError(f"{path}: {len(values)} pixels, expected {W*H}")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtl", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rtl = read_rgb(args.rtl)
    ref = render(W, H, risk_level=2, stop=1, locked=0,
                 distance_valid=1, speed_valid=1,
                 distance_mm=1234, speed_q16=(-(432 * 65536)) & 0xFFFFFFFF)
    write_rgb(args.out_dir / "ref_640x480.rgb", ref)
    mismatches = [(i, a, b) for i, (a, b) in enumerate(zip(rtl, ref)) if a != b]
    write_png(args.out_dir / "rtl_640x480.png", W, H, rtl)
    diff_path = args.out_dir / "diff_640x480.png"
    if mismatches:
        i, actual, expected = mismatches[0]
        diff = [0xFF0000 if a != b else 0x101010 for a, b in zip(rtl, ref)]
        write_png(diff_path, W, H, diff)
        print(f"[FAIL] 640x480: {len(mismatches)} mismatches; first x={i%W},y={i//W}, "
              f"rtl={actual:06x}, ref={expected:06x}")
        return 1
    if diff_path.exists():
        diff_path.unlink()
    print(f"[ok] 640x480: pixel-exact ({W*H} px), RTL PNG={args.out_dir/'rtl_640x480.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
