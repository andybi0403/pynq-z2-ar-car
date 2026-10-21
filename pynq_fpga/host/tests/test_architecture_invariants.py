import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
RTL = ROOT / "fpga" / "rtl"
SAFE_CAR = REPO / "stm32预备程序" / "Source" / "APP" / "safe_car.c"
ENCODER_FINDINGS = REPO / "docs" / "03_硬件与接线" / \
    "10_霍尔编码器TT马达电气与QEI参数核定_20260919.md"


class ArchitectureInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.top = (RTL / "car_perception_top.v").read_text(encoding="utf-8")
        cls.osd = (RTL / "car_axis_osd.v").read_text(encoding="utf-8")

    def test_one_timebase_and_one_axi_frontend(self):
        self.assertEqual(len(re.findall(r"\bcar_time_counter\b[^;]*\btimebase\s*\(", self.top, re.S)), 1)
        self.assertEqual(len(re.findall(r"\baxil_reg_if\s*#\s*\(", self.top)), 1)

    def test_integrated_top_uses_cores_not_wrapper_tops(self):
        for wrapper in ("car_axil_regs", "car_sensors_top", "car_qei_top"):
            self.assertIsNone(re.search(rf"\b{wrapper}\s+\w+\s*\(", self.top), wrapper)
        for core in ("car_sensors_core", "car_qei_core", "car_risk_core"):
            self.assertIsNotNone(re.search(rf"\b{core}\s+\w+\s*\(", self.top), core)

    def test_one_global_snapshot_trigger_and_epoch(self):
        self.assertEqual(len(re.findall(r"\bwire\s+snap_trigger\s*=", self.top)), 1)
        self.assertEqual(len(re.findall(r"if\s*\(snap_trigger\)\s*begin", self.top)), 1)
        self.assertIn("snap_epoch<=snap_epoch+1'b1", self.top)

    def test_osd_is_pure_axis_and_keeps_validity_separate(self):
        self.assertNotIn("axil_reg_if", self.osd)
        self.assertNotIn("car_time_counter", self.osd)
        self.assertIn("state_distance_valid", self.osd)
        self.assertIn("state_speed_valid", self.osd)
        self.assertNotIn("state_sensor_valid", self.osd)


class TwoWheelEncoderArchitectureTests(unittest.TestCase):
    """Freeze the user-confirmed two-front-encoder, two-sided drive facts.

    The STM32 runtime drives LEFT and RIGHT vehicle sides (front+rear motors
    of one side share one TB6612 channel); the PL provides exactly two QEI
    channels for the two ENCODED front wheels.  No rear-wheel encoder or
    per-wheel PWM may appear in any authoritative source.
    """

    @classmethod
    def setUpClass(cls):
        cls.safe_car = SAFE_CAR.read_text(encoding="utf-8", errors="replace")
        cls.top = (RTL / "car_perception_top.v").read_text(encoding="utf-8")
        cls.register_map = json.loads(
            (RTL.parent / "registers" / "register_map.json")
            .read_text(encoding="utf-8")
        )

    def test_stm32_drive_stays_two_sided(self):
        # One motors(left, right) entry point; exactly two channel() calls.
        self.assertEqual(
            len(re.findall(r"static void motors\(int left, int right\)", self.safe_car)),
            1,
        )
        self.assertEqual(len(re.findall(r"\bchannel\((left|right),", self.safe_car)), 2)
        # No per-wheel channels (front/rear independent PWM) exist.
        self.assertIsNone(re.search(r"(Front_|Rear_|MotoC|MotoD)", self.safe_car))
        self.assertNotIn("QEI", self.safe_car)

    def test_pl_has_exactly_two_qei_channels(self):
        ports = re.findall(r"input wire (qei\d_[ab])", self.top)
        self.assertEqual(sorted(ports), ["qei0_a", "qei0_b", "qei1_a", "qei1_b"])
        self.assertIsNone(re.search(r"\bqei[23]_", self.top))
        scale_regs = [r["name"] for r in self.register_map["registers"]
                      if r["name"].startswith("QEI")]
        for suffix in ("SCALE",):
            named = [n for n in scale_regs if n.endswith(suffix)]
            self.assertEqual(named, [f"QEI0_{suffix}", f"QEI1_{suffix}"])

    def test_qei_channel_semantics_documented(self):
        text = ENCODER_FINDINGS.read_text(encoding="utf-8")
        self.assertIn("QEI0", text)
        self.assertIn("左前", text)
        self.assertIn("QEI1", text)
        self.assertIn("右前", text)
        self.assertIn("共用", text)
        self.assertIn("TT_48_ORIGINAL_WHEEL_FRONT_2", text)


if __name__ == "__main__":
    unittest.main()
