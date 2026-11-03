import unittest
import tkinter as tk
from car_console import Console, KEY_COMMANDS, motion, parse_status


class Tests(unittest.TestCase):
    def test_protocol(self):
        self.assertEqual(motion(1), b'$1,0,0,0,0,0,0,0,0,0#')
        self.assertEqual(len(motion(4)),21)
        state=parse_status(b'$SAFE,MS10,IR0,MM800,VALID1,LOCK1,FAULT1,CMD0,PWM1800,USB1#\r\n')
        self.assertEqual(state['LOCK'],1)
        self.assertIsNone(parse_status(b'$SAFE,MS10#'))

    def test_keyboard_mapping(self):
        self.assertEqual(KEY_COMMANDS, {'Up': 1, 'Down': 2, 'Left': 3, 'Right': 4})

    def test_ui_starts_disabled(self):
        root=tk.Tk(); root.withdraw()
        app=Console(root)
        self.assertFalse(app.ready())
        app.drive(1)
        self.assertEqual(app.command,0)
        root.update_idletasks(); app.close()


if __name__=='__main__':
    unittest.main()
