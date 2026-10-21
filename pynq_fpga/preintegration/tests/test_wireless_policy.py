"""Deterministic rate scheduling and congestion/recovery, independent of hardware."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from wireless_policy import VideoPolicy


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.now=0.;self.policy=VideoPolicy(clock=lambda:self.now)
    def test_manual_fractional_cadence_does_not_collapse_24fps_to_15(self):
        for fps in VideoPolicy.FPS_OPTIONS:
            self.policy.configure({'mode':'manual','fps':fps,'quality':65})
            admitted=sum(self.policy.admit(now=n/30) for n in range(300))
            self.assertLessEqual(abs(admitted-10*fps),1,(fps,admitted))
    def test_fixed_cannot_silently_reduce_fps_or_quality(self):
        self.policy.configure({'mode':'fixed','fps':10,'quality':35})
        for n in range(100):self.now=n;self.policy.observe(cost_ms=1000,backlogged=True)
        p=self.policy.settings();self.assertEqual((p['output_fps'],p['jpeg_quality']),(30,75))
        self.assertEqual(p['level'],0)
    def test_congestion_fast_reports_cannot_hide_slow_receiver(self):
        self.policy.configure({'mode':'auto'})
        for n in range(70):
            self.now=n*.05
            if n in (20,40,60):self.policy.observe(receiver={'visible':True,'received_fps':10,'drawn_fps':8})
            self.policy.observe(cost_ms=1)
        p=self.policy.settings();self.assertEqual(p['level'],1);self.assertEqual(p['output_fps'],24)
        self.assertEqual(p['transitions'],1)
    def test_recovery_waits_for_stable_five_seconds(self):
        self.policy.configure({'mode':'auto'})
        for n in range(31):self.now=n*.05;self.policy.observe(cost_ms=80)
        self.assertEqual(self.policy.settings()['level'],1)
        for n in range(1,121):self.now=1.5+n*.05;self.policy.observe(cost_ms=1)
        self.assertEqual(self.policy.settings()['level'],1)
        for n in range(121,151):self.now=1.5+n*.05;self.policy.observe(cost_ms=1)
        self.assertEqual(self.policy.settings()['level'],0)
    def test_bounded_floor_snapshot_bypass_and_no_invented_frames(self):
        self.policy.configure({'mode':'auto'})
        for n in range(400):self.now=n*.1;self.policy.observe(backlogged=True)
        p=self.policy.settings();self.assertEqual((p['level'],p['output_fps'],p['jpeg_quality']),(4,10,45))
        self.assertTrue(self.policy.admit(now=40));self.assertFalse(self.policy.admit(now=40.01))
        self.assertTrue(self.policy.admit(now=40.01,force=True));self.assertFalse(self.policy.admit(now=40.02))
    def test_invalid_settings_and_feedback(self):
        for payload in ({'mode':'auto','fps':True},{'mode':'auto','quality':74},{'mode':'oops'},{'mode':'auto','unknown':1}):
            with self.assertRaises(ValueError):self.policy.configure(payload)
        self.policy.configure({'mode':'auto'})
        for bad in (float('nan'),-1,999,True):
            with self.assertRaises(ValueError):self.policy.observe(receiver={'visible':True,'received_fps':bad,'drawn_fps':30})


if __name__=='__main__':unittest.main()
