import sys, unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perception_client import PerceptionSnapshot, Sample, Odometry, evaluate_snapshot, PerceptionClient, ContractError
from qei_quality import QeiDisplayFilter, BENCH_FILTER_TICKS
import car_regs as reg
from test_perception_client import FakeIO


def shot(value=0, seq=1, ts=1000, info=0, fault=False, valid=True, epoch=0):
    s = Sample(value, ts, valid, seq)
    healthy = Sample(0, ts, True, seq)
    return PerceptionSnapshot(seq, Sample(1000, ts, True, seq), Sample(4, ts, True, seq),
        0, 1000, value, s, 0, 1000, value, s, 0, 100, healthy, 2, ts,
        Odometry(valid=True,fault=fault,epoch=epoch), Odometry(valid=True,epoch=epoch),
        info, 0)


class QeiQualityTests(unittest.TestCase):
    def test_new_illegal_edge_denies_valid_zero_and_saturation_cannot_clear_it(self):
        for info in (1 << 4, 255 << 4):
            decision = evaluate_snapshot(shot(info=info),1000)
            self.assertFalse(decision.permit)
            self.assertIn('qei0_illegal_transition',decision.reasons)
        self.assertIn('qei0_diagnostic_saturated',decision.reasons)

    def test_odometry_fault_alone_and_arithmetic_saturation_are_denied(self):
        self.assertIn('qei0_odometry_fault',evaluate_snapshot(shot(fault=True),1000).reasons)
        for speed in (-0x80000000,0x7fffffff):
            self.assertIn('qei0_velocity_saturated',evaluate_snapshot(shot(speed),1000).reasons)
        # A clean reverse wheel is still a measurement, not noise to erase.
        self.assertTrue(evaluate_snapshot(shot(-200*65536),1000).permit)

    def test_filter_rejection_diagnostic_alone_does_not_invalidate_clean_velocity(self):
        self.assertTrue(evaluate_snapshot(shot(info=255<<20),1000).permit)

    def test_divider_recovery_does_not_erase_overrun_diagnostic(self):
        from qei_quality import raw_fault_reasons
        for count in (1, 254, 255):
            with self.subTest(count=count):
                s=shot(info=count<<12)
                self.assertIn('qei0_velocity_overrun',evaluate_snapshot(s,1000).reasons)
                self.assertFalse(evaluate_snapshot(s,1000).permit)
                f=QeiDisplayFilter()
                self.assertIn('velocity_overrun',f.update(s,1000)[0].reasons)
                raw={'QEI0_INFO':count<<12,'QEI0_VEL':0,'ODOM0_META':0}
                self.assertIn('velocity_overrun',raw_fault_reasons(raw,0))
        self.assertIn('overrun_diagnostic_saturated',raw_fault_reasons(raw,0))

    def test_isolated_spike_removed_after_three_distinct_batches_without_mutating_source(self):
        f=QeiDisplayFilter()
        for i,value in enumerate((100,9000,100),1):
            original=shot(value*65536,i,i*5_000_000)
            result=f.update(original,i*5_000_000)[0]
            self.assertEqual(original.qei0_velocity_q16,value*65536)
        self.assertTrue(result.valid);self.assertEqual(result.value_q16,100*65536)
        self.assertEqual(result.source_timestamp,15_000_000)

    def test_repeated_reads_do_not_warm_up_or_extend_freshness(self):
        f=QeiDisplayFilter();s=shot(seq=1,ts=0)
        for now in (0,100,1000):
            self.assertFalse(f.update(s,now)[0].valid)
        self.assertIn('stale',f.update(s,20_000_000)[0].reasons)

    def test_fault_immediate_invalidation_then_clean_rearm_requires_new_warmup(self):
        f=QeiDisplayFilter()
        for i in range(1,4): f.update(shot(100, i, i*1000),i*1000)
        bad=f.update(shot(0,4,4000,info=16),4000)[0]
        self.assertFalse(bad.valid);self.assertIsNone(bad.value_q16)
        self.assertFalse(f.update(shot(0,5,5000),5000)[0].valid)
        self.assertFalse(f.update(shot(0,6,6000),6000)[0].valid)
        self.assertTrue(f.update(shot(0,7,7000),7000)[0].valid)

    def test_timestamp_and_sequence_wrap_and_real_reversal_preserved(self):
        f=QeiDisplayFilter()
        for seq,ts,v in ((65534,0xfffffff0,-100),(65535,0xfffffff8,-100),(0,8,-100)):
            result=f.update(shot(v,seq,ts),ts)[0]
        self.assertTrue(result.valid);self.assertEqual(result.value_q16,-100)

    def test_reversal_does_not_publish_the_previous_direction(self):
        f=QeiDisplayFilter()
        for i in range(1,4):
            self.assertEqual(f.update(shot(100,i,i*1000),i*1000)[0].valid,i==3)
        for i in (4,5):
            value=f.update(shot(-100,i,i*1000),i*1000)[0]
            self.assertFalse(value.valid);self.assertIsNone(value.value_q16)
        value=f.update(shot(-100,6,6000),6000)[0]
        self.assertTrue(value.valid);self.assertEqual(value.value_q16,-100)

    def test_reversal_through_zero_and_other_channel_are_independent(self):
        f=QeiDisplayFilter()
        for i in range(1,4):f.update(shot(100,i,i*1000),i*1000)
        f.update(shot(0,4,4000),4000)
        s=shot(-100,5,5000)
        s=replace(s,qei1_velocity_q16=100)
        left,right=f.update(s,5000)
        self.assertFalse(left.valid);self.assertTrue(right.valid)
        self.assertEqual(right.value_q16,100)

    def test_sequence_regression_and_half_wrap_ambiguity_are_rejected(self):
        for sequence in (2, 3+0x8000):
            with self.subTest(sequence=sequence):
                f=QeiDisplayFilter()
                for i in range(1,4):f.update(shot(100,i,i*1000),i*1000)
                value=f.update(shot(100,sequence,4000),4000)[0]
                self.assertFalse(value.valid)
                self.assertIn('batch_identity_invalid',value.reasons)

    def test_long_gap_requires_new_window_even_if_latest_batch_is_fresh(self):
        f=QeiDisplayFilter()
        for i in range(1,4):f.update(shot(100,i,i*1000),i*1000)
        for i,ts in ((4,20_003_000),(5,20_004_000)):
            self.assertIn('warming_up',f.update(shot(100,i,ts),ts)[0].reasons)
        self.assertTrue(f.update(shot(100,6,20_005_000),20_005_000)[0].valid)

    def test_real_stationary_windows_remain_displayable(self):
        f=QeiDisplayFilter()
        for i in range(1,4):value=f.update(shot(0,i,i*10_000_000),i*10_000_000+100)[0]
        self.assertTrue(value.valid);self.assertEqual(value.value_q16,0)

    def test_config_epoch_change_and_backwards_time_clear_history(self):
        f=QeiDisplayFilter()
        for i in range(1,4): f.update(shot(10,i,i*100),i*100)
        self.assertFalse(f.update(shot(100,4,400,epoch=1),400)[0].valid)
        self.assertIn('batch_identity_invalid',f.update(shot(100,5,390,epoch=1),390)[0].reasons)

    def test_median_timestamp_can_expire_before_latest_batch(self):
        f=QeiDisplayFilter()
        f.update(shot(0,1,0),0)
        f.update(shot(100,2,1_000_000),1_000_000)
        result=f.update(shot(9000,3,19_000_000),19_000_000)[0]
        self.assertTrue(result.valid);self.assertEqual(result.source_timestamp,1_000_000)
        result=f.update(shot(9000,3,19_000_000),21_000_000)[0]
        self.assertFalse(result.valid);self.assertIn('filtered_sample_stale',result.reasons)

    def test_filter_setup_is_explicit_readback_checked_and_keeps_scales_zero(self):
        io=FakeIO();client=PerceptionClient(io)
        with self.assertRaises(ValueError):client.configure_qei_filters(1000,1000)
        client.configure_qei_filters(BENCH_FILTER_TICKS,BENCH_FILTER_TICKS,motor_disconnected=True)
        self.assertEqual(io.read32(reg.QEI0_FILTER),1000)
        self.assertEqual(io.read32(reg.QEI1_FILTER),1000)
        self.assertEqual(io.read32(reg.QEI0_SCALE),0)
        self.assertEqual(io.read32(reg.QEI1_SCALE),0)
        io.mem[reg.QEI0_SCALE]=5362
        with self.assertRaises(ContractError):client.configure_qei_filters(1000,1000,motor_disconnected=True)

    def test_snapshot_records_diagnostics_in_same_epoch(self):
        io=FakeIO();io.mem[reg.QEI1_INFO]=255<<4
        result=PerceptionClient(io).snapshot()
        self.assertEqual(result.qei1_info,255<<4)
        from perception_replay import snapshot_registers
        self.assertEqual(snapshot_registers(result)['QEI1_INFO'],255<<4)

    def test_partial_filter_readback_failure_remains_unconfigured_and_disabled(self):
        class BadReadback(FakeIO):
            def read32(self, offset):
                value=super().read32(offset)
                return value+1 if offset==reg.QEI1_FILTER else value
        io=BadReadback();io.mem[reg.RISK_ENABLE]=1
        with self.assertRaisesRegex(ContractError,'readback mismatch'):
            PerceptionClient(io).configure_qei_filters(1000,1000,motor_disconnected=True)
        self.assertEqual(io.read32(reg.RISK_ENABLE),0)
        self.assertEqual(io.read32(reg.QEI0_SCALE),0)
        self.assertEqual(io.read32(reg.QEI1_SCALE),0)


if __name__=='__main__':unittest.main()
