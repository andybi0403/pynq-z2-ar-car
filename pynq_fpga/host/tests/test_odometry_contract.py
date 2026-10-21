import json
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import car_regs as reg
from perception_client import ContractError, PerceptionClient, Odometry
from perception_replay import snapshot_registers, replay
from calibration_config import WheelCalibration, CalibrationConfig
from test_perception_client import FakeIO


class OdometryContractTests(unittest.TestCase):
    def test_display_identity_retries_instead_of_combining_two_sofs(self):
        class DisplayIO(FakeIO):
            def __init__(self):
                super().__init__();self.reads=0;self.mem[reg.DISPLAY_FRAME_ID]=55
            def read32(self,offset):
                if offset==reg.DISPLAY_TAG_COUNT:
                    self.reads+=1
                    if self.reads==2:self.mem[reg.DISPLAY_FRAME_ID]=66
                    return 10 if self.reads==1 else 11
                return super().read32(offset)
        io=DisplayIO();result=PerceptionClient(io).display_diagnostics()
        self.assertEqual(result['DISPLAY_FRAME_ID'],66)
        self.assertEqual(result['DISPLAY_TAG_COUNT'],11)
        self.assertEqual(io.reads,4)

    def test_display_identity_churn_fails_closed(self):
        class DisplayIO(FakeIO):
            def __init__(self):super().__init__();self.count=0
            def read32(self,offset):
                if offset==reg.DISPLAY_TAG_COUNT:
                    self.count+=1;return self.count
                return super().read32(offset)
        with self.assertRaisesRegex(ContractError,'display frame identity changed'):
            PerceptionClient(DisplayIO(),snapshot_attempts=2).display_diagnostics()

    def test_display_status_preserves_received_age_and_invalidates_stale(self):
        io=FakeIO();client=PerceptionClient(io)
        client.publish_car_status({'lock':0,'fault':0x1234},.25)
        self.assertEqual(io.writes[-2:],[(reg.DISPLAY_CAR_AGE,25_000_000),
                                        (reg.DISPLAY_CAR_STATE,0x12340002)])
        client.publish_car_status({'lock':0,'fault':0},.7)
        self.assertEqual(io.mem[reg.DISPLAY_CAR_STATE],0)
        client.publish_car_status(None,None)
        self.assertEqual(io.mem[reg.DISPLAY_CAR_STATE],0)
        with self.assertRaises(ValueError):
            client.publish_car_status({'lock':2,'fault':0},0)
    def test_signed_64bit_and_unsigned_path_round_trip(self):
        io = FakeIO()
        io.mem.update({reg.ODOM0_DISP_LO: 0xFFFF0000,
                       reg.ODOM0_DISP_HI: 0xFFFFFFFF,
                       reg.ODOM0_PATH_LO: 65536, reg.ODOM0_PATH_HI: 2,
                       reg.ODOM0_META: 0x8000FFFF, reg.ODOM0_EPOCH: 65535,
                       reg.ODOM1_META: 0xC0000001})
        shot = PerceptionClient(io).snapshot()
        self.assertEqual(shot.odometry0.displacement_q16, -65536)
        self.assertEqual(shot.odometry0.travelled_q16, (2 << 32) + 65536)
        self.assertEqual(shot.odometry0.sequence, 65535)
        self.assertFalse(shot.odometry_valid)
        raw = snapshot_registers(shot)
        self.assertEqual(raw['ODOM0_DISP_HI'], 0xFFFFFFFF)
        self.assertEqual(raw['ODOM0_PATH_HI'], 2)
        shot = replace(shot, odometry1=Odometry(3*65536, 3*65536, valid=True))
        self.assertTrue(shot.odometry_valid)
        self.assertEqual(shot.displacement_q16, 65536)

    def test_odometry_tear_retries_whole_snapshot(self):
        class TearIO(FakeIO):
            def read32(self, offset):
                if offset == reg.ODOM1_EPOCH:
                    self.mem[reg.SNAP_EPOCH] += 1
                return super().read32(offset)
        with self.assertRaisesRegex(ContractError, 'stable'):
            PerceptionClient(TearIO(), snapshot_attempts=2).snapshot()

    def test_legacy_id_rejected_before_use(self):
        io = FakeIO()
        io.mem[reg.ID_VERSION] = 0xC4251006
        with self.assertRaisesRegex(ContractError, 'mismatch'):
            PerceptionClient(io).verify_contract()

    def test_replay_cannot_omit_odometry(self):
        fixture = Path(__file__).resolve().parents[1] / 'replays/safety_timeline_v1.jsonl'
        self.assertEqual(len(replay(fixture)), 6)
        rows = [json.loads(line) for line in fixture.read_text().splitlines()]
        del rows[1]['registers']['ODOM0_DISP_HI']
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'broken.jsonl'
            path.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'ODOM0_DISP_HI'):
                replay(path)

    def test_reset_requires_fresh_stationary_and_new_zero_epoch(self):
        class ResetIO(FakeIO):
            def write32(self, offset, value):
                super().write32(offset, value)
                if offset == reg.ODOM_CTRL:
                    for i in range(2):
                        self.mem[getattr(reg, f'ODOM{i}_EPOCH')] = 0
                        for suffix in ('DISP_LO','DISP_HI','PATH_LO','PATH_HI'):
                            self.mem[getattr(reg, f'ODOM{i}_{suffix}')] = 0
        io = ResetIO()
        client = PerceptionClient(io)
        with self.assertRaisesRegex(ContractError, 'fresh zero'):
            client.reset_odometry()
        io.mem.update({reg.QEI0_META: 0x80000001, reg.QEI1_META: 0x80000001,
                       reg.QEI0_TS: 0xFFFFFFFE, reg.QEI1_TS: 0xFFFFFFFE,
                       reg.ODOM0_EPOCH: 65535, reg.ODOM1_EPOCH: 65535,
                       reg.ODOM0_DISP_LO: 33})
        client.reset_odometry()
        io.mem[reg.QEI0_VEL] = 1
        with self.assertRaisesRegex(ContractError, 'fresh zero'):
            client.reset_odometry()


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.config = CalibrationConfig(WheelCalibration(5362, direction=1),
                                        WheelCalibration(5400, filter_ticks=8),
                                        'loaded rollout, operator sample', True)

    def test_save_load_and_atomic_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'calibration.json'
            self.config.save(path)
            self.assertEqual(CalibrationConfig.load(path), self.config)
            io = FakeIO()
            payload = self.config.apply(PerceptionClient(io), motor_disconnected=True)
            self.assertTrue(payload['measured'])
            self.assertEqual(io.mem[reg.QEI0_DIR], 1)
            self.assertEqual(io.mem[reg.QEI1_FILTER], 8)
            self.assertEqual(io.mem[reg.QEI0_SCALE], 5362)
            self.assertEqual(io.commands, [0])
            scale_writes = [(off, value) for off, value in io.writes
                            if off in (reg.QEI0_SCALE, reg.QEI1_SCALE)]
            self.assertEqual(scale_writes[:2], [(reg.QEI0_SCALE, 0),(reg.QEI1_SCALE,0)])

    def test_config_failure_invalidates_both_wheels(self):
        class BrokenIO(FakeIO):
            def read32(self, offset):
                return 99 if offset == reg.QEI1_FILTER else super().read32(offset)
        io = BrokenIO()
        with self.assertRaisesRegex(ContractError, 'scales cleared=True'):
            self.config.apply(PerceptionClient(io), motor_disconnected=True)
        self.assertEqual(io.mem[reg.QEI0_SCALE], 0)
        self.assertEqual(io.mem[reg.QEI1_SCALE], 0)

    def test_no_hardware_access_without_explicit_disconnection(self):
        io = FakeIO()
        with self.assertRaisesRegex(ValueError, 'disconnected'):
            self.config.apply(PerceptionClient(io))
        self.assertEqual(io.writes, [])

    def test_bad_fields_and_wrong_wheel_mapping_are_rejected(self):
        for kwargs in ({'scale':True}, {'scale':0}, {'scale':1,'direction':2},
                       {'scale':1,'zero_ticks':20_000_000}):
            with self.assertRaises(ValueError):
                WheelCalibration(**kwargs)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'bad.json'
            item = self.config.payload()
            item['channel_map']['left'] = 'QEI1_right_front'
            path.write_text(json.dumps(item), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'mapping'):
                CalibrationConfig.load(path)


if __name__ == '__main__':
    unittest.main()
