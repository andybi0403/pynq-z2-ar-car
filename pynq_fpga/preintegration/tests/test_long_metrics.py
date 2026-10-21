import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from association_metrics import AssociationMetrics
from frame_pipeline import FrameMetrics


class LongMetricsTests(unittest.TestCase):
    def test_twelve_thousand_frames_keep_bounded_quantiles_and_true_totals(self):
        association=AssociationMetrics();frame=FrameMetrics()
        for n in range(12000):
            stamp=n*33_333_333;frame.observe(stamp)
            association.observe({'frame_id':n,'received_host_ns':stamp,'valid':True,
                'receive_to_submit_ms':900 if n==0 else 2,'snapshot_host_age_ms':20,'clock_uncertainty_ns':100,
                'sample_age_ms':dict(us=50,qei0=10,qei1=10,risk=1)})
        self.assertEqual(len(frame.intervals_ns),8192)
        self.assertTrue(all(len(v)==8192 for v in association.values.values()))
        self.assertEqual(association.summary()['frames'],12000)
        self.assertEqual(association.summary()['receive_to_submit_ms']['max'],900)
        self.assertEqual(association.summary()['receive_to_submit_ms']['count'],12000)
        self.assertEqual(association.summary()['receive_to_submit_ms']['p95'],2)
        self.assertEqual(frame.summary()['frames'],12000)
        self.assertAlmostEqual(frame.summary()['measured_fps'],30,places=5)


if __name__=='__main__':unittest.main()
