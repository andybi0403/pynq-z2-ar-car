from pathlib import Path
import sys,unittest,io,threading,time,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pynq_fpga/preintegration/host'))
from async_journal import AsyncJournal
class JournalTests(unittest.TestCase):
 def test_mutation_isolation_and_close_drain(self):
  stream=io.StringIO();writer=AsyncJournal(stream)
  item={'type':'frame','values':[1]};self.assertTrue(writer.submit(item));item['values'][0]=2
  for n in range(100):self.assertTrue(writer.submit({'n':n}))
  writer.close();rows=[json.loads(x) for x in stream.getvalue().splitlines()]
  self.assertEqual(rows[0]['values'],[1]);self.assertEqual(len(rows),101)
 def test_slow_disk_cannot_block_producer_and_overflow_is_reported(self):
  entered=threading.Event();release=threading.Event()
  class Slow(io.StringIO):
   def write(self,s):entered.set();release.wait(2);return super().write(s)
  stream=Slow();writer=AsyncJournal(stream,capacity=2)
  writer.submit({'type':'critical'},critical=True);self.assertTrue(entered.wait(1))
  self.assertTrue(writer.submit({'n':1}));self.assertTrue(writer.submit({'n':2}))
  self.assertFalse(writer.submit({'n':3}));release.set()
  with self.assertRaises(RuntimeError):writer.close()
  self.assertEqual(writer.snapshot()['dropped_records'],1)
 def test_byte_budget_rejects_large_record_without_disk_work(self):
  writer=AsyncJournal(io.StringIO(),max_pending_bytes=64)
  self.assertFalse(writer.submit({'message':'x'*100}))
  with self.assertRaises(RuntimeError):writer.close()
  self.assertEqual(writer.snapshot()['accepted'] if 'accepted' in writer.snapshot() else writer.snapshot()['records'],0)
 def test_write_error_is_visible(self):
  class Broken(io.StringIO):
   def write(self,s):raise OSError('disk full')
  writer=AsyncJournal(Broken());writer.submit({'n':1},critical=True)
  with self.assertRaises(RuntimeError):writer.close()
  self.assertIn('disk full',writer.snapshot()['error'])

class TelemetrySnapshotTests(unittest.TestCase):
    def test_nested_detachment_and_shared_identity(self):
        from async_journal import snapshot_copy
        shared={'samples':[1,2], 'flags':(True,None)}
        original={'a':shared,'b':shared,'large_clock':2**63+7}
        result=snapshot_copy(original)
        self.assertEqual(result,original)
        self.assertIs(result['a'],result['b'])
        original['a']['samples'].append(3)
        self.assertEqual(result['a']['samples'],[1,2])
        result['b']['samples'].append(4)
        self.assertEqual(original['a']['samples'],[1,2,3])

if __name__=='__main__':unittest.main()
