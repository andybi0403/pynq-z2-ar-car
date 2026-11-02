import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path('pynq_fpga/host/tests').resolve()))
from supervisor_c_fixture import SupervisorCFixture
class TestNewPolicy(unittest.TestCase):
 def test_stalled_supervisor_sends_stop_and_latches_actual_c(self):
  h=SupervisorCFixture();h.arm();h.drive();start=h.ms();h.control_enabled=False;h.advance(500)
  self.assertTrue(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(0,0));self.assertTrue(any(kind=='stop' for t,kind,_ in h.sent if t>=start))
 def test_invalid_range_does_not_itself_stop_actual_c(self):
  h=SupervisorCFixture();h.arm();h.drive();h.pl.valid=False;h.advance(250)
  self.assertFalse(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(900,900))
 def test_sensor_sample_freeze_does_not_itself_stop_actual_c(self):
  h=SupervisorCFixture();h.arm();h.drive();h.pl.sampling=False;h.advance(400)
  self.assertFalse(h.c.s.latched);self.assertEqual(h.c.log[-1][3:5],(900,900))
if __name__=='__main__':unittest.main()
