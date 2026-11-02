from pathlib import Path
import sys,unittest,threading,time,builtins
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'pynq_fpga/preintegration/host'),str(ROOT/'pynq_fpga/host')]
from wireless_core import VideoHub
class StatsTests(unittest.TestCase):
 def test_slow_percentile_sort_does_not_hold_publication_lock(self):
  hub=VideoHub();hub.observe('decoded',3);entered=threading.Event();release=threading.Event()
  def slow(values):
   entered.set();self.assertTrue(release.wait(2));return builtins.sorted(values)
  with patch('wireless_core.sorted',slow,create=True):
   worker=threading.Thread(target=hub.stats);worker.start()
   self.assertTrue(entered.wait(2))
   self.assertTrue(hub.condition.acquire(timeout=.1))
   hub.condition.release();hub.observe('captured');release.set();worker.join(2)
   self.assertFalse(worker.is_alive())
 def test_cached_http_statistics_never_compute_on_caller(self):
  hub=VideoHub();entered=threading.Event();release=threading.Event()
  def slow():
   entered.set();release.wait(2);return {'stats_generated_ns':123,'counts':{'captured':7}}
  with patch.object(hub,'stats',slow):
   initial=hub.cached_stats();self.assertTrue(initial['warming_up'])
   self.assertTrue(entered.wait(2));self.assertEqual(hub.cached_stats(),initial)
   release.set()
   deadline=time.monotonic()+2
   while hub.cached_stats().get('stats_generated_ns')!=123 and time.monotonic()<deadline:time.sleep(.001)
   self.assertEqual(hub.cached_stats()['counts']['captured'],7)
   hub.close();hub._stats_worker.join(2);self.assertFalse(hub._stats_worker.is_alive())
 def test_quantiles_and_counts_remain_exact(self):
  hub=VideoHub()
  for n in range(1,101):hub.observe('decoded',n)
  hub.observe('captured',amount=3)
  stats=hub.stats();self.assertEqual(stats['latency']['decoded'],{'p50_ms':50,'p95_ms':95,'p99_ms':99})
  self.assertEqual(stats['counts']['captured'],3)
if __name__=='__main__':unittest.main()
