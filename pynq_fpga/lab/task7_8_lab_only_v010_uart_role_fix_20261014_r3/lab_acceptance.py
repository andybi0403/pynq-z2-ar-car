"""Safe, evidence-producing bench runner for task 7/8 LAB_ONLY artifacts.

The default ``contract`` command runs on a PC.  Hardware commands import PYNQ
only after the artifact pair has passed its hash and HWH checks.  No command in
this file sends a non-zero motor request or a release request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


HERE = Path(__file__).resolve().parent
if not (HERE / "perception_client.py").is_file():
    PROJECT = HERE.parents[1]
    sys.path.insert(0, str(PROJECT / "host"))
    sys.path.insert(0, str(PROJECT.parent / "stm32预备程序" / "pc"))

from board_runtime import (  # noqa: E402
    Task78BoardRuntime, validate_artifact_pair, validate_ip_dict,
)
from frame_pipeline import FrameMetrics, RawFrameSource, build_ffmpeg_command  # noqa: E402
from overlay_session import DeviceLease, open_verified_overlay  # noqa: E402
from runtime_identity import RUNTIME_FILES,sha256 as runtime_sha256
from perception_client import (  # noqa: E402
    ContractError, PerceptionClient, PynqMMIO, QEI_SCALE_PROFILES,
    snapshot_to_link_sample,
)
from perception_replay import snapshot_registers  # noqa: E402

try:
    from . import car_regs as reg  # noqa: E402
except ImportError:
    import car_regs as reg  # noqa: E402


EXPECTED_CLASS = "LAB_ONLY_NO_MOTOR_NON_RELEASE"
CONTROL_BASE = 0x43C00000
CONTROL_LENGTH = 0x1000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_package(bitfile: Path, hwhfile: Path, manifest_path: Path, *,
                   allow_legacy_contract: bool = False) -> dict:
    try:
        validate_artifact_pair(bitfile, hwhfile)
    except ET.ParseError as exc:
        raise ValueError(f"hwh not well-formed: {exc}") from exc
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "car-lab-artifact/v1":
        raise ValueError("unsupported or missing LAB_ONLY manifest schema")
    if manifest.get("classification") != EXPECTED_CLASS:
        raise ValueError("artifact is not classified as LAB_ONLY non-release")
    accepted = {f"0x{reg.INTEGRATED_ID:08X}"}
    if allow_legacy_contract:
        accepted.add("0xC4251006")
    if manifest.get("integrated_id") not in accepted:
        raise ValueError("LAB_ONLY manifest has the wrong integrated contract ID")
    contracts = manifest.get("contracts", {})
    if contracts.get("release_gate") != "BLOCKED_EXPECTED":
        raise ValueError("LAB_ONLY manifest does not preserve the release block")
    if contracts.get("motor_output_allowed") is not False:
        raise ValueError("LAB_ONLY manifest must prohibit motor output")
    for key, path in (("bit", bitfile), ("hwh", hwhfile)):
        entry = manifest.get("artifacts", {}).get(key, {})
        if entry.get("file") != path.name:
            raise ValueError(f"{key} filename differs from manifest")
        if int(entry.get("bytes", -1)) != path.stat().st_size:
            raise ValueError(f"{key} length differs from manifest")
        if entry.get("sha256") != _sha256(path):
            raise ValueError(f"{key} SHA-256 differs from manifest")
    if manifest.get('integrated_id') == f'0x{reg.INTEGRATED_ID:08X}':
        code = manifest.get('runtime_files')
        if not isinstance(code,dict) or set(code)!=set(RUNTIME_FILES):
            raise ValueError('LAB_ONLY runtime source hashes are incomplete')
        for name,digest in code.items():
            file=manifest_path.parent/name
            if not file.is_file() or runtime_sha256(file)!=digest:
                raise ValueError(f'LAB_ONLY runtime source mismatch: {name}')
    return manifest


def _load_overlay(bitfile: Path):
    overlay = open_verified_overlay(bitfile, bitfile.with_suffix(".hwh"))
    validate_ip_dict(overlay.ip_dict)
    return overlay


def run_mmio(bitfile: Path, hwhfile: Path, manifest_path: Path,
             output: Path, count: int, interval: float) -> None:
    if count < 2:
        raise ValueError("count must be at least 2 to prove epoch progression")
    verify_package(bitfile, hwhfile, manifest_path)
    _load_overlay(bitfile)
    io = PynqMMIO(CONTROL_BASE, CONTROL_LENGTH)
    client = PerceptionClient(io)
    client.verify_contract()
    records = []
    previous_epoch = None
    for index in range(count):
        ticks, shot, decision = client.sample_and_decide()
        if previous_epoch is not None and shot.epoch == previous_epoch:
            raise ContractError(f"snapshot epoch did not advance at sample {index}")
        previous_epoch = shot.epoch
        records.append({
            "index": index,
            "epoch": shot.epoch,
            "pl_ticks": ticks,
            "host_monotonic_ns": time.monotonic_ns(),
            "registers": snapshot_registers(shot),
            "decision": {"permit": decision.permit, "reasons": list(decision.reasons)},
        })
        if index + 1 < count:
            time.sleep(interval)
    evidence = {
        "schema": "car-lab-mmio/v1", "hardware": True,
        "artifact": bitfile.name, "integrated_id": f"0x{reg.INTEGRATED_ID:08X}",
        "control_base": CONTROL_BASE, "control_length": CONTROL_LENGTH,
        "samples": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"LAB_MMIO_PASS samples={count} output={output}")


def sensor_mismatches(registers: dict, expectations: dict) -> list[str]:
    """Return exact mismatches for one raw snapshot; empty means a match."""
    us_data = int(registers["US_DATA"]) & 0xFFFFFFFF
    us_meta = int(registers["US_META"]) & 0xFFFFFFFF
    ir_data = int(registers["IR_STATUS"]) & 0xFFFFFFFF
    ir_meta = int(registers["IR_META"]) & 0xFFFFFFFF
    observed = {
        "us_valid": int(bool(us_meta & 0x80000000)),
        "us_fault": (us_data >> 12) & 0xF,
        "distance_mm": us_data & 0xFFF,
        "ir_valid": int(bool(ir_meta & 0x80000000)),
        "ir_mask": ir_data & 0x3,
        "ir_stable": int(bool(ir_data & 0x4)),
        "risk_stop": int(bool(int(registers["RISK_STATE"]) & 1)),
    }
    mismatches = []
    for name in ("us_valid", "us_fault", "ir_valid", "ir_mask",
                 "ir_stable", "risk_stop"):
        expected = expectations.get(name)
        if expected is not None and observed[name] != expected:
            mismatches.append(f"{name}: got {observed[name]}, expected {expected}")
    minimum = expectations.get("distance_min")
    maximum = expectations.get("distance_max")
    if minimum is not None and observed["distance_mm"] < minimum:
        mismatches.append(
            f"distance_mm: got {observed['distance_mm']}, expected >= {minimum}"
        )
    if maximum is not None and observed["distance_mm"] > maximum:
        mismatches.append(
            f"distance_mm: got {observed['distance_mm']}, expected <= {maximum}"
        )
    return mismatches


def decode_risk_state(value: int) -> dict[str, int | bool]:
    """Decode the frozen v0.6 RISK_STATE word for readable bench evidence."""
    raw = int(value) & 0xFFFFFFFF
    reasons = (raw >> 16) & 0xFFFF
    return {
        "raw": raw,
        "stop": bool(raw & 1),
        "level": (raw >> 1) & 0x3,
        "reason_bits": reasons,
        "command_invalid": bool(reasons & (1 << 1)),
        "command_stale": bool(reasons & (1 << 2)),
    }


def qei_scale_arg(text: str) -> int:
    """argparse type for one explicit Q16.16 SCALE register value."""
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from exc
    if not 1 <= value <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError(
            "scale must be in [1, 0xFFFFFFFF]; 0 means uncalibrated"
        )
    return value


def run_qei_config(bitfile: Path, hwhfile: Path, manifest_path: Path,
                   output: Path, profile: str | None,
                   left_scale: int | None, right_scale: int | None,
                   motor_disconnected: bool) -> None:
    """Standalone QEI scale configuration/verification entry.

    Writing CFG_SCALE is a configuration action, never part of the read-only
    sensor-check or of normal startup: it requires explicit operator intent
    (profile or both per-side scales) plus the motor-disconnected /
    wheels-off-ground confirmation.
    """
    if not motor_disconnected:
        raise ValueError(
            "qei-config requires --motor-disconnected: unplug the motor "
            "power and keep both front wheels off the ground"
        )
    explicit_scales = left_scale is not None or right_scale is not None
    if profile is not None and explicit_scales:
        raise ValueError("give either --qei-profile or --left-scale/--right-scale, not both")
    if explicit_scales and (left_scale is None or right_scale is None):
        raise ValueError("--left-scale and --right-scale must be given together")
    if profile is None and not explicit_scales:
        raise ValueError("qei-config requires --qei-profile or --left-scale/--right-scale")

    verify_package(bitfile, hwhfile, manifest_path)
    _load_overlay(bitfile)
    client = PerceptionClient(PynqMMIO(CONTROL_BASE, CONTROL_LENGTH))
    if profile is not None:
        applied_profile = profile
        applied = client.configure_qei_profile(profile)
    else:
        applied_profile = None
        applied = client.configure_qei_scales(left_scale, right_scale)

    # Second readback after the verified write proves the registers hold the
    # calibrated values stably, not only during the write transaction.
    try:
        stable_left = client.io.read32(reg.QEI0_SCALE) & 0xFFFFFFFF
        stable_right = client.io.read32(reg.QEI1_SCALE) & 0xFFFFFFFF
        if stable_left != applied[0] or stable_right != applied[1]:
            raise ContractError(
                "QEI scale registers did not hold the configured values: "
                f"left 0x{stable_left:08X}, right 0x{stable_right:08X}"
            )
    except Exception as exc:
        try:
            client.invalidate_qei_scales()
            cleanup = "both channels invalidated"
        except Exception as cleanup_exc:
            cleanup = f"cleanup incomplete: {cleanup_exc}"
        raise ContractError(
            f"QEI scale stability verification failed; {cleanup}: {exc}"
        ) from exc
    evidence = {
        "schema": "car-lab-qei-config/v1", "hardware": True,
        "artifact": bitfile.name, "integrated_id": f"0x{reg.INTEGRATED_ID:08X}",
        "motor_disconnected": True,
        "profile": applied_profile,
        "channel_map": {"QEI0_SCALE": "left_front", "QEI1_SCALE": "right_front"},
        "left_scale": applied[0], "right_scale": applied[1],
        "left_scale_hex": f"0x{applied[0]:08X}",
        "right_scale_hex": f"0x{applied[1]:08X}",
        "readback_verified": True,
        "temporary_nominal": applied_profile is not None,
        "release_sent": False, "nonzero_command_sent": False,
        "note": ("Values remain temporary until the per-side loaded rollout "
                 "calibration replaces them (see docs/03_硬件与接线/10)."),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(f"LAB_QEI_CONFIG_PASS left={applied[0]} right={applied[1]} "
          f"profile={applied_profile} output={output}")


def run_sensor_check(bitfile: Path, hwhfile: Path, manifest_path: Path,
                     output: Path, count: int, interval: float,
                     expectations: dict, port: str = "/dev/ttyPS1") -> None:
    if count < 2:
        raise ValueError("count must be at least 2 to prove epoch progression")
    if not any(value is not None for value in expectations.values()):
        raise ValueError("sensor-check requires at least one expected value")
    verify_package(bitfile, hwhfile, manifest_path)
    _load_overlay(bitfile)
    client = PerceptionClient(PynqMMIO(CONTROL_BASE, CONTROL_LENGTH))
    client.verify_contract()
    from pynq_link import HybridCarLink
    link = HybridCarLink(port)
    try:
        client.attach_sensor_link(link)
        link.start()
        deadline=time.monotonic()+.5
        while time.monotonic()<deadline:
            report=link.sensor_snapshot()
            if report is not None and report['us_seq']!=0:break
            time.sleep(.01)
        records = []
        previous_epoch = None
        for index in range(count):
            ticks, shot, decision = client.sample_and_decide()
            if previous_epoch is not None and shot.epoch == previous_epoch:
                raise ContractError(f"snapshot epoch did not advance at sample {index}")
            previous_epoch = shot.epoch
            registers = snapshot_registers(shot)
            records.append({
                "index": index,
                "epoch": shot.epoch,
                "pl_ticks": ticks,
                "host_monotonic_ns": time.monotonic_ns(),
                "registers": registers,
                "decision": {"permit": decision.permit, "reasons": list(decision.reasons)},
                "mismatches": sensor_mismatches(registers, expectations),
            })
            if index + 1 < count:
                time.sleep(interval)
    finally:
        link.close()
    failed = [item for item in records if item["mismatches"]]
    evidence = {
        "schema": "car-lab-sensor-check/v1", "hardware": True,
        "artifact": bitfile.name, "integrated_id": f"0x{reg.INTEGRATED_ID:08X}",
        "expectations": expectations, "samples": records,
        "passed": not failed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    if failed:
        first = failed[0]
        raise ContractError(
            f"sensor expectation failed at sample {first['index']}: "
            + "; ".join(first["mismatches"])
        )
    print(f"LAB_SENSOR_CHECK_PASS samples={count} output={output}")


def run_uart_stop(port: str, duration: float, output: Path,
                  motor_disconnected: bool, stop_deadline_ms: float = 300.0,
                  link_factory=None) -> None:
    if not motor_disconnected:
        raise ValueError("UART STOP test requires --motor-disconnected")
    if stop_deadline_ms <= 0:
        raise ValueError("stop_deadline_ms must be positive")
    if link_factory is None:
        from pynq_link import HybridCarLink
        link_factory = lambda: HybridCarLink(port)

    link = link_factory()
    states = []
    first_safe_latency_ms = None
    try:
        if callable(getattr(link, 'sensor_snapshot', None)) and 'client' in locals():
            client.attach_sensor_link(link)
        link.start()
        baseline_seq = int(link.state_seq)
        requested_at = time.monotonic()
        link.stop_request()
        deadline = requested_at + duration
        seen_seq = baseline_seq
        while time.monotonic() < deadline:
            current_seq = int(link.state_seq)
            if current_seq != seen_seq:
                state = link.state
                if state is not None:
                    received_at = time.monotonic()
                    entry = dict(state)
                    entry["rx_seq"] = current_seq
                    entry["after_stop_ms"] = (received_at - requested_at) * 1000.0
                    states.append(entry)
                    if (first_safe_latency_ms is None and entry["left"] == 0
                            and entry["right"] == 0 and entry["lock"] != 0):
                        first_safe_latency_ms = entry["after_stop_ms"]
                seen_seq = current_seq
            time.sleep(0.01)
    finally:
        link.close()
    if not states:
        raise ContractError("no fresh $CAR status received after STOP request")
    if any(item["left"] != 0 or item["right"] != 0 for item in states):
        raise ContractError(f"STM32 reported non-zero output during STOP test: {states}")
    if first_safe_latency_ms is None:
        raise ContractError(f"STM32 did not report a latched state: {states}")
    if first_safe_latency_ms > stop_deadline_ms:
        raise ContractError(
            f"fresh locked-zero $CAR arrived after {first_safe_latency_ms:.1f} ms; "
            f"deadline is {stop_deadline_ms:.1f} ms"
        )
    evidence = {
        "schema": "car-lab-uart-stop/v1", "hardware": True,
        "motor_disconnected": True, "port": port, "baud": 115200,
        "duration_s": duration, "states": states,
        "fresh_after_request": True,
        "first_safe_latency_ms": first_safe_latency_ms,
        "stop_deadline_ms": stop_deadline_ms,
        "release_sent": False, "nonzero_command_sent": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"LAB_UART_STOP_PASS states={len(states)} output={output}")


def run_safety_loop(bitfile: Path, hwhfile: Path, manifest_path: Path,
                    port: str, duration: float, interval: float, output: Path,
                    motor_disconnected: bool,
                    stop_deadline_ms: float = 300.0,
                    client_factory=None, link_factory=None) -> None:
    """Run the real PL-client-to-CarLink path while commanding zero only."""
    if not motor_disconnected:
        raise ValueError("safety-loop requires --motor-disconnected")
    if duration <= 0 or interval <= 0 or stop_deadline_ms <= 0:
        raise ValueError("invalid safety-loop duration/interval/deadline")
    if client_factory is None:
        verify_package(bitfile, hwhfile, manifest_path)
        _load_overlay(bitfile)
        client = PerceptionClient(PynqMMIO(CONTROL_BASE, CONTROL_LENGTH))
    else:
        client = client_factory()
    client.verify_contract()
    if link_factory is None:
        from pynq_link import HybridCarLink
        link_factory = lambda: HybridCarLink(port)

    link = link_factory()
    timeline = []
    car_states = []
    first_safe_latency_ms = None
    unsafe_state = None
    previous_epoch = None
    started_at = time.monotonic()
    try:
        if callable(getattr(link, 'sensor_snapshot', None)) and 'client' in locals():
            client.attach_sensor_link(link)
        link.start()
        baseline_seq = int(link.state_seq)
        link.stop_request()
        seen_seq = baseline_seq
        deadline = started_at + duration
        while time.monotonic() < deadline:
            pl_ticks, shot, decision = client.sample_and_decide()
            if previous_epoch is not None and shot.epoch == previous_epoch:
                raise ContractError("snapshot epoch did not advance in safety-loop")
            previous_epoch = shot.epoch
            observed_at = time.monotonic()
            sample = snapshot_to_link_sample(shot, pl_ticks)
            # This phase exercises the production split-source API.  Both
            # sources are refreshed, but the driving request is always zero.
            link.update_sample(sample.valid, sample.distance_mm,
                               sample.infrared_mask, observed_at - ((pl_ticks-shot.ultrasonic.timestamp)&0xffffffff)/100_000_000)
            link.update_command(0, 0)
            current_seq = int(link.state_seq)
            car_state = None
            if current_seq != seen_seq and link.state is not None:
                car_state = dict(link.state)
                car_state["rx_seq"] = current_seq
                car_state["after_stop_ms"] = (time.monotonic() - started_at) * 1000.0
                car_states.append(car_state)
                seen_seq = current_seq
                if car_state["left"] != 0 or car_state["right"] != 0:
                    unsafe_state = car_state
                    link.stop_request()
                if (first_safe_latency_ms is None and car_state["left"] == 0
                        and car_state["right"] == 0 and car_state["lock"] != 0):
                    first_safe_latency_ms = car_state["after_stop_ms"]
            timeline.append({
                "host_monotonic_ns": time.monotonic_ns(),
                "pl_ticks": pl_ticks,
                "epoch": shot.epoch,
                "registers": snapshot_registers(shot),
                "decision": {"permit": decision.permit,
                             "reasons": list(decision.reasons)},
                "pl_risk": decode_risk_state(shot.risk_state),
                "link_sample": {
                    "valid": sample.valid,
                    "distance_mm": sample.distance_mm,
                    "infrared_mask": sample.infrared_mask,
                },
                "zero_command": True,
                "fresh_car_state": car_state,
            })
            if unsafe_state is not None:
                break
            time.sleep(interval)
    finally:
        link.close()

    failures = []
    if not car_states:
        failures.append("no fresh $CAR status received")
    if unsafe_state is not None:
        failures.append(f"non-zero motor output reported: {unsafe_state}")
    if first_safe_latency_ms is None:
        failures.append("no fresh locked-zero $CAR status received")
    elif first_safe_latency_ms > stop_deadline_ms:
        failures.append(
            f"first locked-zero response {first_safe_latency_ms:.1f} ms "
            f"exceeded {stop_deadline_ms:.1f} ms"
        )
    risk_reason_changes = []
    previous_reasons = None
    for index, item in enumerate(timeline):
        reasons = item["pl_risk"]["reason_bits"]
        if reasons != previous_reasons:
            risk_reason_changes.append({
                "index": index,
                "pl_ticks": item["pl_ticks"],
                "risk": item["pl_risk"],
            })
            previous_reasons = reasons
    evidence = {
        "schema": "car-lab-safety-loop/v1", "hardware": True,
        "artifact": bitfile.name, "integrated_id": f"0x{reg.INTEGRATED_ID:08X}",
        "motor_disconnected": True, "port": port, "baud": 115200,
        "duration_requested_s": duration,
        "duration_observed_s": time.monotonic() - started_at,
        "stop_deadline_ms": stop_deadline_ms,
        "first_safe_latency_ms": first_safe_latency_ms,
        "release_sent": False, "nonzero_command_sent": False,
        "baseline_pl_risk": timeline[0]["pl_risk"] if timeline else None,
        "risk_reason_changes": risk_reason_changes,
        "timeline": timeline, "car_states": car_states,
        "failures": failures, "passed": not failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    if failures:
        raise ContractError("safety-loop failed: " + "; ".join(failures))
    print(f"LAB_SAFETY_LOOP_PASS samples={len(timeline)} output={output}")


def camera_metric_mismatches(summary: dict, min_fps: float,
                             max_p95_ms: float,
                             max_drop_rate: float) -> list[str]:
    if min_fps <= 0 or max_p95_ms <= 0 or not 0 <= max_drop_rate <= 1:
        raise ValueError("invalid camera metric thresholds")
    frames = int(summary.get("frames") or 0)
    drops = int(summary.get("inferred_drops") or 0)
    fps = summary.get("measured_fps")
    p95 = summary.get("interval_p95_ms")
    drop_rate = drops / (frames + drops) if frames + drops else 1.0
    summary["inferred_drop_rate"] = drop_rate
    mismatches = []
    if fps is None or float(fps) < min_fps:
        mismatches.append(f"measured_fps: got {fps}, expected >= {min_fps}")
    if p95 is None or float(p95) > max_p95_ms:
        mismatches.append(f"interval_p95_ms: got {p95}, expected <= {max_p95_ms}")
    if drop_rate > max_drop_rate:
        mismatches.append(
            f"inferred_drop_rate: got {drop_rate:.6f}, expected <= {max_drop_rate}"
        )
    return mismatches


def run_video(bitfile: Path, hwhfile: Path, manifest_path: Path,
              output: Path, hold_seconds: float, ffmpeg: Path | None,
              camera_device: str | None, frames: int,
              min_fps: float = 25.0, max_p95_ms: float = 50.0,
              max_drop_rate: float = 0.05) -> None:
    verify_package(bitfile, hwhfile, manifest_path)
    runtime = Task78BoardRuntime.open(bitfile, hwhfile)
    runtime.start(require_monitor=True)
    try:
        if camera_device is None:
            from frame_pipeline import color_bars_bgr0
            runtime.write_bytes(color_bars_bgr0())
            time.sleep(hold_seconds)
            evidence = {
                "schema": "car-lab-video/v1", "hardware": True,
                "mode": "color-bars", "monitor_connected": runtime.monitor_connected,
                "frame_submitted": True, "visual_color_order_confirmed": False,
            }
        else:
            command = build_ffmpeg_command(ffmpeg, backend="v4l2", device=camera_device)
            metrics = FrameMetrics()
            with RawFrameSource(command) as source:
                for _ in range(frames):
                    frame = source.read()
                    if frame is None:
                        raise EOFError("camera stream ended before requested frame count")
                    runtime.write_bytes(frame)
                    metrics.observe(time.monotonic_ns())
            evidence = metrics.summary()
            mismatches = camera_metric_mismatches(
                evidence, min_fps, max_p95_ms, max_drop_rate
            )
            evidence.update({
                "schema": "car-lab-video/v1", "hardware": True,
                "mode": "camera", "device": camera_device,
                "monitor_connected": runtime.monitor_connected,
                "visual_color_order_confirmed": False,
                "thresholds": {
                    "min_fps": min_fps,
                    "max_p95_ms": max_p95_ms,
                    "max_drop_rate": max_drop_rate,
                },
                "metric_mismatches": mismatches,
                "metric_passed": not mismatches,
            })
    finally:
        runtime.stop()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if evidence["mode"] == "camera" and not evidence["metric_passed"]:
        raise ContractError("camera metrics failed: " + "; ".join(evidence["metric_mismatches"]))
    if evidence["mode"] == "color-bars":
        print(f"LAB_COLOR_BARS_SUBMITTED visual_confirmation_required output={output}")
    else:
        print(f"LAB_CAMERA_METRICS_PASS visual_confirmation_required output={output}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=(
        "contract", "mmio", "sensor-check", "uart-stop", "safety-loop",
        "color-bars", "camera", "qei-config"
    ))
    parser.add_argument("--bit", type=Path, default=HERE / "task7_8_LAB_ONLY.bit")
    parser.add_argument("--hwh", type=Path, default=HERE / "task7_8_LAB_ONLY.hwh")
    parser.add_argument("--manifest", type=Path, default=HERE / "lab_manifest.json")
    parser.add_argument("--evidence-dir", type=Path, default=HERE / "evidence")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--port", default="/dev/ttyPS1")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--stop-deadline-ms", type=float, default=300.0)
    parser.add_argument("--motor-disconnected", action="store_true")
    parser.add_argument("--hold-seconds", type=float, default=10.0)
    parser.add_argument("--ffmpeg", type=Path, default=Path("/usr/bin/ffmpeg"))
    parser.add_argument("--camera-device", default="/dev/video0")
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--min-fps", type=float, default=25.0)
    parser.add_argument("--max-p95-ms", type=float, default=50.0)
    parser.add_argument("--max-drop-rate", type=float, default=0.05)
    parser.add_argument("--label", default="scenario")
    parser.add_argument("--expect-us-valid", type=int, choices=(0, 1))
    parser.add_argument("--expect-us-fault", type=int, choices=range(16))
    parser.add_argument("--distance-min", type=int)
    parser.add_argument("--distance-max", type=int)
    parser.add_argument("--expect-ir-valid", type=int, choices=(0, 1))
    parser.add_argument("--expect-ir-mask", type=int, choices=range(4))
    parser.add_argument("--expect-ir-stable", type=int, choices=(0, 1))
    parser.add_argument("--expect-risk-stop", type=int, choices=(0, 1))
    parser.add_argument("--qei-profile", choices=sorted(QEI_SCALE_PROFILES))
    parser.add_argument("--left-scale", type=qei_scale_arg)
    parser.add_argument("--right-scale", type=qei_scale_arg)
    args = parser.parse_args(argv)
    if args.count < 2 or args.interval < 0 or args.duration <= 0 or args.frames < 1:
        parser.error("invalid count/interval/duration/frames")
    if args.min_fps <= 0 or args.max_p95_ms <= 0 or not 0 <= args.max_drop_rate <= 1:
        parser.error("invalid camera metric thresholds")
    if args.distance_min is not None and args.distance_min < 0:
        parser.error("distance-min must be non-negative")
    if args.distance_max is not None and args.distance_max < 0:
        parser.error("distance-max must be non-negative")
    if (args.distance_min is not None and args.distance_max is not None
            and args.distance_min > args.distance_max):
        parser.error("distance-min must not exceed distance-max")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", args.label):
        parser.error("label must be 1-48 ASCII letters, digits, '_' or '-'")
    device_lease = None
    try:
        if args.phase != "contract":
            device_lease = DeviceLease()
            device_lease.__enter__()
        if args.phase == "contract":
            manifest = verify_package(args.bit, args.hwh, args.manifest)
            print("LAB_CONTRACT_PASS " + json.dumps({
                "classification": manifest["classification"],
                "integrated_id": manifest["integrated_id"],
                "release_gate": manifest["contracts"]["release_gate"],
            }, sort_keys=True))
        elif args.phase == "mmio":
            run_mmio(args.bit, args.hwh, args.manifest,
                     args.evidence_dir / "mmio.json", args.count, args.interval)
        elif args.phase == "sensor-check":
            expectations = {
                "us_valid": args.expect_us_valid,
                "us_fault": args.expect_us_fault,
                "distance_min": args.distance_min,
                "distance_max": args.distance_max,
                "ir_valid": args.expect_ir_valid,
                "ir_mask": args.expect_ir_mask,
                "ir_stable": args.expect_ir_stable,
                "risk_stop": args.expect_risk_stop,
            }
            run_sensor_check(
                args.bit, args.hwh, args.manifest,
                args.evidence_dir / f"sensor_{args.label}.json",
                args.count, args.interval, expectations, args.port,
            )
        elif args.phase == "uart-stop":
            run_uart_stop(args.port, args.duration,
                          args.evidence_dir / "uart_stop.json", args.motor_disconnected,
                          args.stop_deadline_ms)
        elif args.phase == "safety-loop":
            run_safety_loop(
                args.bit, args.hwh, args.manifest, args.port,
                args.duration, args.interval,
                args.evidence_dir / "safety_loop.json",
                args.motor_disconnected, args.stop_deadline_ms,
            )
        elif args.phase == "qei-config":
            run_qei_config(
                args.bit, args.hwh, args.manifest,
                args.evidence_dir / "qei_config.json",
                args.qei_profile, args.left_scale, args.right_scale,
                args.motor_disconnected,
            )
        elif args.phase == "color-bars":
            run_video(args.bit, args.hwh, args.manifest,
                      args.evidence_dir / "color_bars.json", args.hold_seconds,
                      None, None, args.frames)
        else:
            run_video(args.bit, args.hwh, args.manifest,
                      args.evidence_dir / "camera_900.json", args.hold_seconds,
                      args.ffmpeg, args.camera_device, args.frames,
                      args.min_fps, args.max_p95_ms, args.max_drop_rate)
        return 0
    except (AttributeError, ContractError, EOFError, ImportError, OSError,
            RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"LAB_{args.phase.upper().replace('-', '_')}_FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if device_lease is not None:
            device_lease.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
