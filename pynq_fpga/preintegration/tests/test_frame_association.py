import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from frame_association import FrameAssociator


class AssociationTests(unittest.TestCase):
    def test_ordered_lookup_selects_exact_prior_bracket_with_bounded_history(self):
        a=FrameAssociator(history=3)
        for i in range(5):
            a.publish(host_before_ns=i*1000,host_after_ns=i*1000+20,
                      pl_ticks64=i*100,epoch=i,
                      registers={n+'_TS':i*100 for n in ('US','QEI0','QEI1','RISK')})
        self.assertEqual(a.associate(1,2019)['reason'],'no_prior_snapshot')
        self.assertEqual(a.associate(1,2020)['epoch'],2)
        self.assertEqual(a.associate(1,4019)['epoch'],3)
        self.assertEqual(a.associate(1,4020)['epoch'],4)

    def publish(self, a, before=1000, after=1020, ticks=0x100000010):
        return a.publish(host_before_ns=before, host_after_ns=after,
                         pl_ticks64=ticks, epoch=7,
                         registers={n + "_TS": 0xfffffff0 for n in ("US", "QEI0", "QEI1", "RISK")})

    def test_wrap_clock_domain_and_raw_values_preserved(self):
        a = FrameAssociator()
        self.publish(a)
        r = a.associate(1, 2010, 5010)
        self.assertTrue(r["valid"])
        self.assertEqual(r["estimated_frame_pl_ticks64"], 0x100000074)
        self.assertAlmostEqual(r["sample_age_ms"]["us"], 0.00132)
        self.assertEqual(r["clock_uncertainty_ns"], 10)
        self.assertEqual(r["receive_to_submit_ms"], 0.003)
        self.assertEqual(r["registers"]["US_TS"], 0xfffffff0)

    def test_future_or_expired_snapshot_cannot_be_associated(self):
        a = FrameAssociator()
        self.publish(a)
        self.assertEqual(a.associate(1, 1010)["reason"], "no_prior_snapshot")
        self.assertEqual(a.associate(1, 200001000)["reason"], "snapshot_stale")

    def test_bad_clock_brackets_and_reverse_submission_fail(self):
        a = FrameAssociator()
        with self.assertRaises(ValueError): self.publish(a, 1020, 1000)
        self.publish(a)
        with self.assertRaises(ValueError): self.publish(a, 1010, 1040)
        with self.assertRaises(ValueError): a.associate(1, 2010, 2000)

    def test_invalid_sensor_does_not_drop_video_after_half_timestamp_wrap(self):
        from association_metrics import AssociationMetrics
        from frame_metadata import encode,decode
        from test_frame_metadata import association
        raw=association()['registers']
        for name in ('US','QEI0','QEI1','RISK'):
            raw[name+'_META']=0
            raw[name+'_TS']=0
        a=FrameAssociator()
        a.publish(host_before_ns=1000,host_after_ns=1020,
                  pl_ticks64=0x80000010,registers=raw,epoch=7)
        result=a.associate(1,2010,5010)
        self.assertTrue(result['valid'])
        self.assertEqual(result['registers'],raw)
        self.assertEqual(result['sample_age_ms'],dict(us=None,qei0=None,qei1=None,risk=None))
        displayed=decode(encode(result))
        self.assertFalse(displayed['distance_valid'])
        self.assertFalse(displayed['speed_valid'])
        self.assertEqual(displayed['risk_level'],3)
        metrics=AssociationMetrics();metrics.observe(result)
        self.assertEqual(metrics.summary()['invalid_associations'],0)
        self.assertEqual(metrics.summary()['qei0_age_ms']['count'],0)
        raw['US_META']=0x80000001
        b=FrameAssociator()
        b.publish(host_before_ns=1000,host_after_ns=1020,
                  pl_ticks64=0x80000010,registers=raw,epoch=7)
        self.assertEqual(b.associate(1,2010)['reason'],'ambiguous_sample_timestamp')


if __name__ == "__main__": unittest.main()
