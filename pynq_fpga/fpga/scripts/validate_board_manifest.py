import argparse
import json
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true", help="require every physical constraint to be verified")
    args = parser.parse_args()
    path = pathlib.Path(__file__).resolve().parents[1] / "board" / "board_manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    if data.get("schema_version") != 2:
        errors.append("unexpected manifest schema version")
    if data.get("part") != "xc7z020clg400-1":
        errors.append("unexpected FPGA part")
    ports = data.get("ports", [])
    names = [p.get("name") for p in ports]
    if len(names) != len(set(names)):
        errors.append("duplicate logical port")
    pins = [p.get("package_pin") for p in ports if p.get("physical")]
    if len(pins) != len(set(pins)):
        errors.append("duplicate package pin")
    for p in ports:
        if not p.get("name") or p.get("direction") not in {"input", "output", "inout"}:
            errors.append(f"invalid port entry: {p!r}")
        if p.get("physical"):
            if not p.get("package_pin") or not p.get("iostandard"):
                errors.append(f"physical port lacks pin/electrical data: {p.get('name')}")
            if p.get("bank") not in {13, 34, 35}:
                errors.append(f"unexpected or missing IO bank: {p.get('name')}")
            if p.get("verified") and len(p.get("evidence", [])) < 2:
                errors.append(f"verified physical port lacks two-source evidence: {p.get('name')}")
        elif p.get("package_pin") or p.get("iostandard"):
            errors.append(f"internal port must not claim package constraint: {p.get('name')}")
    if args.release:
        unresolved = [p.get("name") for p in ports if not p.get("verified")]
        electrical = [p.get("name") for p in ports if p.get("physical") and not p.get("electrical_ready")]
        if not data.get("release_ready") or unresolved or electrical:
            errors.append("release blocked; unresolved ports: " + ", ".join(unresolved or ["none"]))
            errors.append("release blocked; external electrical checks: " + ", ".join(electrical or ["none"]))
        if not data.get("hardware_revision_confirmed"):
            errors.append("release blocked; physical board revision not confirmed")
        for key, value in data.get("evidence", {}).items():
            if not value:
                errors.append(f"release evidence missing: {key}")
    if errors:
        for item in errors:
            print("BOARD_MANIFEST_ERROR:", item)
        return 1
    print(f"BOARD_MANIFEST_PASS ({len(ports)} logical ports; release={args.release})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
