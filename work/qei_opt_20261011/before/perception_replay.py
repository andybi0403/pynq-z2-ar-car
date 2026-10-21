"""Deterministic v0.6 PL register recorder/replayer.

JSONL keeps raw register values. Replay drives the production PerceptionClient
through RegisterIO; it does not implement a second parser.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from . import car_regs as reg
    from .perception_client import (
        ContractError, PerceptionClient, PynqMMIO,
    )
except ImportError:
    import car_regs as reg
    from perception_client import ContractError, PerceptionClient, PynqMMIO


SCHEMA = "car-perception-replay/v1"
TICK_HZ = 100_000_000


def _u32(value) -> int:
    if isinstance(value, str):
        value = int(value, 0)
    if not isinstance(value, int):
        raise ValueError(f"register value is not an integer: {value!r}")
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"register value out of uint32 range: {value!r}")
    return value


REGISTER_OFFSETS = {
    name: value for name, value in vars(reg).items()
    if name.isupper() and isinstance(value, int) and name not in {
        "CONTRACT_VERSION", "INTEGRATED_ID"
    }
}

SNAPSHOT_REGISTER_NAMES = frozenset({
    "US_DATA", "US_TS", "US_META", "IR_STATUS", "IR_TS", "IR_META",
    "QEI0_POS", "QEI0_PERIOD", "QEI0_VEL", "QEI0_TS", "QEI0_META",
    "QEI1_POS", "QEI1_PERIOD", "QEI1_VEL", "QEI1_TS", "QEI1_META",
    "RISK_STATE", "RISK_REQUIRED_MM", "RISK_TS", "RISK_META",
    "CMD_STATE", "CMD_TS",
} | {f"ODOM{i}_{suffix}" for i in range(2) for suffix in
     ("DISP_LO", "DISP_HI", "PATH_LO", "PATH_HI", "TS", "META", "EPOCH")})


def _validate_header(path: Path, line_no: int, item: dict) -> None:
    if item.get("type") != "header" or item.get("schema") != SCHEMA:
        raise ValueError(f"{path}:{line_no}: missing {SCHEMA} header")
    if item.get("contract_version") != reg.CONTRACT_VERSION:
        raise ValueError(
            f"{path}:{line_no}: contract_version must be {reg.CONTRACT_VERSION}"
        )
    if _u32(item.get("contract_id")) != reg.INTEGRATED_ID:
        raise ValueError(
            f"{path}:{line_no}: contract_id must be 0x{reg.INTEGRATED_ID:08X}"
        )
    if item.get("tick_hz") != TICK_HZ:
        raise ValueError(f"{path}:{line_no}: tick_hz must be {TICK_HZ}")
    if not isinstance(item.get("source"), str) or not item["source"].strip():
        raise ValueError(f"{path}:{line_no}: non-empty source is required")
    if not isinstance(item.get("hardware"), bool):
        raise ValueError(f"{path}:{line_no}: hardware must be boolean")


def _validate_sample(path: Path, line_no: int, item: dict, expected_index: int) -> None:
    if item.get("type") != "sample" or not isinstance(item.get("registers"), dict):
        raise ValueError(f"{path}:{line_no}: sample/registers required")
    if item.get("index") != expected_index:
        raise ValueError(
            f"{path}:{line_no}: event index {item.get('index')!r}; "
            f"expected {expected_index}"
        )
    epoch = item.get("epoch")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or not 0 <= epoch <= 0xFFFF:
        raise ValueError(f"{path}:{line_no}: event {expected_index}: invalid epoch")
    ticks = item.get("pl_ticks")
    if not isinstance(ticks, int) or isinstance(ticks, bool) or not 0 <= ticks <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"{path}:{line_no}: event {expected_index}: invalid pl_ticks")
    host_ns = item.get("host_monotonic_ns")
    if not isinstance(host_ns, int) or isinstance(host_ns, bool) or host_ns < 0:
        raise ValueError(
            f"{path}:{line_no}: event {expected_index}: invalid host_monotonic_ns"
        )
    names = set(item["registers"])
    unknown = names - set(REGISTER_OFFSETS)
    missing = SNAPSHOT_REGISTER_NAMES - names
    if unknown:
        raise ValueError(
            f"{path}:{line_no}: event {expected_index}: unknown registers "
            f"{sorted(unknown)}"
        )
    if missing:
        raise ValueError(
            f"{path}:{line_no}: event {expected_index}: missing registers "
            f"{sorted(missing)}"
        )
    for name, raw in item["registers"].items():
        try:
            _u32(raw)
        except ValueError as exc:
            raise ValueError(
                f"{path}:{line_no}: event {expected_index}: {name}: {exc}"
            ) from exc
    expected = item.get("expected")
    if not isinstance(expected, dict) or not isinstance(expected.get("permit"), bool):
        raise ValueError(f"{path}:{line_no}: event {expected_index}: invalid expected")
    reasons = expected.get("reasons")
    if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
        raise ValueError(
            f"{path}:{line_no}: event {expected_index}: expected.reasons must be strings"
        )


def load_jsonl(path: Path) -> tuple[dict, list[dict]]:
    header = None
    records: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_no}: object required")
            if header is None:
                _validate_header(Path(path), line_no, item)
                header = item
            else:
                _validate_sample(Path(path), line_no, item, len(records))
                records.append(item)
    if header is None:
        raise ValueError(f"{path}: empty replay")
    if not records:
        raise ValueError(f"{path}: replay contains no samples")
    return header, records


class ReplayRegisterIO:
    """Read-only replay transport with CTRL snapshot/time-latch behavior."""

    def __init__(self, header: dict, records: list[dict]):
        contract_id = _u32(header.get("contract_id"))
        self.mem = {
            reg.ID_VERSION: contract_id,
            reg.STATUS: 3,
            reg.SNAP_EPOCH: 0,
        }
        self.records = records
        self.index = -1
        self.current: dict | None = None
        self._epoch_reads = 0

    def read32(self, offset: int) -> int:
        if offset == reg.SNAP_EPOCH and self.current is not None:
            self._epoch_reads += 1
            if self.current.get("fault") == "epoch_tear" and self._epoch_reads >= 2:
                return (self.mem[reg.SNAP_EPOCH] + 1) & 0xFFFF
        return self.mem.get(offset, 0) & 0xFFFFFFFF

    def write32(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        if offset != reg.CTRL:
            # Replays are observational; command writes are retained only for
            # deterministic tests and never reach a serial or motor device.
            self.mem[offset] = value
            return
        if value & 1:
            self.index += 1
            if self.index >= len(self.records):
                raise ContractError("replay exhausted")
            self.current = self.records[self.index]
            registers = self.current["registers"]
            for name, raw in registers.items():
                if name not in REGISTER_OFFSETS:
                    raise ValueError(f"unknown register name in replay: {name}")
                self.mem[REGISTER_OFFSETS[name]] = _u32(raw)
            expected_epoch = int(self.current.get("epoch", self.index + 1)) & 0xFFFF
            if self.current.get("fault") != "epoch_freeze":
                self.mem[reg.SNAP_EPOCH] = expected_epoch
            self._epoch_reads = 0
        if value & 2:
            if self.current is None:
                raise ContractError("time latch requested before first replay sample")
            ticks = int(self.current["pl_ticks"])
            if not 0 <= ticks <= 0xFFFFFFFFFFFFFFFF:
                raise ValueError("pl_ticks out of uint64 range")
            self.mem[reg.TS_SNAP_LO] = ticks & 0xFFFFFFFF
            self.mem[reg.TS_SNAP_HI] = ticks >> 32
            self.mem[reg.STATUS] = 3


def snapshot_registers(shot) -> dict[str, int]:
    def meta(sample):
        return (int(sample.valid) << 31) | sample.sequence

    values = {
        "US_DATA": shot.ultrasonic.data & 0xFFFFFFFF,
        "US_TS": shot.ultrasonic.timestamp,
        "US_META": meta(shot.ultrasonic),
        "IR_STATUS": shot.infrared.data & 0xFFFFFFFF,
        "IR_TS": shot.infrared.timestamp,
        "IR_META": meta(shot.infrared),
        "QEI0_POS": shot.qei0_position & 0xFFFFFFFF,
        "QEI0_PERIOD": shot.qei0_period,
        "QEI0_VEL": shot.qei0.data & 0xFFFFFFFF,
        "QEI0_TS": shot.qei0.timestamp,
        "QEI0_META": meta(shot.qei0),
        "QEI1_POS": shot.qei1_position & 0xFFFFFFFF,
        "QEI1_PERIOD": shot.qei1_period,
        "QEI1_VEL": shot.qei1.data & 0xFFFFFFFF,
        "QEI1_TS": shot.qei1.timestamp,
        "QEI1_META": meta(shot.qei1),
        "RISK_STATE": shot.risk_state,
        "RISK_REQUIRED_MM": shot.risk_required_mm,
        "RISK_TS": shot.risk.timestamp,
        "RISK_META": meta(shot.risk),
        "CMD_STATE": shot.command_state,
        "CMD_TS": shot.command_timestamp,
    }
    for i, odo in enumerate((shot.odometry0, shot.odometry1)):
        fields = {
            "DISP_LO": odo.displacement_q16 & 0xFFFFFFFF,
            "DISP_HI": (odo.displacement_q16 >> 32) & 0xFFFFFFFF,
            "PATH_LO": odo.travelled_q16 & 0xFFFFFFFF,
            "PATH_HI": odo.travelled_q16 >> 32,
            "TS": odo.timestamp,
            "META": (int(odo.valid) << 31) | (int(odo.fault) << 30) | odo.sequence,
            "EPOCH": odo.epoch,
        }
        values.update({f"ODOM{i}_{key}": value for key, value in fields.items()})
    return values


def record(io, output: Path, count: int, *, source: str, hardware: bool) -> None:
    client = PerceptionClient(io)
    client.verify_contract()
    header = {
        "type": "header", "schema": SCHEMA,
        "contract_version": reg.CONTRACT_VERSION,
        "contract_id": f"0x{reg.INTEGRATED_ID:08X}",
        "tick_hz": TICK_HZ, "source": source, "hardware": bool(hardware),
    }
    with Path(output).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(header, separators=(",", ":")) + "\n")
        for index in range(count):
            now, shot, decision = client.sample_and_decide()
            item = {
                "type": "sample", "index": index, "epoch": shot.epoch,
                "pl_ticks": now, "host_monotonic_ns": time.monotonic_ns(),
                "registers": snapshot_registers(shot),
                "expected": {"permit": decision.permit, "reasons": list(decision.reasons)},
            }
            stream.write(json.dumps(item, separators=(",", ":")) + "\n")


def replay(path: Path) -> list[tuple[dict, object, object]]:
    header, records = load_jsonl(path)
    io = ReplayRegisterIO(header, records)
    client = PerceptionClient(io, snapshot_attempts=1)
    client.verify_contract()
    results = []
    for record_item in records:
        now, shot, decision = client.sample_and_decide()
        expected = record_item.get("expected")
        if expected is not None:
            if bool(expected.get("permit")) != decision.permit:
                raise ContractError(
                    f"event {record_item.get('index')}: permit={decision.permit}, "
                    f"expected={expected.get('permit')}; raw={record_item['registers']}"
                )
            expected_reasons = tuple(expected.get("reasons", []))
            if expected_reasons != decision.reasons:
                raise ContractError(
                    f"event {record_item.get('index')}: reasons={decision.reasons}, "
                    f"expected={expected_reasons}; raw={record_item['registers']}"
                )
        results.append((record_item, shot, decision))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("replay", "pynq"), default="replay")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base", type=lambda x: int(x, 0))
    parser.add_argument("--length", type=lambda x: int(x, 0), default=0x1000)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        if args.transport == "replay":
            if args.input is None:
                parser.error("--input is required for replay")
            results = replay(args.input)
            print(f"REPLAY_PASS input={args.input} schema={SCHEMA} "
                  f"contract=0x{reg.INTEGRATED_ID:08X} events={len(results)}")
        else:
            if args.base is None or args.output is None:
                parser.error("--base and --output are required for pynq recording")
            io = PynqMMIO(args.base, args.length)
            record(io, args.output, args.count, source="pynq-mmio", hardware=True)
            print(f"RECORD_PASS output={args.output} count={args.count}")
        return 0
    except (ContractError, OSError, RuntimeError, ValueError) as exc:
        source = args.input if args.transport == "replay" else args.output
        print(
            f"PERCEPTION_IO_FAIL input={source} schema={SCHEMA} "
            f"contract=0x{reg.INTEGRATED_ID:08X}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
