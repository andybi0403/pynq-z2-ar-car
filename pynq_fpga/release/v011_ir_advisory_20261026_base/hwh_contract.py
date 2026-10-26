"""Audit the generated task 7/8 HWH before any PYNQ runtime uses it."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class HwhContract:
    control_base: int
    control_size: int
    vdma_base: int
    vdma_size: int
    dynclk_base: int
    dynclk_size: int
    vtc_base: int
    vtc_size: int
    hpd_base: int
    hpd_size: int
    video_bits: int
    video_clock_hz: int
    reset_active_low: bool
    hpd_is_input: bool
    interrupts_to_ps: bool
    placeholder_present: bool
    production_present: bool
    sensor_ports_present: bool
    uart_emio_present: bool


def _width(port: ET.Element) -> int:
    left = port.get("LEFT")
    right = port.get("RIGHT")
    if left is None and right is None:
        return 1
    if left is None or right is None:
        raise ValueError(f"incomplete width on port {port.get('NAME')}")
    return abs(int(left) - int(right)) + 1


def _one(elements: list[ET.Element], what: str) -> ET.Element:
    if len(elements) != 1:
        raise ValueError(f"expected one {what}, found {len(elements)}")
    return elements[0]


def audit_hwh(path: Path, *, require_placeholder: bool = True) -> HwhContract:
    root = ET.parse(path).getroot()
    ranges = list(root.iter("MEMRANGE"))

    def region(instance: str) -> tuple[int, int]:
        item = _one([e for e in ranges if e.get("INSTANCE") == instance],
                    f"MEMRANGE for {instance}")
        base = int(item.get("BASEVALUE", ""), 0)
        high = int(item.get("HIGHVALUE", ""), 0)
        if high < base:
            raise ValueError(f"invalid MEMRANGE for {instance}")
        return base, high - base + 1

    control_instance = "control_slot_stub" if require_placeholder else "car_system"
    control_base, control_size = region(control_instance)
    vdma_base, vdma_size = region("video_vdma")
    dynclk_base, dynclk_size = region("hdmi_dynclk")
    vtc_base, vtc_size = region("hdmi_vtc")
    hpd_base, hpd_size = region("hdmi_hpd_gpio")
    modules = list(root.iter("MODULE"))
    module_by_instance = {e.get("INSTANCE"): e for e in modules}
    module_types = {e.get("MODTYPE") for e in modules}
    placeholder = "axi_control_slot_stub" in module_types
    production = "car_board_video_wrapper" in module_types
    sink = module_by_instance.get("hdmi_axis_to_video")
    osd_slot = module_by_instance.get("osd_slot_stub" if require_placeholder else "car_system")
    if sink is None or osd_slot is None:
        raise ValueError("HDMI sink or explicit OSD slot is missing")
    tdata = _one([e for e in sink.iter("PORT")
                  if e.get("NAME") == "s_axis_video_tdata"],
                 "HDMI sink AXIS tdata port")
    clock = _one([e for e in osd_slot.iter("PORT") if e.get("NAME") == "aclk"],
                 "OSD slot aclk port")
    reset = _one([e for e in osd_slot.iter("PORT") if e.get("NAME") == "aresetn"],
                 "OSD slot aresetn port")
    ports = list(root.findall("./EXTERNALPORTS/PORT"))
    if not ports:  # compact synthetic fixtures use PORTS
        ports = list(root.findall("./PORTS/PORT"))
    port_names = {e.get("NAME") for e in ports}

    if (control_base, control_size) != (0x43C00000, 0x1000):
        raise ValueError("control window must be 0x43C00000/4KiB")
    if (vdma_base, vdma_size) != (0x43000000, 0x10000):
        raise ValueError("VDMA window must be 0x43000000/64KiB")
    if (dynclk_base, dynclk_size) != (0x43C10000, 0x10000):
        raise ValueError("HDMI clock window must be 0x43C10000/64KiB")
    if (vtc_base, vtc_size) != (0x43C20000, 0x10000):
        raise ValueError("HDMI VTC window must be 0x43C20000/64KiB")
    if (hpd_base, hpd_size) != (0x41230000, 0x10000):
        raise ValueError("HDMI HPD window must be 0x41230000/64KiB")
    if _width(tdata) != 24:
        raise ValueError("OSD slot must be 24-bit AXIS")
    if int(clock.get("CLKFREQUENCY", "0")) != 100_000_000:
        raise ValueError("video clock must be 100MHz")
    if reset.get("POLARITY") != "ACTIVE_LOW":
        raise ValueError("video reset must be active-low")
    required_ports = {"hdmi_out_clk_n", "hdmi_out_clk_p", "hdmi_out_data_n",
                      "hdmi_out_data_p", "hdmi_tx_hpdn"}
    if not required_ports.issubset(port_names):
        raise ValueError("HDMI TMDS/HPD top-level ports are incomplete")
    hpd_port = _one([e for e in ports if e.get("NAME") == "hdmi_tx_hpdn"],
                    "HDMI HPDN top-level port")
    if hpd_port.get("DIR") not in ("I", "IN"):
        raise ValueError("HDMI HPDN must be an input per local schematic sheet 6")

    def connected(instance: str, port: str, peer_instance: str, peer_port: str) -> bool:
        module = module_by_instance.get(instance)
        if module is None:
            return False
        for item in module.iter("PORT"):
            if item.get("NAME") != port:
                continue
            return any(c.get("INSTANCE") == peer_instance and
                       c.get("PORT") == peer_port
                       for c in item.iter("CONNECTION"))
        return False

    interrupts_ok = (
        connected("video_vdma", "mm2s_introut", "video_irq_concat", "In0") and
        connected("hdmi_hpd_gpio", "ip2intc_irpt", "video_irq_concat", "In1") and
        connected("video_irq_concat", "dout", "ps7", "IRQ_F2P")
    )
    if not interrupts_ok:
        raise ValueError("VDMA/HPDN interrupts must route through video_irq_concat to PS")
    if require_placeholder and not placeholder:
        raise ValueError("isolated framework is missing its explicit control placeholder")
    if require_placeholder and (production or "car_perception_top" in module_types or "car_axis_osd" in module_types):
        raise ValueError("A-E production RTL leaked into isolated HWH")
    sensor_ports = {"us_echo", "us_trig", "ir_l_raw", "ir_r_raw",
                    "qei0_a", "qei0_b", "qei1_a", "qei1_b"}
    sensors_ok = sensor_ports.issubset(port_names)
    uart_ok = {"uart_rxd", "uart_txd"}.issubset(port_names)
    if not require_placeholder:
        if not production or placeholder:
            raise ValueError("integrated HWH must contain production wrapper and no placeholder")
        if not sensors_ok:
            raise ValueError("integrated HWH is missing sensor top-level ports")
        if not uart_ok:
            raise ValueError("integrated HWH is missing PS UART1 EMIO ports")

    return HwhContract(
        control_base=control_base,
        control_size=control_size,
        vdma_base=vdma_base,
        vdma_size=vdma_size,
        dynclk_base=dynclk_base,
        dynclk_size=dynclk_size,
        vtc_base=vtc_base,
        vtc_size=vtc_size,
        hpd_base=hpd_base,
        hpd_size=hpd_size,
        video_bits=24,
        video_clock_hz=100_000_000,
        reset_active_low=True,
        hpd_is_input=True,
        interrupts_to_ps=True,
        placeholder_present=placeholder,
        production_present=production,
        sensor_ports_present=sensors_ok,
        uart_emio_present=uart_ok,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hwh", required=True, type=Path)
    parser.add_argument("--integrated", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit_hwh(args.hwh, require_placeholder=not args.integrated)
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"HWH_CONTRACT_FAIL file={args.hwh}: {exc}")
        return 1
    print("HWH_CONTRACT_PASS " + json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
