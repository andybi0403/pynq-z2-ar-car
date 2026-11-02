"""Offline policy tests with a controllable clock; no vehicle IO."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'pynq_fpga/preintegration/host'),str(ROOT/'pynq_fpga/host')]
from trial_control import TrialGate,TrialMailbox,TrialOwner

class DemoPolicyTests(unittest.TestCase):
    def setUp(self):
        self.t=10.
        self.mail=TrialMailbox(clock=lambda:self.t)
        self.gate=TrialGate(self.mail,clock=lambda:self.t)
        self.gate.connect('driver')
        self.sync()
        self.gate.message('driver',dict(type='claim',client_ms=self.t*1000))
        self.mail.consume()

    def sync(self):
        q=self.gate.challenge('driver')
        return self.gate.message('driver',dict(type='sync',nonce=q['nonce'],received_ms=self.t*1000,sent_ms=self.t*1000))

    def intent(self,seq,age_ms=0,kind='intent'):
        return self.gate.message('driver',dict(type=kind,seq=seq,client_ms=self.t*1000-age_ms,left=0 if kind=='release' else 900,right=0 if kind=='release' else 900))

    def test_delayed_packet_discarded_then_fresh_packet_continues(self):
        self.intent(1);self.mail.consume();stamp=self.gate.sessions['driver']['last_intent_ms']
        self.t+=.1
        self.assertEqual(self.intent(2,250)['type'],'dropped')
        self.assertEqual(self.mail.consume(),(None,None))
        self.assertEqual(self.gate.owner,'driver')
        self.assertEqual(self.gate.sessions['driver']['last_intent_ms'],stamp)
        self.assertEqual(self.intent(3)['type'],'ack')
        self.assertEqual(self.mail.consume()[0],'intent')

    def test_continuous_stale_packets_expire_original_500ms_lease(self):
        self.intent(1);self.mail.consume()
        for seq in range(2,6):
            self.t+=.1;self.intent(seq,300)
        self.t+=.101;self.gate.maintain()
        self.assertIsNone(self.gate.owner)
        self.assertEqual(self.mail.consume(),('stop',None))

    def test_socket_disconnect_is_immediate_stop(self):
        self.intent(1);self.gate.disconnect('driver')
        self.assertIsNone(self.gate.owner)
        self.assertEqual(self.mail.consume(),('stop',None))

    def test_late_release_never_queues_release(self):
        self.assertEqual(self.intent(1,250,'release')['type'],'dropped')
        self.assertEqual(self.mail.consume(),(None,None))

    def test_slow_sync_retains_original_clock_and_does_not_renew_intent(self):
        old=self.gate.sessions['driver']['sync']
        q=self.gate.challenge('driver');sent=self.t*1000;self.t+=.25
        reply=self.gate.message('driver',dict(type='sync',nonce=q['nonce'],received_ms=sent,sent_ms=sent))
        self.assertEqual(reply['type'],'dropped')
        self.assertEqual(self.gate.sessions['driver']['sync'],old)
        self.assertEqual(self.gate.owner,'driver')
        self.t+=.251;self.gate.maintain();self.assertIsNone(self.gate.owner)

    def test_expired_mailbox_packet_is_not_a_new_stop_or_intent(self):
        self.mail.submit(900,900);self.t+=.201
        self.assertEqual(self.mail.consume(),(None,None))

    def test_invalid_pwm_and_replay_still_stop(self):
        self.intent(1);self.mail.consume()
        with self.assertRaises(ValueError):self.intent(1)
        self.assertEqual(self.mail.consume(),('stop',None))

    def test_110ms_sampling_jitter_is_advisory_200ms_stops_without_restart_fault(self):
        stops=[];duration=[.11]
        def tick():self.t+=duration[0];return 'sample'
        control=SimpleNamespace(tick=tick,stop=lambda:stops.append(self.t))
        owner=TrialOwner(control,self.mail,clock=lambda:self.t)
        owner.step();self.assertEqual(stops,[]);self.assertEqual(owner.jitter_count,1)
        duration[0]=.201;owner.step()
        self.assertEqual(len(stops),1);self.assertIsNone(owner.fault)
        duration[0]=.01;owner.step();self.assertIsNone(owner.fault)

if __name__=='__main__':unittest.main()
