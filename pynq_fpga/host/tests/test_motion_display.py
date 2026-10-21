import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motion_display import MeasuredDriveModel,MotionDisplayEstimator
from qei_quality import DisplaySpeed,QeiDisplayFilter
from perception_client import Odometry,evaluate_snapshot
from test_qei_quality import shot


def data(value=400, tick=10_000_000, epoch=0, fault=False, good=True):
    s=shot(round(value*65536),int(tick//1_000_000)&65535,tick&0xffffffff,
           info=16 if fault else 0,valid=good,epoch=epoch)
    s=replace(s,odometry0=Odometry(epoch=epoch),odometry1=Odometry(epoch=epoch))
    result=DisplaySpeed(round(value*65536) if good else None,
                        tick&0xffffffff if good else None,tick&0xffffffff,good,() if good else ('invalid',))
    return s,(result,result)


class MotionDisplayTests(unittest.TestCase):
    def test_normal_display_slew_is_bounded_and_raw_source_is_unchanged(self):
        f=MotionDisplayEstimator();previous=0
        for i in range(1,41):
            tick=i*5_000_000;s,values=data(1000,tick)
            original=repr(s);result=f.update(s,values,tick)
            self.assertEqual(repr(s),original)
            self.assertTrue(result['estimated']);self.assertTrue(result['available'])
            self.assertLessEqual(abs(result['speed_mm_s']-previous),30.000001)
            previous=result['speed_mm_s']
        self.assertGreater(previous,900)

    def test_sampling_rate_changes_do_not_change_the_style_substantially(self):
        def run(step):
            f=MotionDisplayEstimator()
            for i in range(int(1/step)+1):
                tick=round(i*step*100_000_000);s,v=data(400,tick)
                r=f.update(s,v,tick)
            return r['speed_mm_s']
        self.assertLess(abs(run(.01)-run(.05)),10)

    def test_duplicate_samples_do_not_extend_hold_and_no_startup_number_is_invented(self):
        f=MotionDisplayEstimator();s,v=data(good=False)
        self.assertFalse(f.update(s,v,10_000_000)['available'])
        s,v=data(400,10_000_000)
        f.update(s,v,10_000_000)
        f.update(s,v,25_000_000) # Same sample, still fresh.
        bad,bv=data(good=False)
        self.assertEqual(f.update(bad,bv,30_000_000)['mode'],'hold')
        self.assertTrue(f.update(bad,bv,109_999_999)['available'])
        r=f.update(bad,bv,110_000_000)
        self.assertFalse(r['available']);self.assertIsNone(r['speed_mm_s'])

    def test_explicit_stationary_display_rejects_phantom_distance_and_does_not_fix_control(self):
        f=MotionDisplayEstimator(stationary_assumed=True);median=QeiDisplayFilter()
        for i in range(1,20):
            tick=i*5_000_000;s,_=data(8000,tick,fault=True)
            s=replace(s,odometry0=Odometry(100000000,100000000,valid=False,fault=True),
                      odometry1=Odometry(900000000,900000000,valid=False,fault=True))
            before=evaluate_snapshot(s,tick)
            r=f.update(s,median.update(s,tick),tick)
            self.assertEqual((r['speed_mm_s'],r['displacement_mm'],r['travelled_mm']),(0,0,0))
            self.assertEqual(r['mode'],'stationary_assumption')
            self.assertFalse(before.permit);self.assertEqual(before,evaluate_snapshot(s,tick))

    def test_locked_zero_requires_fresh_actual_feedback(self):
        s,v=data(good=False)
        for feedback,age,available in (({'left':0,'right':0,'lock':1},.1,True),
                                      ({'left':0,'right':0,'lock':1},.25,True),
                                      ({'left':0,'right':0,'lock':1},.7,False),
                                      ({'left':0,'right':0,'lock':0},.1,False),
                                      ({'left':100,'right':100,'lock':1},.1,False)):
            r=MotionDisplayEstimator().update(s,v,10_000_000,car=feedback,car_age_s=age)
            self.assertEqual(r['available'],available)
            if available:self.assertEqual(r['mode'],'locked_zero_estimate')

    def test_epoch_change_and_clock_restart_discard_old_display_state(self):
        f=MotionDisplayEstimator();s,v=data(400,10_000_000);f.update(s,v,10_000_000)
        bad,bv=data(epoch=1,good=False)
        self.assertFalse(f.update(bad,bv,15_000_000)['available'])
        s,v=data(400,20_000_000,epoch=1);f.update(s,v,20_000_000)
        self.assertFalse(f.update(bad,bv,0)['available'])

    def test_wheel_disagreement_does_not_select_the_smaller_value(self):
        s,v=data(400,10_000_000)
        smaller=replace(v[1],value_q16=0)
        r=MotionDisplayEstimator().update(s,(v[0],smaller),10_000_000,
            car={'left':1000,'right':1000,'lock':0},car_age_s=.25)
        self.assertFalse(r['available']);self.assertIn('wheel_disagreement',r['reasons'])

    def test_clean_turn_and_unreported_intent_are_not_straight_line_faults(self):
        s,v=data(400,10_000_000)
        for right,car in ((100,{'left':1000,'right':250,'lock':0}),
                          (-400,{'left':1000,'right':-1000,'lock':0}), (100,None)):
            with self.subTest(right=right,car=car):
                r=MotionDisplayEstimator().update(s,(v[0],replace(v[1],value_q16=right*65536)),
                     10_000_000,car=car,car_age_s=.25)
                self.assertTrue(r['available']);self.assertEqual(r['mode'],'smoothed')
                self.assertNotIn('wheel_disagreement',r['reasons'])

    def test_locked_feedback_stays_visible_between_300ms_reports_but_expires(self):
        f=MotionDisplayEstimator();s,v=data(good=False)
        for ms in range(0,1200,50):
            r=f.update(s,v,ms*100_000,car={'left':0,'right':0,'lock':1},car_age_s=(ms%300)/1000)
            self.assertTrue(r['available'])
            self.assertGreater(r['valid_for_s'],0)
        r=f.update(s,v,1800*100_000,car={'left':0,'right':0,'lock':1},car_age_s=.7)
        self.assertFalse(r['available'])

    def test_model_needs_measured_provenance_and_never_extrapolates(self):
        payload={'schema':'car-display-drive-model/v1','measured':True,
                 'provenance':'synthetic unit-test fixture; not hardware calibration',
                 'points':[[0,0],[1000,500],[2000,800]]}
        model=MeasuredDriveModel(payload)
        self.assertEqual(model.speed(500),250);self.assertEqual(model.speed(-500),-250)
        self.assertIsNone(model.speed(2100))
        for patch in ({'measured':False},{'provenance':''},{'points':[[0,0],[1000,float('nan')]]}):
            with self.assertRaises(ValueError):MeasuredDriveModel({**payload,**patch})
        f=MotionDisplayEstimator(model=model);s,v=data(good=False)
        f.update(s,v,0,car={'left':1000,'right':1000,'lock':0},car_age_s=.05)
        r=f.update(s,v,5_000_000,car={'left':1000,'right':1000,'lock':0},car_age_s=.05)
        self.assertEqual(r['mode'],'measured_model_estimate');self.assertGreater(r['speed_mm_s'],0)
        self.assertFalse(f.update(s,v,10_000_000,car={'left':1000,'right':1000,'lock':0},car_age_s=.7)['available'])

    def test_distance_correction_is_bounded_and_long_gaps_are_not_integrated(self):
        f=MotionDisplayEstimator();s,v=data(400,0)
        s=replace(s,odometry0=Odometry(valid=True),odometry1=Odometry(valid=True))
        f.update(s,v,0)
        tick=5_000_000;s,v=data(400,tick)
        s=replace(s,odometry0=Odometry(65536000,65536000,valid=True),odometry1=Odometry(65536000,65536000,valid=True))
        r=f.update(s,v,tick)
        self.assertLessEqual(r['travelled_mm'],4.01)
        bad,bv=data(good=False)
        unavailable=f.update(bad,bv,500_000_000)
        self.assertFalse(unavailable['available'])

    def test_source_age_is_correct_across_32_bit_tick_wrap(self):
        f=MotionDisplayEstimator();s,v=data(400,0xfffffff0)
        f.update(s,v,0xfffffff0)
        r=f.update(s,v,0x100000010)
        self.assertAlmostEqual(r['measurement_age_s'],32/100_000_000)


if __name__=='__main__':unittest.main()
