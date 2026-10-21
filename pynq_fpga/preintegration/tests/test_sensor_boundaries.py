"""PS calibration must agree with the actual 64-cycle PL divider contract."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'host'))
from calibration_config import WheelCalibration


class SensorBoundaryTests(unittest.TestCase):
    def test_too_short_zero_observation_rejected_before_mmio(self):
        for timeout in (0,1,64,65,True):
            with self.assertRaises(ValueError):WheelCalibration(scale=5362,zero_ticks=timeout)
        self.assertEqual(WheelCalibration(scale=5362,zero_ticks=66).zero_ticks,66)
        self.assertEqual(WheelCalibration(scale=5362,zero_ticks=19_000_000).zero_ticks,19_000_000)
    def test_unmeasured_scale_cannot_become_valid_calibration(self):
        for scale in (0,-1,0x100000000,True):
            with self.assertRaises(ValueError):WheelCalibration(scale=scale)


if __name__=='__main__':unittest.main()
