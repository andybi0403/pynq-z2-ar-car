"""Actual production C acquisition/control/protocol with the Python UART v3 client."""
import ctypes as C
import unittest
from test_night_a_loop import lib, CSafe
from pynq_link import crc16, hybrid_frame, HybridCarLink, MockSerial, parse_sensor_report


class Session(C.Structure):
    _fields_=[('session',C.c_uint32),('query_seq',C.c_uint32),('command_seq',C.c_uint32),
              ('initialized',C.c_uint8),('query_seen',C.c_uint8),('command_seen',C.c_uint8)]


lib.hybrid_receive.argtypes=[C.POINTER(CSafe),C.POINTER(Session),C.c_char_p,C.c_size_t,C.c_uint32]
lib.hybrid_receive.restype=C.c_int
lib.safe_local_sample.argtypes=[C.POINTER(CSafe),C.c_uint16,C.c_uint8,C.c_uint32,C.c_uint8,C.c_uint8,C.c_uint32]
lib.hybrid_report.argtypes=[C.c_char_p,C.c_size_t,C.POINTER(CSafe),C.POINTER(Session),C.c_uint32,
                           C.c_uint32,C.c_uint,C.c_uint,C.c_uint,C.c_uint32,C.c_uint,C.c_uint,C.c_uint,C.c_int,C.c_int]
lib.hybrid_report.restype=C.c_size_t


class ProductionHybridTests(unittest.TestCase):
    def setUp(self):
        self.s=CSafe();self.h=Session();lib.safe_init(C.byref(self.s))
    def sample(self, now, *, stamp=None, ir=0, valid=1):
        lib.safe_local_sample(C.byref(self.s),1000,valid,now if stamp is None else stamp,ir,1,now)
    def send(self,packet,now):
        return lib.hybrid_receive(C.byref(self.s),C.byref(self.h),packet,len(packet),now)
    def arm(self):
        self.sample(0);self.send(hybrid_frame('Q1',123,1),0)
        for now in range(1,401):self.sample(now)
        self.assertEqual(self.send(hybrid_frame('R1',123,1),400),1)
        self.assertFalse(self.s.latched)
    def test_production_report_roundtrip_and_age_bound(self):
        clock=[1.0];serial=MockSerial();link=HybridCarLink('fixture',ser=serial,clock_fn=lambda:clock[0],session=123)
        link._send_once(clock[0])
        for packet in serial.written:self.send(packet,1000)
        self.sample(1000,stamp=980)
        buf=C.create_string_buffer(180)
        n=lib.hybrid_report(buf,len(buf),C.byref(self.s),C.byref(self.h),1,7,20,1,1000,8,1,1,0,0,0)
        self.assertGreater(n,0)
        packet=buf.raw[:n].rstrip(b'\r\n')
        self.assertEqual(parse_sensor_report(packet)['us_age_ms'],20)
        serial._rx.append(packet);clock[0]=1.02;link._process_rx(clock[0])
        self.assertLessEqual(link.sensor_snapshot()['us_sample_s'],.98)
        self.assertEqual(link.state['lock'],1)
    def test_repeated_driving_queries_cannot_renew_frozen_local_sample(self):
        self.arm()
        for seq,now in enumerate(range(400,651,50),2):
            self.send(hybrid_frame('Q1',123,seq),now)
            self.send(hybrid_frame('D1',123,seq,500,500),now)
        self.assertEqual(self.s.sample_ms,400)
        self.assertTrue(self.s.latched);self.assertTrue(self.s.reason&8)
    def test_corruption_and_wrong_session_lock_actual_outputs(self):
        self.arm();self.send(hybrid_frame('D1',123,2,600,600),400)
        packet=hybrid_frame('D1',123,3,600,600).replace(b'600',b'601',1)
        self.assertEqual(self.send(packet,401),0)
        left=C.c_int();right=C.c_int();lib.safe_outputs(C.byref(self.s),C.byref(left),C.byref(right))
        self.assertEqual((left.value,right.value),(0,0))
        self.assertEqual(self.send(hybrid_frame('D1',999,4,600,600),402),0)
    def test_uart_failure_with_local_acquisition_alive(self):
        self.arm();self.send(hybrid_frame('D1',123,2,600,600),400)
        for now in range(401,651):self.sample(now)
        self.assertTrue(self.s.latched);self.assertTrue(self.s.reason&16)


if __name__=='__main__':unittest.main()
