import unittest
from unittest.mock import patch
from pynq_link import HybridCarLink, MockSerial, crc16, hybrid_frame, parse_sensor_report


def reply(session=123, request=1, us_seq=7, us_age=20, valid=1, mm=1000,
          ir_seq=8, ir_age=1, ir_valid=1, ir=0, left=0, right=0, lock=1):
    body = f'$S1,{session},{request},{us_seq},{us_age},{valid},{mm},{ir_seq},{ir_age},{ir_valid},{ir},{left},{right},{lock},1,0'
    return f'{body},{crc16(body):04X}#'.encode()


class HybridLinkTests(unittest.TestCase):
    def setUp(self):
        self.now = 1.0
        self.serial = MockSerial()
        self.link = HybridCarLink('fixture', ser=self.serial, clock_fn=lambda: self.now, session=123)

    def receive(self, packet):
        self.serial._rx.append(packet)
        self.link._process_rx(self.now)

    def test_ir_reset_is_advisory_and_does_not_discard_fresh_us_or_actuators(self):
        self.link._send_once(self.now);self.receive(reply(us_seq=100,ir_seq=900))
        self.now+=.05
        self.link._send_once(self.now)
        self.receive(reply(request=2,us_seq=101,ir_seq=1,ir=3,lock=0,left=200,right=200))
        sensors=self.link.sensor_snapshot()
        self.assertTrue(sensors['us_valid']);self.assertFalse(sensors['ir_valid'])
        self.assertEqual(self.link.state['left'],200)
        self.assertEqual(self.link.state['lock'],0)
        self.assertEqual(self.link.ir_sequence_warnings,1)

    def test_crc_known_vector_and_strict_format(self):
        self.assertEqual(crc16(b'123456789'), 0x29b1)
        self.assertIsNotNone(parse_sensor_report(reply()))
        for packet in (reply()[:-1], reply().replace(b'1000', b'1001'), reply(mm=4096),
                       reply(valid=2), reply(ir=4), reply().replace(b',0,0,1,', b',+0,0,1,')):
            self.assertIsNone(parse_sensor_report(packet))

    def test_only_outstanding_reply_can_update_state(self):
        self.receive(reply()); self.assertIsNone(self.link.state)
        self.link._send_once(self.now)
        self.receive(reply(session=124)); self.assertIsNone(self.link.state)
        self.receive(reply()); self.assertIsNotNone(self.link.state)
        sequence = self.link.state_seq
        self.receive(reply()); self.assertEqual(self.link.state_seq, sequence)

    def test_request_timeout_and_fragment_resynchronization(self):
        self.link._send_once(self.now)
        self.now += .151
        self.receive(reply()); self.assertIsNone(self.link.state)
        self.link._send_once(self.now)
        packet = reply(request=2)
        self.receive(b'garbage$broken' + packet[:25]); self.assertIsNone(self.link.state)
        self.receive(packet[25:]); self.assertEqual(self.link.state['mm'], 1000)

    def test_duplicate_sample_queries_do_not_refresh_age(self):
        self.link._send_once(self.now); self.receive(reply())
        original = self.link.sensor_snapshot()['us_sample_s']
        for request in range(2, 7):
            self.now += .05
            self.link._send_once(self.now)
            self.receive(reply(request=request, us_age=0, ir_seq=8+request))
            self.assertEqual(self.link.sensor_snapshot()['us_sample_s'], original)
        self.assertFalse(self.link.sensor_snapshot()['us_valid'])
        self.assertTrue(self.link.sensor_snapshot()['ir_valid'])

    def test_legacy_echo_cannot_refresh_sensor_or_executor(self):
        self.link._send_once(self.now)
        self.receive(b'$CAR,0,0,1,1,9999,0,0#')
        self.assertIsNone(self.link.sensor_snapshot()); self.assertIsNone(self.link.state)

    def test_diagnostics_expose_verified_link_and_sensor_counts(self):
        self.link._send_once(self.now)
        self.now += .012
        self.receive(reply(mm=432, ir=2))
        link = self.link.diagnostics()
        self.assertEqual(link['query_tx_count'], 1)
        self.assertEqual(link['report_rx_count'], 1)
        self.assertEqual(link['sensor_errors'], 0)
        self.assertEqual(link['state_sequence'], 1)
        self.assertTrue(link['link_fresh'])
        self.assertLess(link['last_reply_latency_ms'], 20)
        self.assertEqual(link['sensor']['distance_mm'], 432)
        self.assertTrue(link['sensor']['us_valid'])
        self.assertTrue(link['sensor']['ir_valid'])
        self.assertFalse(link['sensor']['ir_left_active'])
        self.assertTrue(link['sensor']['ir_right_active'])

    def test_sequence_rollback_and_out_of_order_replies(self):
        self.link._send_once(self.now); self.receive(reply(us_seq=99))
        self.now += .01; self.link._send_once(self.now)
        self.receive(reply(request=2, us_seq=0))
        self.assertEqual(self.link.state_seq, 1)
        self.now += .01; self.link._send_once(self.now)
        self.now += .01; self.link._send_once(self.now)
        self.receive(reply(request=4, us_seq=100, ir_seq=10))
        self.receive(reply(request=3, us_seq=100, ir_seq=10))
        self.assertEqual(self.link.state_seq, 2)

    def test_query_is_independent_of_command_and_short_writes_fail(self):
        self.link._send_once(self.now)
        self.assertTrue(self.serial.written[0].startswith(b'$Q1,123,1,'))
        self.assertEqual(self.serial.written[1], b'$PSTOP#')
        self.serial.write = lambda packet: 1
        with self.assertRaises(OSError): self.link._send_once(self.now)

    def test_command_packets_have_no_sensor_override_fields(self):
        packet = hybrid_frame('D1', 123, 9, 600, -500)
        self.assertTrue(packet.startswith(b'$D1,123,9,600,-500,'))
        for values in ((2401, 0), (True, 0)):
            with self.assertRaises(ValueError): hybrid_frame('D1',123,1,*values)

    def establish_locked_diagnostic(self):
        self.link=HybridCarLink('fixture',ser=self.serial,clock_fn=lambda:self.now,
                                session=123,locked_diagnostic=True)
        self.link._send_once(self.now);self.receive(reply(us_seq=1000,ir_seq=9000))

    def reset_reply(self,request,**kwargs):
        self.now+=.05;self.link._send_once(self.now)
        self.receive(reply(request=request,us_seq=request,ir_seq=request*2,**kwargs))

    def test_locked_reset_rotates_session_and_never_replays_cached_motion(self):
        self.establish_locked_diagnostic()
        self.link._cmd=(800,800,True,1000,0);self.link._rel_flag=True
        for request in (2,3,4):
            self.reset_reply(request)
            self.assertIsNone(self.link.sensor_snapshot());self.assertIsNone(self.link.state)
        self.assertEqual(self.link.locked_resync_count,1)
        self.assertEqual(self.link.acquisition_epoch,1)
        self.assertTrue(self.link.diagnostics()['resync_pending'])
        with patch('pynq_link.secrets.randbelow',return_value=456):
            self.now+=.05;self.link._send_once(self.now)
        self.assertEqual(self.link.session,457)
        self.assertTrue(self.link.diagnostics()['resync_pending'])
        self.receive(reply(session=457,request=5,us_seq=5,ir_seq=10))
        self.assertEqual(self.link.sensor_snapshot()['acquisition_epoch'],1)
        self.assertEqual(self.link.state_seq,2)
        self.assertFalse(self.link.diagnostics()['resync_pending'])
        self.assertFalse(self.link._rel_flag);self.assertIsNone(self.link._cmd_ms)
        self.assertTrue(all(p==b'$PSTOP#' or p.startswith(b'$Q1,') for p in self.serial.written))
        self.now+=.05;self.link._send_once(self.now)
        self.receive(reply(session=123,request=6,us_seq=1001,ir_seq=9001))
        self.assertEqual(self.link.state_seq,2)
        self.receive(reply(session=457,request=6,us_seq=6,ir_seq=12))
        self.assertEqual(self.link.state_seq,3)

    def test_default_link_does_not_auto_accept_counter_rollback(self):
        self.link._send_once(self.now);self.receive(reply(us_seq=1000,ir_seq=9000))
        for request in (2,3,4):self.reset_reply(request)
        self.assertEqual(self.link.acquisition_epoch,0)
        self.assertEqual(self.link.locked_resync_count,0)
        self.assertEqual(self.link.state_seq,1)

    def test_single_counter_rollback_and_bad_crc_cannot_trigger_resync(self):
        self.establish_locked_diagnostic()
        for request in (2,3,4):
            self.now+=.05;self.link._send_once(self.now)
            self.receive(reply(request=request,us_seq=1,ir_seq=9000+request))
        for request in (5,6,7):
            self.now+=.05;self.link._send_once(self.now)
            self.receive(reply(request=request,us_seq=1,ir_seq=1).replace(b',1000,',b',1001,'))
        self.assertEqual(self.link.locked_resync_count,0)

    def test_unlocked_or_nonzero_reset_reply_cannot_confirm_recovery(self):
        self.establish_locked_diagnostic()
        self.reset_reply(2,left=100,lock=0)
        self.assertIsNone(self.link.state);self.assertIsNone(self.link.sensor_snapshot())
        self.reset_reply(3);self.reset_reply(4)
        self.assertEqual(self.link.locked_resync_count,0)
        self.reset_reply(5);self.assertEqual(self.link.locked_resync_count,1)

    def test_natural_32bit_sensor_wrap_does_not_trigger_recovery(self):
        self.establish_locked_diagnostic()
        self.link._sensors['us_seq']=self.link._sensors['ir_seq']=0xfffffffe
        self.reset_reply(2)
        self.assertEqual(self.link.locked_resync_count,0)
        self.assertEqual(self.link.state_seq,2)


if __name__ == '__main__': unittest.main()
