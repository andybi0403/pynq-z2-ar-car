import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
path=Path(__file__).resolve().parents[1]/'uart_live_fix_20261014/pynq_console_transport.py'
spec=importlib.util.spec_from_file_location('transport',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class FakeUART:
    def __init__(self,reject=False):self.writes=[];self.index=0;self.reject=reject
    def write(self,data):self.writes.append(data)
    def read(self,n):
        self.index+=1
        marker='UART_AUTH_'+'0'*24
        if self.index==1:return (marker+'_PASSWORD:').encode()
        if self.index==2:return b''
        if self.reject:return ('Sorry, try again.\n'+marker+'_PASSWORD:').encode()
        return ('\n'+marker+'_END:0\n').encode()
class AuthTests(unittest.TestCase):
    @patch.object(module.secrets,'token_hex',return_value='0'*24)
    def test_empty_read_after_password_is_not_rejection(self,mock):
        port=FakeUART();module.authenticate_root(port,'test-only')
        self.assertEqual(port.writes[-1],b'test-only\n');self.assertEqual(len(port.writes),2)
    @patch.object(module.secrets,'token_hex',return_value='0'*24)
    def test_real_repeated_prompt_is_rejection_no_retry(self,mock):
        port=FakeUART(reject=True)
        with self.assertRaisesRegex(RuntimeError,'rejected'):module.authenticate_root(port,'test-only')
        self.assertEqual(len(port.writes),2)
if __name__=='__main__':unittest.main(verbosity=2)
