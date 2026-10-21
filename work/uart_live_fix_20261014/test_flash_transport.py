"""Regression for a ROM that is either freshly reset or already synchronized."""
import ast,time,unittest
from pathlib import Path
src=ast.parse(Path(__file__).with_name('flash_stm32_board.py').read_text(encoding='utf8'))
selected=[n for n in src.body if isinstance(n,ast.FunctionDef) and n.name in {'read_exact','ack','command','identify_rom'}]
api={'time':time}
exec(compile(ast.Module(body=selected,type_ignores=[]),'<actual-uploader-functions>','exec'),api)
class Port:
 def __init__(self,synchronized=False,nack=False):self.synced=synchronized;self.nack=nack;self.buffer=bytearray();self.writes=[]
 def write(self,data):
  self.writes.append(data)
  if self.nack:self.buffer.extend(b'\x1f')
  elif not self.synced:
   if data==b'\x7f':self.synced=True;self.buffer.extend(b'\x79')
  elif data==b'\x02\xfd':self.buffer.extend(b'\x79\x01\x04\x10\x79')
 def read(self,n):
  if not self.buffer:time.sleep(.01);return b''
  data=bytes(self.buffer[:n]);del self.buffer[:n];return data
 def flush(self):pass
 def reset_input_buffer(self):self.buffer.clear()
class ConnectTests(unittest.TestCase):
 def test_already_synchronized_never_resends_autobaud(self):
  p=Port(True);self.assertEqual(api['identify_rom'](p),b'\x04\x10');self.assertEqual(p.writes,[b'\x02\xfd'])
 def test_fresh_reset_autobaud_then_getid(self):
  p=Port();self.assertEqual(api['identify_rom'](p),b'\x04\x10');self.assertEqual(p.writes,[b'\x02\xfd',b'\x7f',b'\x02\xfd'])
 def test_unrecognized_boundary_aborts_without_erase_or_write(self):
  p=Port(True,True)
  with self.assertRaises(RuntimeError):api['identify_rom'](p)
  self.assertEqual(p.writes,[b'\x02\xfd'])
if __name__=='__main__':unittest.main(verbosity=2)
