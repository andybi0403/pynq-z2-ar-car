"""Audit a returned handoff offline. Never import its scripts or access hardware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(path: Path) -> dict:
    envelope = json.loads(path.read_text(encoding="utf-8-sig"))
    decoder = json.JSONDecoder()
    output = envelope.get("output", "")
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                value, _ = decoder.raw_decode(line)
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
    raise ValueError(f"No JSON result in {path.name}")


def contained(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes handoff: {relative}")
    return result


def audit(handoff: Path, project: Path) -> dict:
    manifest = json.loads((handoff / "文件清单.json").read_text(encoding="utf-8-sig"))
    checks = []
    for row in manifest["source_files"]:
        path = contained(handoff, row["path"])
        actual = digest(path) if path.is_file() else None
        size = path.stat().st_size if path.is_file() else None
        checks.append({"path": row["path"], "expected_sha256": row["sha256"],
                       "actual_sha256": actual, "expected_bytes": row["bytes"],
                       "actual_bytes": size, "matched": actual == row["sha256"] and size == row["bytes"]})
    checksum_checks = []
    for line in (handoff / "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        relative = relative.lstrip(" *")
        path = contained(handoff, relative)
        checksum_checks.append({"path": relative, "matched": path.is_file() and digest(path) == expected})
    mapping = {
        "board_manifest.json": "pynq_fpga/fpga/board/board_manifest.json",
        "register_map_v0.11.md": "pynq_fpga/nightly/register_map_v0.11.md",
        "task7_8_integrated.xdc": "pynq_fpga/preintegration/constraints/task7_8_integrated.xdc",
    }
    source_checks = []
    for source in sorted((handoff / "相关源码").rglob("*")):
        if not source.is_file():
            continue
        relative = "pynq_fpga/fpga/rtl/" + source.name if source.parent.name == "rtl" else mapping[source.name]
        local = project / relative
        source_checks.append({"returned": source.relative_to(handoff).as_posix(), "local": relative,
                              "sha256": digest(source), "matched": local.is_file() and digest(source) == digest(local)})
    logs = handoff / "实测日志"
    ground = payload(logs / "board_gpio_jb1_ground_check-163921.json")
    wire = payload(logs / "board_gpio_output_wire_ground_check-172052.json")
    converter = payload(logs / "board_gpio_converter_low_control-171210.json")
    gpio = {}
    for name, result in [("independent_wire", ground), ("original_la3_wire", wire)]:
        values = result["B_input_states"]
        gpio[name] = {"samples": len(values), "all_jb1_low": bool(values) and all(v & 1 == 0 for v in values),
                      "b_states": sorted(set(values)), "restored": result["restored"],
                      "restored_id": result["restored_id"], "scales_after_restore": result["scales_after_restore"]}
    gpio["converter"] = {"disabled": converter["oe_disabled"], "enabled": converter["oe_enabled"],
                         "all_enabled_jb1_low": all(v & 1 == 0 for v in converter["oe_enabled"]["all_input_states"]),
                         "restored": converter["restored"]}
    uart = payload(logs / "board_locked_query-095546.json")
    raw = bytes.fromhex(uart["raw_hex"])
    import binascii
    frames = [line.strip() for line in raw.splitlines() if line.startswith(b"$S1,")]
    crc_errors = 0
    requests = []
    for frame in frames:
        # The production protocol covers the leading '$', excluding ',CRC#'.
        body, checksum = frame[:-1].rsplit(b",", 1)
        crc_errors += binascii.crc_hqx(body, 0xFFFF) != int(checksum, 16)
        requests.append(int(body.split(b",")[2]))
    epochs = []
    for name in ["board_encoder_prepare-153805.json", "board_encoder_prepare-154010.json", "board_encoder_prepare-154201.json"]:
        result = payload(logs / name)
        epochs.append({"file": name, "epoch": result["epoch"], "qei": result["qei"]})
    end = payload(logs / "board_read_end_summary-102429.json")["last_summary"]
    test3 = json.loads((handoff / "网页导出/test3.json").read_text(encoding="utf-8-sig"))
    release_zip = next((handoff / "原发布包_供比对不要求重刷").glob("*.zip"))
    local_zip = project / "pynq_fpga/release/v011_uart_recovery_20261026_r17b.zip"
    mismatches = [row for row in checks if not row["matched"]]
    return {"schema": "returned-handoff-audit/v1", "hardware_accessed": False,
            "upstream_manifest": {"checked": len(checks), "matched": len(checks)-len(mismatches), "mismatches": mismatches},
            "upstream_sha256sums": {"checked": len(checksum_checks), "mismatches": [row for row in checksum_checks if not row["matched"]]},
            "production_source_checks": source_checks,
            "original_r17b_zip_identical": local_zip.is_file() and digest(release_zip) == digest(local_zip),
            "gpio": gpio,
            "uart": {"frames": len(frames), "independent_crc_errors": crc_errors,
                     "requests_exactly_1_to_80": requests == list(range(1, 81)), "all_locked_zero": uart["all_locked_zero"]},
            "qei_snapshots": epochs,
            "failed_session": {key: end.get(key) for key in ["duration_observed_s", "passed", "motion_allowed", "release_sent", "failures", "control_timing"]},
            "test3": {"browser_video": test3["browser_video"], "control_timing": test3["state"]["control_timing"],
                      "motion_allowed": test3["state"]["motion_allowed"], "interconnect_test": test3["state"]["interconnect_test"]},
            "integrity_passed": not mismatches and all(row["matched"] for row in checksum_checks)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.handoff.resolve(), args.project_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "manifest": result["upstream_manifest"],
                      "production_sources_identical": all(x["matched"] for x in result["production_source_checks"]),
                      "original_r17b_zip_identical": result["original_r17b_zip_identical"], "uart": result["uart"],
                      "integrity_passed": result["integrity_passed"]}, ensure_ascii=False))
    return 0 if result["integrity_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
