# -*- coding: utf-8 -*-
"""夜间B：OSD 逐像素比对 + PNG 生成 + 差异图。

流程：
  1. 用参考渲染器（独立实现）生成 7 个场景的期望帧 osd_ref_fN.rgb
  2. 与 RTL dump（tb_car_osd_text.sv 产出 osd_rtl_fN.rgb）逐像素比对
  3. 全部一致 -> RTL dump 转 PNG（真实 RTL 输出，非参考图冒充）
     不一致 -> 保存差异图与首个差异坐标，退出码非 0
运行：python compare_osd.py
"""
import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from osd_ref_render import render  # noqa: E402

W, H = 480, 112
SCENARIOS = [
    ("f1", dict(risk_level=1, stop=0, locked=0, distance_valid=1, speed_valid=1,
                distance_mm=1000, speed_q16=2_0000_0000)),
    ("f2", dict(risk_level=1, stop=0, locked=0, distance_valid=1, speed_valid=1,
                distance_mm=750, speed_q16=-(1234 * 65536))),
    ("f3", dict(risk_level=3, stop=0, locked=0, distance_valid=0, speed_valid=0,
                distance_mm=0xFFF, speed_q16=0x80000000)),
    ("f4", dict(risk_level=2, stop=1, locked=1, distance_valid=1, speed_valid=1,
                distance_mm=500, speed_q16=1_0000_0000)),
    ("f5", dict(risk_level=0, stop=0, locked=0, distance_valid=1, speed_valid=1,
                distance_mm=2000, speed_q16=3_0000_0000)),
    ("f6", dict(risk_level=0, stop=0, locked=0, distance_valid=1, speed_valid=0,
                distance_mm=321, speed_q16=65536)),
    ("f7", dict(risk_level=0, stop=0, locked=0, distance_valid=0, speed_valid=1,
                distance_mm=0xFFF, speed_q16=-(42 * 65536))),
]
BASE = Path(__file__).resolve().parent


def write_png(path, w, h, rgb24_list):
    """最小 PNG encoder（无第三方依赖，zlib 标准库压缩）。"""
    raw = b""
    for y in range(h):
        raw += b"\x00"  # filter none
        row = rgb24_list[y * w:(y + 1) * w]
        for c in row:
            raw += struct.pack(">3B", (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6))
    png += chunk(b"IEND", b"")
    Path(path).write_bytes(png)


def read_rgb(path):
    vals = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            vals.append(int(line, 16))
    assert len(vals) == W * H, f"{path}: {len(vals)} px, expect {W*H}"
    return vals


def write_rgb(path, values):
    Path(path).write_text("".join(f"{v:06x}\n" for v in values), encoding="ascii")


def latest_rtl_dir():
    build = BASE.parents[1] / "fpga" / "build" / "sim_tb_car_osd_text"
    candidates = [p for p in build.iterdir() if p.is_dir() and
                  (p / "osd_rtl_f1.rgb").exists()]
    if not candidates:
        raise FileNotFoundError(f"no timestamped RTL dump under {build}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtl-dir", type=Path, default=None,
                        help="XSim run directory containing osd_rtl_fN.rgb")
    parser.add_argument("--out-dir", type=Path, default=BASE / "osd_out")
    args = parser.parse_args(argv)
    rtl_dir = args.rtl_dir.resolve() if args.rtl_dir else latest_rtl_dir()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"RTL_DIR={rtl_dir}")
    total_err = 0
    for name, kw in SCENARIOS:
        stale_diff = out_dir / f"diff_{name}.png"
        if stale_diff.exists():
            stale_diff.unlink()
        ref = render(W, H, **kw)
        write_rgb(out_dir / f"ref_{name}.rgb", ref)
        rtl_path = rtl_dir / f"osd_rtl_{name}.rgb"
        rtl = read_rgb(rtl_path)
        mism = [(i, rtl[i], ref[i]) for i in range(W * H) if rtl[i] != ref[i]]
        if mism:
            first = mism[0]
            print(f"[FAIL] {name}: {len(mism)} mismatched px, "
                  f"first idx={first[0]} (x={first[0]%W},y={first[0]//W}) "
                  f"rtl={first[1]:06x} ref={first[2]:06x}")
            # 差异图：红=RTL色，黑=参考色
            diff = [0xFF0000 if a != b else 0x101010
                    for a, b in zip(rtl, ref)]
            write_png(out_dir / f"diff_{name}.png", W, H, diff)
            total_err += 1
        else:
            print(f"[ok] {name}: pixel-exact ({W*H} px)")
        # PNG 由实际 RTL 输出生成（非参考渲染冒充）
        write_png(out_dir / f"rtl_{name}.png", W, H, rtl)
    if total_err:
        print(f"COMPARE FAILED ({total_err} scenario(s) with mismatches)")
        sys.exit(1)
    print("COMPARE PASSED (all scenarios pixel-exact)")
    sys.exit(0)


if __name__ == "__main__":
    main()
