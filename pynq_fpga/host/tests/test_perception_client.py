import pathlib
import sys
import types
import unittest
from dataclasses import replace
from unittest import mock

HOST = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST))

import car_regs as reg
from perception_client import (
    ContractError, PerceptionClient, PerceptionSnapshot, PynqMMIO, Sample,
    QEI_SCALE_PROFILES, PROFILE_TT_48_ORIGINAL_WHEEL_FRONT_2,
    elapsed32, evaluate_snapshot, snapshot_to_link_sample,
)


class FakeIO:
    def __init__(self):
        self.mem = {reg.ID_VERSION: reg.INTEGRATED_ID, reg.SNAP_EPOCH: 7,
                    reg.STATUS: 3, reg.TS_SNAP_LO: 0xFFFFFFFE,
                    reg.TS_SNAP_HI: 1}
        self.freeze_epoch = False
        self.commands = []
        self.writes = []

    def read32(self, offset):
        return self.mem.get(offset, 0)

    def write32(self, offset, value):
        self.writes.append((offset, value))
        if offset == reg.CTRL and value & 1 and not self.freeze_epoch:
            self.mem[reg.SNAP_EPOCH] = (self.mem[reg.SNAP_EPOCH] + 1) & 0xFFFF
        if offset == reg.RISK_CMD:
            self.commands.append(value)
        self.mem[offset] = value


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.io = FakeIO()
        self.client = PerceptionClient(self.io, snapshot_attempts=2)

    def test_version_gate(self):
        self.client.verify_contract()
        self.io.mem[reg.ID_VERSION] ^= 1
        with self.assertRaises(ContractError):
            self.client.verify_contract()

    def test_snapshot_and_signed_velocity(self):
        self.io.mem.update({
            reg.US_DATA: 888, reg.US_TS: 0xFFFFFFF8, reg.US_META: 0x80000022,
            reg.IR_STATUS: 4, reg.IR_TS: 9, reg.IR_META: 0x80000023,
            reg.QEI0_VEL: 0xFC180000, reg.QEI0_TS: 10, reg.QEI0_META: 0x80000024,
            reg.QEI1_VEL: 0x03E80000, reg.QEI1_TS: 11, reg.QEI1_META: 0x80000025,
            reg.RISK_STATE: 1, reg.RISK_TS: 12, reg.RISK_META: 0x80000026,
            reg.RISK_REQUIRED_MM: 1202,
        })
        shot = self.client.snapshot()
        self.assertEqual(shot.epoch, 8)
        self.assertEqual(shot.ultrasonic.sequence, 0x22)
        self.assertTrue(shot.ultrasonic.valid)
        self.assertEqual(shot.qei0_velocity_q16, -1000 << 16)
        self.assertEqual(shot.qei1_velocity_q16, 1000 << 16)
        self.assertEqual(shot.risk_required_mm, 1202)

    def test_snapshot_timeout_is_failure(self):
        self.io.freeze_epoch = True
        with self.assertRaises(ContractError):
            self.client.snapshot()

    def test_command_encoding_and_wrap_age(self):
        self.client.set_command(forward=True, valid=True)
        self.client.set_command(forward=False, valid=False)
        self.assertEqual(self.io.commands, [3, 0])
        self.assertEqual(elapsed32(5, 0xFFFFFFF8), 13)

    def test_atomic_pl_time(self):
        self.assertEqual(self.client.read_pl_ticks64(), 0x1FFFFFFFE)

    def test_mmio_adapter_and_bounds(self):
        calls = []

        class MMIO:
            def __init__(self, base, length):
                calls.append(("init", base, length))
            def read(self, offset, size):
                calls.append(("read", offset, size))
                return 0x1_89ABCDEF
            def write(self, offset, value):
                calls.append(("write", offset, value))

        with mock.patch.dict(sys.modules, {"pynq": types.SimpleNamespace(MMIO=MMIO)}):
            io = PynqMMIO(0x40000000, 0x1000)
            self.assertEqual(io.read32(0x144), 0x89ABCDEF)
            io.write32(0x140, 0x1_00000003)
            with self.assertRaises(ValueError):
                io.read32(2)
            with self.assertRaises(ValueError):
                io.write32(0x1000, 0)
        self.assertEqual(calls, [
            ("init", 0x40000000, 0x1000),
            ("read", 0x144, 4),
            ("write", 0x140, 3),
        ])

    def test_sequence_wrap_and_link_sample_preserves_ir(self):
        self.io.mem.update({
            reg.US_DATA: 1000, reg.US_TS: 100, reg.US_META: 0x8000FFFF,
            reg.IR_STATUS: 5, reg.IR_TS: 1, reg.IR_META: 0x8000FFFF,
            reg.QEI0_META: 0x8000FFFF, reg.QEI1_META: 0x8000FFFF,
            reg.RISK_META: 0x8000FFFF,
        })
        shot = self.client.snapshot()
        self.assertEqual(shot.ultrasonic.sequence, 0xFFFF)
        sample = snapshot_to_link_sample(shot, 101)
        self.assertTrue(sample.valid)
        self.assertEqual((sample.distance_mm, sample.infrared_mask), (1000, 1))
        self.io.mem[reg.US_META] = 0x80000000
        self.assertEqual(self.client.snapshot().ultrasonic.sequence, 0)

    def test_age_boundary_and_static_ir_semantics(self):
        valid = lambda ts, data=0: Sample(data, ts, True, 1)
        shot = PerceptionSnapshot(
            epoch=1, ultrasonic=valid(100, 1000), infrared=valid(0, 4),
            qei0_position=0, qei0_period=0, qei0_velocity_q16=0, qei0=valid(100),
            qei1_position=0, qei1_period=0, qei1_velocity_q16=0, qei1=valid(100),
            risk_state=0, risk_required_mm=100, risk=valid(100),
            command_state=2, command_timestamp=100,
        )
        self.assertTrue(evaluate_snapshot(shot, 100 + 19_999_999).permit)
        decision = evaluate_snapshot(shot, 100 + 20_000_000)
        self.assertFalse(decision.permit)
        self.assertIn("us_stale", decision.reasons)
        self.assertNotIn("ir_stale", decision.reasons)

        now = 30_000_000
        fresh = lambda data=0: Sample(data, now, True, 2)
        base = PerceptionSnapshot(
            epoch=2, ultrasonic=fresh(1000), infrared=fresh(4),
            qei0_position=0, qei0_period=0, qei0_velocity_q16=0, qei0=fresh(),
            qei1_position=0, qei1_period=0, qei1_velocity_q16=0, qei1=fresh(),
            risk_state=0, risk_required_mm=100, risk=fresh(),
            command_state=2, command_timestamp=now,
        )
        q0_stale = replace(base, qei0=Sample(0, now - 20_000_000, True, 3))
        self.assertIn("qei0_stale", evaluate_snapshot(q0_stale, now).reasons)
        q1_stale = replace(base, qei1=Sample(0, now - 20_000_000, True, 3))
        self.assertIn("qei1_stale", evaluate_snapshot(q1_stale, now).reasons)
        ir_invalid = replace(base, infrared=Sample(0, now, True, 3))
        self.assertTrue(evaluate_snapshot(ir_invalid, now).permit)
        self.assertTrue(snapshot_to_link_sample(ir_invalid, now).valid)
        for mask in (1,2,3):
            warning=replace(base,infrared=Sample(mask|4,now,True,3))
            self.assertTrue(evaluate_snapshot(warning,now).permit)
            self.assertEqual(snapshot_to_link_sample(warning,now).infrared_mask,mask)
        missing=replace(base,infrared=Sample(0,0,False,3))
        self.assertTrue(evaluate_snapshot(missing,now).permit)
        self.assertTrue(snapshot_to_link_sample(missing,now).valid)


