"""Offline interleaving at the real hybrid UART query write, with production C."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'pynq_fpga/host/tests'),str(ROOT/'stm32_tools/pc')]
import test_hybrid_c_loop as hybrid
from pynq_link import HybridCarLink,MockSerial

class UARTClockRaceTests(unittest.TestCase):
    setUp=hybrid.ProductionHybridTests.setUp
    sample=hybrid.ProductionHybridTests.sample
    send=hybrid.ProductionHybridTests.send
    arm=hybrid.ProductionHybridTests.arm
    def interleaved_link(self, delay=.01, update=True):
        self.arm()
        self.clock=[.4]
        serial=MockSerial()
        link=HybridCarLink('fixture',ser=serial,clock_fn=lambda:self.clock[0],session=123)
        link._query_seq=1;link._control_seq=1;link.suppressed=False
        link.update_sample(True,1000,0,self.clock[0])
        link.update_control_observation(self.clock[0]);link.update_command(0,0)
        self.packets=[]
        def write(packet):
            self.packets.append(packet)
            self.send(packet,round(self.clock[0]*1000))
            if packet.startswith(b'$Q1,'):
                # Query write releases the GIL; the independent control worker
                # may publish newer observations before UART makes its decision.
                self.clock[0]+=delay
                self.sample(round(self.clock[0]*1000))
                if update:
                    link.update_control_observation(self.clock[0])
                    link.update_command(0,0)
            return len(packet)
        serial.write=write
        return link

    def test_fresh_concurrent_zero_intent_does_not_send_stop_or_relock(self):
        link=self.interleaved_link()
        for _ in range(100):
            kind=link._send_once(self.clock[0])
            self.assertEqual(kind,'drive')
            self.assertFalse(self.s.latched)
            self.clock[0]+=.04
        self.assertNotIn(b'$PSTOP#',self.packets)

    def test_delayed_query_without_new_observation_still_stops(self):
        link=self.interleaved_link(delay=.25,update=False)
        self.assertEqual(link._send_once(self.clock[0]),'stop')
        self.assertTrue(self.s.latched)

    def test_invalid_future_observation_is_not_clamped_to_zero_age(self):
        link=self.interleaved_link(delay=0,update=False)
        link.update_control_observation(self.clock[0]+1)
        self.assertEqual(link._send_once(self.clock[0]),'stop')

if __name__=='__main__':unittest.main()
