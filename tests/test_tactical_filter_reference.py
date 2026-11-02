import unittest
from tactical_filter_reference import TacticalFilter, MS, MASK


class FilterReferenceTests(unittest.TestCase):
    def test_outlier_and_repeat_do_not_refresh(self):
        f = TacticalFilter()
        for seq, distance in enumerate((600, 610, 2500)):
            result = f.accept(seq, seq * 100 * MS, distance, True, seq * 100 * MS)
        self.assertEqual(result['filtered_mm'], 610)
        self.assertEqual(f.accept(2, 200 * MS, 200, True, 201 * MS)['filtered_mm'], 610)
        self.assertFalse(f.observe(400 * MS)['valid'])

    def test_wrap_and_invalid_require_new_samples(self):
        f = TacticalFilter(); base = MASK - 150 * MS
        for i, seq in enumerate((65534, 65535, 0)):
            t = (base + i * 100 * MS) & MASK
            result = f.accept(seq, t, 500, True, t)
        self.assertTrue(result['valid'])
        self.assertFalse(f.accept(1, t, 0, False, t)['valid'])
        self.assertFalse(f.accept(2, (t + 100 * MS) & MASK, 500, True, (t + 100 * MS) & MASK)['valid'])

    def test_trend_requires_confirmation_and_expires(self):
        f = TacticalFilter(); states = []
        for i in range(12):
            t = i * 100 * MS
            states.append(f.accept(i, t, 1200 - 20 * i, True, t)['trend'])
        self.assertIn('approaching', states)
        self.assertEqual(states[0], 'unknown')
        self.assertEqual(f.observe(1300 * MS)['trend'], 'unknown')

    def test_poll_cadence_prevents_healthy_sample_expiry_between_commits(self):
        def run(period):
            f=TacticalFilter();good=total=0
            for now in range(0,5001):
                result=f.observe(now*MS)
                if now>=50 and now%period==0:
                    # MCU US samples every 60ms; queries every 50ms, 12ms reply.
                    query=((now-12)//50)*50
                    stamp=(query//60)*60
                    result=f.accept(stamp//60,stamp*MS,600,True,now*MS)
                if now>=1000:
                    total+=1;good+=int(result['valid'])
            return good/total
        self.assertLess(run(100),.9)
        self.assertEqual(run(50),1.0)


if __name__ == '__main__':
    unittest.main()
