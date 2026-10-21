"""Production ARM RX/IRQ/poll routing against the real Python host parser.

Requires unicorn and pyelftools. The modeled peripheral evidence is offline;
actual UART/flash readback remains a separate hardware acceptance step.
"""
import json,struct,unittest
from uart_arm_fixture import Machine,SYMS,HybridCarLink
from pynq_link import hybrid_frame

def pair(data_uart,noise=None,flags=0x20):
    m=Machine();port=m.U1 if data_uart==1 else m.U2
    other=m.U2 if data_uart==1 else m.U1
    now=[0.0]
    class Wire:
        def __init__(self):self.offset=0
        def write(self,data):m.inject(port,data);return len(data)
        def read(self,n):
            data=bytes(m.output[port][self.offset:self.offset+min(n,7)])
            self.offset+=len(data);return data
    host=HybridCarLink('ARM fixture',ser=Wire(),clock_fn=lambda:now[0],session=123)
    for ms in range(1250):
        now[0]=ms/1000;m.write32(SYMS['millis'],ms)
        if noise and ms%100==0:m.inject(other,noise,flags)
        if ms%50==0:host._send_once(now[0])
        m.step(ms);host._process_rx(now[0])
    return m,host

class UartRoleTests(unittest.TestCase):
    def test_real_host_on_each_uart(self):
        for port in (1,2):
            m,h=pair(port)
            self.assertEqual(h.state_seq,25)
            self.assertEqual(h.sensor_errors,0)
            self.assertEqual(m.facts()['bound_uart'],port)
            self.assertTrue(m.facts()['all_replies_locked_zero'])
            active=m.U1 if port==1 else m.U2
            self.assertNotIn(b'$SAFE',bytes(m.output[active]))

    def test_stray_bytes_and_framing_errors_cannot_take_over(self):
        for port,flags in ((1,0x20),(2,0x20),(1,2),(2,2)):
            m,h=pair(port,b'x',flags)
            self.assertEqual(h.state_seq,25)
            self.assertEqual(h.sensor_errors,0)
            self.assertEqual(m.facts()['bound_uart'],port)
            self.assertEqual(m.read32(0x40000834),0)
            self.assertEqual(m.read32(0x40000838),0)

    def test_bad_crc_and_drive_cannot_bind(self):
        m=Machine()
        for packet in (b'x',hybrid_frame('Q1',123,1)[:-6]+b',0000#',hybrid_frame('D1',123,1,10,10)):
            m.inject(m.U1,packet);m.step(1)
            self.assertEqual(m.facts()['bound_uart'],0)
        m.inject(m.U2,hybrid_frame('Q1',123,1));m.step(2)
        self.assertEqual(m.facts()['bound_uart'],2)

    def test_other_uart_cannot_change_session_or_accept_commands(self):
        m=Machine();m.inject(m.U1,hybrid_frame('Q1',123,1));m.step(1)
        for packet in (hybrid_frame('Q1',999,1),hybrid_frame('D1',123,2,1000,1000),hybrid_frame('R1',123,3)):
            m.inject(m.U2,packet);m.step(2)
        self.assertEqual(m.facts()['bound_uart'],1)
        self.assertEqual(m.read32(SYMS['hybrid']),123)
        self.assertEqual(m.u.mem_read(SYMS['hybrid']+14,1),b'\x00')
        self.assertEqual(m.read32(0x40000834),0)
        self.assertEqual(m.read32(0x40000838),0)

    def test_stop_does_not_release_or_unbind(self):
        for data_uart in (1,2):
            m,h=pair(data_uart)
            port=m.U1 if data_uart==1 else m.U2
            other=m.U2 if data_uart==1 else m.U1
            for sequence,stop in enumerate((b'$HALT#',b'$PSTOP#',b'$ARM#',b'$BT#'),26):
                m.inject(other,stop);m.step(1251)
                self.assertEqual(m.facts()['bound_uart'],data_uart)
                m.inject(port,hybrid_frame('Q1',123,sequence));m.step(1252,100)
                self.assertEqual(m.reports()[-1]['request'],sequence)
                self.assertTrue(m.reports()[-1]['lock'])
                self.assertEqual(m.reports()[-1]['left'],0)
                self.assertEqual(m.reports()[-1]['right'],0)

    def test_secondary_halt_stops_nonzero_modeled_outputs(self):
        m=Machine();m.inject(m.U1,hybrid_frame('Q1',123,1));m.step(0)
        # Explicitly modeled healthy sensors and an already authorized command:
        # prove nonzero PWM before HALT so a broken stop cannot pass trivially.
        m.u.mem_write(SYMS['echo_valid'],b'\x01')
        m.u.mem_write(SYMS['echo_mm'],struct.pack('<H',1000))
        m.write32(SYMS['echo_sample_ms'],10)
        m.u.mem_write(SYMS['ir_valid'],b'\x01')
        m.u.mem_write(SYMS['ir_count'],b'\x03')
        m.write32(SYMS['ir_sample_ms'],10)
        control=bytearray(40)
        struct.pack_into('<II',control,0,10,10)
        struct.pack_into('<H',control,12,1000)
        control[15]=1;control[19]=7
        struct.pack_into('<iii',control,24,600,600,600)
        m.u.mem_write(SYMS['control'],bytes(control));m.step(10)
        self.assertEqual((m.read32(0x40000834),m.read32(0x40000838)),(600,600))
        m.inject(m.U2,b'$HALT#');m.step(11)
        self.assertEqual((m.read32(0x40000834),m.read32(0x40000838)),(0,0))
        self.assertEqual(m.facts()['bound_uart'],1)
        m.inject(m.U1,hybrid_frame('Q1',123,2));m.step(12,100)
        self.assertEqual(m.reports()[-1]['request'],2)
        self.assertEqual((m.reports()[-1]['left'],m.reports()[-1]['right'],m.reports()[-1]['lock']),(0,0,1))

    def test_independent_partial_frames_and_overflow(self):
        m=Machine();packet=hybrid_frame('Q1',123,1)
        m.inject(m.U2,packet[:12]);m.step(1)
        m.inject(m.U1,b'$broken');m.step(2)
        m.inject(m.U2,packet[12:]);m.step(3,100)
        self.assertEqual(m.facts()['bound_uart'],2)
        self.assertEqual(m.reports()[-1]['request'],1)
        m.inject(m.U1,b'x'*200);m.step(4)
        m.inject(m.U2,hybrid_frame('Q1',123,2));m.step(5,100)
        self.assertEqual(m.reports()[-1]['request'],2)
        self.assertTrue(m.reports()[-1]['lock'])

if __name__=='__main__':unittest.main(verbosity=2)
