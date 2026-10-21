"""Check the generated video interconnect and unsuppressed routed DRC report.

This is build evidence, not a hardware or image-quality acceptance test.
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from hwh_contract import audit_hwh


def audit(hwh: Path, drc: Path, bus_skew: Path | None = None) -> dict:
    audit_hwh(hwh, require_placeholder=False)
    root = ET.parse(hwh).getroot()
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    mem = modules["video_hp0_ic"]
    if mem.get("MODTYPE") != "smartconnect":
        raise ValueError("legacy video interconnect: expected SmartConnect")
    params = {p.get("NAME"): p.get("VALUE") for p in mem.iter("PARAMETER")}
    vdma_params={p.get('NAME'):p.get('VALUE') for p in modules['video_vdma'].iter('PARAMETER')}
    wireless=vdma_params.get('C_INCLUDE_S2MM')=='1'
    for name in ("NUM_SI", "NUM_MI", "NUM_CLKS", "HAS_ARESETN"):
        expected='2' if wireless and name=='NUM_SI' else '1'
        if params.get(name) != expected:
            raise ValueError(f"video SmartConnect {name} must be {expected}")

    def port(instance, name):
        matches = modules[instance].findall(f"./PORTS/PORT[@NAME='{name}']")
        if len(matches) != 1:
            raise ValueError(f"missing/ambiguous {instance}/{name}")
        return matches[0]

    clocks=[("video_hp0_ic", "aclk"),
                           ("video_vdma", "m_axi_mm2s_aclk"),
                           ("ps7", "S_AXI_HP0_ACLK")]
    if wireless:
        clocks += [('video_vdma','m_axi_s2mm_aclk'),('video_vdma','s_axis_s2mm_aclk'),('video_capture_adapter','aclk')]
        from wireless_dma import audit_wireless_hwh
        audit_wireless_hwh(hwh)
    for instance, name in clocks:
        p = port(instance, name)
        if p.get("CLKFREQUENCY") != "100000000" or not any(
            c.get("INSTANCE") == "ps7" and c.get("PORT") == "FCLK_CLK0"
            for c in p.iter("CONNECTION")
        ):
            raise ValueError(f"{instance}/{name} must share PS FCLK0 at 100 MHz")
    for instance, name in (("video_hp0_ic", "aresetn"), ("video_vdma", "axi_resetn")):
        p = port(instance, name)
        if p.get("POLARITY") != "ACTIVE_LOW" or not any(
            c.get("INSTANCE") == "rst_100m" and c.get("PORT") == "peripheral_aresetn"
            for c in p.iter("CONNECTION")
        ):
            raise ValueError(f"{instance}/{name} must share the peripheral reset")

    report = drc.read_text(encoding="utf-8")
    if "Fully Routed" not in report:
        raise ValueError("DRC evidence must come from a fully routed design")
    findings = re.findall(r"^([A-Z][A-Z0-9]+-\d+)#\d+ (Warning|Advisory|Error|Critical Warning)\s*$",
                          report, re.MULTILINE)
    if not findings and "REPORT SUMMARY" not in report:
        raise ValueError("missing DRC summary")
    blocking = [(rule, severity) for rule, severity in findings
                if rule in {"REQP-1839", "PDCN-1569"}
                or severity in {"Error", "Critical Warning"}]
    if blocking:
        raise ValueError(f"blocking video/design DRC: {blocking}")
    skew_slacks = []
    if bus_skew is not None:
        skew_report = bus_skew.read_text(encoding="utf-8")
        skew_slacks = re.findall(r"Slack \((MET|VIOLATED)\)\s*:\s*([+-]?[0-9.]+)ns", skew_report)
        if not skew_slacks or any(state != "MET" or float(slack) < 0 for state, slack in skew_slacks):
            raise ValueError("missing or failing routed bus-skew evidence")
    counts = {}
    for rule, severity in findings:
        key = f"{rule} {severity}"
        counts[key] = counts.get(key, 0) + 1
    return {"status": "PASS", "hwh": str(hwh.resolve()), "drc": str(drc.resolve()),
            "video_interconnect": "smartconnect", "clock_hz": 100000000,
            "shared_peripheral_reset": True, "remaining_drc": counts,
            "bus_skew_slack_ns": [float(slack) for _, slack in skew_slacks],
            "hardware_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwh", type=Path, required=True)
    parser.add_argument("--drc", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bus-skew", type=Path)
    args = parser.parse_args()
    result = audit(args.hwh, args.drc, args.bus_skew)
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print("VIDEO_RELIABILITY_AUDIT_PASS " + encoded)


if __name__ == "__main__":
    main()
