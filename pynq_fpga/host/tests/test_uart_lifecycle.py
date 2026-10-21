import sys
from pathlib import Path
import unittest
import threading
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'stm32预备程序/pc'))
import pynq_link
from pynq_link import CarLink,MockSerial


class UartLifecycleTests(unittest.TestCase):
    def test_blocked_uart_read_is_cancelled_and_never_reported_as_clean_stop(self):
        class BlockingSerial(MockSerial):
            def __init__(self):
                super().__init__();self.reading=threading.Event();self.cancelled=threading.Event()
            def read(self,n=1):
                self.reading.set();self.cancelled.wait(2);return b''
            def cancel_read(self):self.cancelled.set()
        ser=BlockingSerial();link=CarLink('fixture',ser=ser);link.PERIOD=.01
        link.start();self.assertTrue(ser.reading.wait(1))
        start=time.monotonic()
        with self.assertRaisesRegex(OSError,'STOP unconfirmed'):link.close()
        self.assertLess(time.monotonic()-start,.5)
        self.assertFalse(link._thread.is_alive())
        self.assertTrue(ser.closed and ser.cancelled.is_set())
    def test_real_serial_constructor_has_bounded_read_and_write(self):
        ser=MockSerial()
        with patch.object(pynq_link.serial,'Serial',return_value=ser) as factory:
            link=CarLink('fixture');factory.assert_called_once_with('fixture',9600,timeout=.05,write_timeout=.1)
            link.close()
        self.assertEqual(ser.written[-1],b'$PSTOP#')
        self.assertTrue(ser.closed)
        link.close() # idempotent
        with self.assertRaises(RuntimeError):link.start()

    def test_background_short_write_records_error_and_terminates(self):
        class ShortSerial(MockSerial):
            def write(self,data):return 1
        ser=ShortSerial();link=CarLink('fixture',ser=ser)
        link.start();link._thread.join(1)
        self.assertFalse(link._thread.is_alive())
        self.assertIn('short UART write',link.transport_error)
        with self.assertRaises(OSError):link.close()
        self.assertTrue(ser.closed)

    def test_background_timeout_records_error_and_shutdown_closes(self):
        class TimeoutSerial(MockSerial):
            def write(self,data):raise TimeoutError('write timeout')
        ser=TimeoutSerial();link=CarLink('fixture',ser=ser)
        link.start();link._thread.join(1)
        self.assertFalse(link._thread.is_alive())
        self.assertEqual(link.transport_error,'write timeout')
        with self.assertRaises(OSError):link.close()
        self.assertTrue(ser.closed)


if __name__=='__main__':unittest.main()