class QeiScaleConfigTests(unittest.TestCase):
    """configure_qei_scales / configure_qei_profile: explicit-only writes."""

    def setUp(self):
        self.io = FakeIO()
        self.client = PerceptionClient(self.io, snapshot_attempts=2)

    def test_scales_write_generated_addresses_in_order_and_read_back(self):
        result = self.client.configure_qei_scales(123456, 654321)
        self.assertEqual(result, (123456, 654321))
        self.assertEqual(
            self.io.writes,
            [(reg.QEI0_SCALE, 123456), (reg.QEI1_SCALE, 654321)],
        )
        self.assertEqual(self.io.mem[reg.QEI0_SCALE], 123456)
        self.assertEqual(self.io.mem[reg.QEI1_SCALE], 654321)

    def test_left_and_right_are_independent(self):
        self.client.configure_qei_scales(1111, 999999)
        self.assertEqual(self.io.mem[reg.QEI0_SCALE], 1111)
        self.assertEqual(self.io.mem[reg.QEI1_SCALE], 999999)

    def test_invalid_scales_fail_without_writing(self):
        for left, right in ((0, 100), (100, 0), (-5, 100), (100, 0x100000000)):
            with self.assertRaises(ValueError):
                self.client.configure_qei_scales(left, right)
        self.assertEqual(self.io.writes, [])
        for bad in (0, -1, 0x100000000, 1.5, "5362", None, True):
            with self.assertRaises(ValueError):
                self.client.configure_qei_scales(bad, bad)
        self.assertEqual(self.io.writes, [])

    def test_contract_id_gate_blocks_scale_writes(self):
        self.io.mem[reg.ID_VERSION] = reg.INTEGRATED_ID ^ 0xFF
        with self.assertRaises(ContractError):
            self.client.configure_qei_scales(5362, 5362)
        self.assertEqual(self.io.writes, [])
        self.assertNotIn(reg.QEI0_SCALE, self.io.mem)

    def test_readback_mismatch_fails_closed(self):
        class FlakyIO(FakeIO):
            corrupt_once = True

            def write32(self, offset, value):
                if offset == reg.QEI1_SCALE and value and self.corrupt_once:
                    self.corrupt_once = False
                    value ^= 0x1  # register does not hold the written value
                super().write32(offset, value)

        io = FlakyIO()
        client = PerceptionClient(io, snapshot_attempts=2)
        with self.assertRaises(ContractError):
            client.configure_qei_scales(5362, 5362)
        self.assertEqual(io.mem[reg.QEI0_SCALE], 0)
        self.assertEqual(io.mem[reg.QEI1_SCALE], 0)

    def test_second_write_exception_clears_both_channels(self):
        class FailOnceIO(FakeIO):
            failed = False

            def write32(self, offset, value):
                if offset == reg.QEI1_SCALE and value and not self.failed:
                    self.failed = True
                    raise OSError("injected right-channel write failure")
                super().write32(offset, value)

        io = FailOnceIO()
        client = PerceptionClient(io, snapshot_attempts=2)
        with self.assertRaisesRegex(ContractError, "both channels invalidated"):
            client.configure_qei_scales(5362, 5362)
        self.assertEqual(io.mem[reg.QEI0_SCALE], 0)
        self.assertEqual(io.mem[reg.QEI1_SCALE], 0)

    def test_cleanup_failure_is_reported_as_uncertain_state(self):
        class StuckRightIO(FakeIO):
            def write32(self, offset, value):
                if offset == reg.QEI1_SCALE:
                    raise OSError("right register inaccessible")
                super().write32(offset, value)

        client = PerceptionClient(StuckRightIO(), snapshot_attempts=2)
        with self.assertRaisesRegex(ContractError, "cleanup incomplete"):
            client.configure_qei_scales(5362, 5362)

    def test_explicit_invalidate_clears_both_channels(self):
        self.io.mem[reg.QEI0_SCALE] = 111
        self.io.mem[reg.QEI1_SCALE] = 222
        self.client.invalidate_qei_scales()
        self.assertEqual(self.io.mem[reg.QEI0_SCALE], 0)
        self.assertEqual(self.io.mem[reg.QEI1_SCALE], 0)

    def test_profile_writes_temporary_5362_to_both_channels(self):
        result = self.client.configure_qei_profile(
            PROFILE_TT_48_ORIGINAL_WHEEL_FRONT_2
        )
        nominal = 5362  # 1:48, crude 65mm, 2496 counts -> round(pi*65/2496*65536)
        self.assertEqual(result, (nominal, nominal))
        self.assertEqual(self.io.mem[reg.QEI0_SCALE], nominal)
        self.assertEqual(self.io.mem[reg.QEI1_SCALE], nominal)

    def test_profile_values_stay_consistent_with_calculator_preset(self):
        import qei_calibration
        scales = QEI_SCALE_PROFILES[PROFILE_TT_48_ORIGINAL_WHEEL_FRONT_2]
        self.assertEqual(
            scales["left_scale"],
            qei_calibration.NOMINAL_PRESETS["TT_48_65MM"]["scale"],
        )
        self.assertEqual(
            scales["right_scale"],
            qei_calibration.NOMINAL_PRESETS["TT_48_65MM"]["scale"],
        )
        self.assertTrue(scales["temporary"])

    def test_unknown_profile_fails_without_writing(self):
        with self.assertRaises(ContractError):
            self.client.configure_qei_profile("TT_90_ORIGINAL_WHEEL")
        self.assertEqual(self.io.writes, [])
        self.assertNotIn(reg.QEI0_SCALE, self.io.mem)
        self.assertNotIn(reg.QEI1_SCALE, self.io.mem)

    def test_no_writes_at_construction_or_import(self):
        fresh = FakeIO()
        PerceptionClient(fresh, snapshot_attempts=2)
        self.assertEqual(fresh.writes, [])
        self.assertNotIn(reg.QEI0_SCALE, fresh.mem)
        self.assertNotIn(reg.QEI1_SCALE, fresh.mem)


if __name__ == "__main__":
    unittest.main()
