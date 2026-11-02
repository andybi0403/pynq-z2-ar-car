"""Display data stays atomic, age-qualified, and separate from raw control."""
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'pynq_fpga/host'),str(ROOT/'pynq_fpga/preintegration/host')]
import car_regs as reg
from perception_client import PerceptionClient,ContractError
from perception_replay import snapshot_registers
from tactical_state import state_from_registers


class SnapshotIO:
    def __init__(self,tear=False):
        self.mem={reg.SNAP_EPOCH:1,reg.ID_VERSION:reg.INTEGRATED_ID,
                  reg.US_DATA:900,reg.US_META:0x80000001,reg.US_FILTER_MM:850,
                  reg.US_FILTER_META:0x80030009,reg.US_FILTER_LATEST_TS:95_000_000,
                  reg.US_FILTER_OLDEST_TS:75_000_000,reg.US_TREND_STATE:0x80000002,
                  reg.US_TREND_DT:50_000_000,reg.US_TREND_DELTA_MM:25,
                  reg.SNAP_CAR_STATE:3,reg.IR_STATUS:5,reg.IR_META:0x80000004,
                  reg.IR_TS:99_000_000}
        self.tear=tear
        self.writes=[]
    def write32(self,offset,value):
        self.writes.append((offset,value))
        if offset==reg.CTRL and value==1:self.mem[reg.SNAP_EPOCH]+=1
    def read32(self,offset):
        if offset==reg.US_FILTER_MM and self.tear:self.mem[reg.SNAP_EPOCH]+=1
        return self.mem.get(offset,0)


class TacticalSnapshotTests(unittest.TestCase):
    def test_new_registers_survive_snapshot_and_replay_without_changing_raw(self):
        io=SnapshotIO();shot=PerceptionClient(io).snapshot()
        raw=snapshot_registers(shot);state=state_from_registers(raw,100_000_000)
        self.assertEqual(shot.ultrasonic.data,900)
        self.assertEqual(state['filtered_mm'],850)
        self.assertEqual(state['sample_sequence'],9)
        self.assertEqual(state['sample_count'],3)
        self.assertEqual(state['trend'],'approaching')
        self.assertEqual(state['ir_mask'],1)
        self.assertTrue(state['ir_valid'] and state['car_valid'] and state['car_locked'])
        self.assertEqual(io.writes,[(reg.CTRL,1)])
        self.assertEqual(len(shot.display_processing),11)

    def test_torn_processing_data_rejects_whole_snapshot(self):
        with self.assertRaisesRegex(ContractError,'stable'):
            PerceptionClient(SnapshotIO(tear=True),snapshot_attempts=2).snapshot()

    def test_age_limits_and_future_data_reject_filter_and_trend(self):
        raw=snapshot_registers(PerceptionClient(SnapshotIO()).snapshot())
        for key,value in (('US_FILTER_LATEST_TS',80_000_000),
                          ('US_FILTER_OLDEST_TS',50_000_000),
                          ('US_FILTER_LATEST_TS',100_000_001),
                          ('US_FILTER_META',0x00030009)):
            state=state_from_registers({**raw,key:value},100_000_000)
            self.assertFalse(state['filter_valid'])
            self.assertFalse(state['trend_valid'])
            self.assertIsNone(state['filtered_mm'])
            self.assertEqual(state['trend'],'unknown')

    def test_low_word_wrap_preserves_recent_samples_and_signed_delta(self):
        raw={'US_FILTER_META':0x80030001,'US_FILTER_MM':487,
             'US_FILTER_LATEST_TS':0xfffffff0,'US_FILTER_OLDEST_TS':0xffffffe0,
             'US_TREND_STATE':0x80000003,'US_TREND_DELTA_MM':0xffffffe7}
        state=state_from_registers(raw,0x100000010)
        self.assertTrue(state['filter_valid'])
        self.assertEqual(state['trend'],'receding')
        self.assertEqual(state['closing_delta_mm'],-25)

    def test_missing_processing_never_promotes_raw_to_filtered(self):
        state=state_from_registers({'US_DATA':487,'US_META':0x80000001},100)
        self.assertFalse(state['filter_valid'])
        self.assertIsNone(state['filtered_mm'])
        self.assertFalse(state['ir_valid'] or state['car_valid'])

    def test_ir_expiry_is_independent_of_filter_age(self):
        raw=snapshot_registers(PerceptionClient(SnapshotIO()).snapshot())
        state=state_from_registers({**raw,'IR_TS':80_000_000},100_000_000)
        self.assertTrue(state['filter_valid'])
        self.assertFalse(state['ir_valid'])

    def test_video_ir_allows_snapshot_phase_without_renewing_raw_validity(self):
        raw=snapshot_registers(PerceptionClient(SnapshotIO()).snapshot())
        self.assertTrue(state_from_registers({**raw,'IR_TS':85_000_000},100_000_000)['ir_valid'])
        self.assertFalse(state_from_registers({**raw,'IR_TS':100_000_001},100_000_000)['ir_valid'])
        self.assertFalse(state_from_registers({**raw,'IR_META':0},100_000_000)['ir_valid'])
        self.assertFalse(state_from_registers({**raw,'IR_STATUS':1},100_000_000)['ir_valid'])


if __name__=='__main__':unittest.main()
