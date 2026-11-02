"""Single-submission UART writes cannot misreport a scheduling delay or replay."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'stm32预备程序/pc'))
import pynq_link as uart

class NonblockingTests(unittest.TestCase):
    def setUp(self):
        self.serial=uart.MockSerial();self.serial.fileno=lambda:77
        self.link=uart.HybridCarLink('fixture',ser=self.serial,session=123)
    def test_full_kernel_submission_does_not_enter_timed_serial_write(self):
        packet=b'$PSTOP#'
        with patch.object(uart.os,'name','posix'),patch.object(uart.os,'get_blocking',return_value=False,create=True),patch.object(uart.os,'write',return_value=len(packet)) as write:
            self.assertEqual(self.link._write_bytes(packet),len(packet))
            write.assert_called_once_with(77,packet)
        self.assertEqual(self.serial.written,[])
    def test_would_block_is_terminal_without_retry(self):
        with patch.object(uart.os,'name','posix'),patch.object(uart.os,'get_blocking',return_value=False,create=True),patch.object(uart.os,'write',side_effect=BlockingIOError('queue full')) as write:
            with self.assertRaises(BlockingIOError):self.link._send_once(0.)
            self.assertEqual(write.call_count,1)
    def test_partial_query_is_rejected_without_sending_following_command(self):
        with patch.object(uart.os,'name','posix'),patch.object(uart.os,'get_blocking',return_value=False,create=True),patch.object(uart.os,'write',return_value=1) as write:
            with self.assertRaisesRegex(OSError,'short sensor query'):self.link._send_once(0.)
            self.assertEqual(write.call_count,1)
    def test_blocking_descriptor_is_rejected_before_write(self):
        with patch.object(uart.os,'name','posix'),patch.object(uart.os,'get_blocking',return_value=True,create=True),patch.object(uart.os,'write') as write:
            with self.assertRaisesRegex(OSError,'nonblocking descriptor'):self.link._write_bytes(b'$PSTOP#')
            write.assert_not_called()

if __name__=='__main__':unittest.main()
