import math
import pathlib
import sys
import unittest

HOST = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST))

import qei_calibration as qc


class QeiCalibrationTests(unittest.TestCase):
    def test_counts_per_wheel_rev_matches_vendor_manual(self):
        # Vendor manual P6/P8: 1:48 -> 13x48x4=2496, 1:90 -> 13x90x4=4680.
        self.assertEqual(qc.counts_per_wheel_rev(48), 2496)
        self.assertEqual(qc.counts_per_wheel_rev(90), 4680)

    def test_four_nominal_presets_match_independent_recalculation(self):
        expected = {
            "TT_48_60MM": (48, 60.0),
            "TT_48_65MM": (48, 65.0),
            "TT_90_60MM": (90, 60.0),
            "TT_90_65MM": (90, 65.0),
        }
        self.assertEqual(set(qc.NOMINAL_PRESETS), set(expected))
        for name, (gear, diameter) in expected.items():
            counts = 13 * gear * 4
            exact = math.pi * diameter / counts * 65536
            preset = qc.NOMINAL_PRESETS[name]
            self.assertEqual(preset["counts_per_wheel_rev"], counts, name)
            self.assertEqual(preset["scale"], round(exact), name)
            self.assertEqual(preset["scale_hex"], f"0x{round(exact):08X}", name)

    def test_reference_table_values(self):
        # Cross-checked against an independent one-off script run.
        self.assertEqual(qc.NOMINAL_PRESETS["TT_48_60MM"]["scale"], 4949)
        self.assertEqual(qc.NOMINAL_PRESETS["TT_48_65MM"]["scale"], 5362)
        self.assertEqual(qc.NOMINAL_PRESETS["TT_90_60MM"]["scale"], 2640)
        self.assertEqual(qc.NOMINAL_PRESETS["TT_90_65MM"]["scale"], 2860)

    def test_scale_from_arbitrary_measured_rollout(self):
        counts = qc.counts_per_wheel_rev(48)
        exact = 205.5 / counts * 65536
        self.assertEqual(qc.scale_from_rollout_mm(205.5, counts), round(exact))

    def test_scale_from_measurements_uses_distance_over_revolutions(self):
        counts = qc.counts_per_wheel_rev(48)
        rollout = 2000.0 / 10.0
        self.assertEqual(
            qc.scale_from_measurements(2000.0, 10.0, counts),
            round(rollout / counts * 65536),
        )
        # Left and right wheels calibrate independently.
        self.assertNotEqual(
            qc.scale_from_measurements(2040.0, 10.0, counts),
            qc.scale_from_measurements(2010.0, 10.0, counts),
        )

    def test_decode_scale_q16_16_error(self):
        scale = qc.NOMINAL_PRESETS["TT_48_65MM"]["scale"]
        mm_per_count = qc.decode_scale(scale)
        self.assertAlmostEqual(mm_per_count, scale / 65536)
        true_mm = math.pi * 65.0 / 2496
        self.assertLess(abs(mm_per_count - true_mm) / true_mm, 1e-4)

    def test_invalid_inputs_are_rejected(self):
        for bad_gear in (0, -48):
            with self.assertRaises(ValueError):
                qc.counts_per_wheel_rev(bad_gear)
        with self.assertRaises(ValueError):
            qc.counts_per_wheel_rev(48.0)
        for bad_diameter in (0.0, -65.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                qc.scale_from_diameter_mm(bad_diameter, 2496)
        for bad_rollout in (0.0, -1.0, float("nan")):
            with self.assertRaises(ValueError):
                qc.scale_from_rollout_mm(bad_rollout, 2496)
        for args in ((0.0, 10.0), (1000.0, 0.0), (1000.0, -1.0)):
            with self.assertRaises(ValueError):
                qc.scale_from_measurements(*args, 2496)
        with self.assertRaises(ValueError):
            qc.scale_from_rollout_mm(200.0, 0)
        # Positive finite mechanical inputs can still quantize outside the
        # unsigned Q16.16 register domain; reject rather than return 0/overflow.
        with self.assertRaises(ValueError):
            qc.scale_from_rollout_mm(1e-12, 2496)
        with self.assertRaises(ValueError):
            qc.scale_from_rollout_mm(1e12, 1)
        for bad_scale in (0, -1, 0x100000000):
            with self.assertRaises(ValueError):
                qc.decode_scale(bad_scale)

    def test_module_has_no_hardware_side_effects(self):
        # Calculator only: the module must import nothing beyond math and
        # must not offer any register I/O helper of its own.
        import ast
        source = pathlib.Path(qc.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        imported.discard("__future__")
        self.assertEqual(imported, {"math"})
        self.assertNotIn("write32", source)
        self.assertNotIn("read32", source)


if __name__ == "__main__":
    unittest.main()
