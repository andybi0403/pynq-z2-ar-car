import unittest
from pynq_link import HybridCarLink, MockSerial, crc16, hybrid_frame, parse_sensor_report


def reply(session=123, request=1, us_seq=7, us_age=20, valid=1, mm=1000,
          ir_seq=8, ir_age=1, ir_valid=1, ir=0):
    body = f'$S1,{session},{request},{us_seq},{us_age},{valid},{mm},{ir_seq},{ir_age},{ir_valid},{ir},0,0,1,1,0'
    return f'{body},{crc16(body):04X}#'.encode()


class HybridLinkTests(unittest.TestCase):
    def setUp(self):
        self.now = 1.0
        self.serial = MockSerial()
        self.link = HybridCarLink('fixture', ser=self.serial, clock_fn=lambda: self.now, session=123)

    def receive(self, packet):
        self.serial._rx.append(packet)
        self.link._process_rx(self.now)

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


if __name__ == '__main__': unittest.main()
