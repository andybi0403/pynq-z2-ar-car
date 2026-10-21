"""Validate the one register source and generate RTL/Python/Markdown constants."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "register_map.json"
RTL = ROOT.parent / "rtl" / "car_reg_defs.vh"
PY = ROOT.parent.parent / "host" / "car_regs.py"
MD = ROOT.parent.parent / "nightly" / "register_map_v0.10.md"


def number(value: object) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def render() -> dict[Path, str]:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    regs = spec["registers"]
    seen: dict[int, str] = {}
    regions = [(r["name"], number(r["start"]), number(r["end"])) for r in spec["regions"]]
    region_names: set[str] = set()
    for name, lo, hi in regions:
        if name in region_names:
            raise ValueError(f"duplicate region name: {name}")
        region_names.add(name)
        if lo > hi:
            raise ValueError(f"invalid region range {name}: {lo:#x}..{hi:#x}")
    ordered_regions = sorted(regions, key=lambda item: item[1])
    for previous, current in zip(ordered_regions, ordered_regions[1:]):
        if current[1] <= previous[2]:
            raise ValueError(
                f"region overlap: {previous[0]} {previous[1]:#x}..{previous[2]:#x} "
                f"and {current[0]} {current[1]:#x}..{current[2]:#x}"
            )
    for reg in regs:
        off = number(reg["offset"])
        if off & 3:
            raise ValueError(f"unaligned register {reg['name']} at {off:#x}")
        if off in seen:
            raise ValueError(f"duplicate {off:#x}: {seen[off]} and {reg['name']}")
        seen[off] = reg["name"]
        if not any(lo <= off <= hi for _, lo, hi in regions):
            raise ValueError(f"register outside regions: {reg['name']}")
        if reg["access"] not in {"RO", "WO", "RW"}:
            raise ValueError(f"invalid access for {reg['name']}")

    version = number(spec["contract_version"])
    ident = number(spec["integrated_id"])
    if ident & 0xFF != version:
        raise ValueError("ID low byte must equal contract_version")

    vh = ["// Generated from registers/register_map.json; do not hand edit.",
          "`ifndef CAR_REG_DEFS_VH", "`define CAR_REG_DEFS_VH",
          f"`define CAR_INTEGRATED_ID 32'h{ident:08X}"]
    py = ["# Generated from fpga/registers/register_map.json; do not hand edit.",
          f"CONTRACT_VERSION = {version}", f"INTEGRATED_ID = 0x{ident:08X}"]
    md = [f"# 统一寄存器表 v0.{version}", "", "由 `fpga/registers/register_map.json` 生成，禁止手工修改本表。", "", "| 偏移 | 名称 | 访问 | 复位 | 说明 |", "|---:|---|---|---:|---|"]
    for reg in regs:
        off = number(reg["offset"])
        vh.append(f"`define CAR_REG_{reg['name']} 12'h{off:03X}")
        py.append(f"{reg['name']} = 0x{off:03X}")
        md.append(f"| 0x{off:03X} | {reg['name']} | {reg['access']} | {reg['reset']} | {reg['description']} |")
    vh += ["`endif", ""]
    py.append("")
    md.append("")
    return {RTL: "\n".join(vh), PY: "\n".join(py), MD: "\n".join(md)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = render()
    if args.check:
        bad = [str(path) for path, text in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
        if bad:
            print("STALE: " + ", ".join(bad))
            return 1
        print(f"REGISTER_MAP_PASS ({len(outputs)} generated files)")
        return 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"REGISTER_MAP_GENERATED ({len(outputs)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
