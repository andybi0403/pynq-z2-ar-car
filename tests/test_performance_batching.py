"""Lossless batched journal behavior, including concurrent producers and faults."""
from pathlib import Path
import io
import json
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'pynq_fpga/preintegration/host'), str(ROOT/'pynq_fpga/host')]
from system_runtime import JointRunner


class Journal(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()


class BatchingTests(unittest.TestCase):
    def setUp(self):
        self.runner = JointRunner(object(), object(), output_dir='unused', identity={})
        self.runner._journal = Journal()
        self.runner._journal_last_flush = 10.

    def rows(self):
        return [json.loads(line) for line in self.runner._journal.getvalue().splitlines()]

    def test_periodic_batch_retains_all_rows_and_shutdown_drains(self):
        with patch('system_runtime.time.monotonic', return_value=10.5):
            for n in range(100):
                self.runner.log({'type': 'wireless_frame', 'index': n})
        self.assertEqual(self.runner._journal.getvalue(), '')
        with patch('system_runtime.time.monotonic', return_value=11.01):
            self.runner.log({'type': 'wireless_performance'})
        self.assertEqual(len(self.rows()), 101)
        self.assertEqual(self.runner._journal.flushes, 1)
        with patch('system_runtime.time.monotonic', return_value=11.1):
            self.runner.log({'type': 'status'})
            self.runner.log({'type': 'end'})
        self.assertEqual([r['type'] for r in self.rows()[-2:]], ['status', 'end'])
        self.assertEqual(self.runner.journal_status()['pending_records'], 0)

    def test_sample_lock_fault_and_command_changes_flush_immediately(self):
        with patch('system_runtime.time.monotonic', return_value=10.1):
            def sample(phase='ARMED', lock=0, fault=0, pwm=0):
                self.runner.log({'type': 'sample', 'control': {'phase': phase,
                    'requested_pwm': [pwm, pwm], 'car': {'lock': lock, 'fault': fault}}})
            sample()
            sample()
            self.assertEqual(self.runner._journal.flushes, 1)
            sample(pwm=900)
            self.assertEqual(len(self.rows()), 3)
            sample('LOCKED', 1, 1)
            self.assertEqual(self.runner._journal.flushes, 3)
            self.runner.log({'type': 'wireless_frame'})
            self.runner.log({'type': 'wireless_video_fault', 'reason': 'disconnect'})
            self.assertEqual(self.rows()[-1]['type'], 'wireless_video_fault')
            self.assertEqual(self.runner.journal_status()['pending_records'], 0)

    def test_size_bound_and_concurrent_producers_preserve_whole_json_lines(self):
        with patch('system_runtime.time.monotonic', return_value=10.1):
            def produce(worker):
                for n in range(60):
                    self.runner.log({'type': 'status', 'worker': worker, 'n': n, 'payload': 'x'*2000})
            workers = [threading.Thread(target=produce, args=(i,)) for i in range(3)]
            for worker in workers: worker.start()
            for worker in workers: worker.join()
            self.assertGreater(self.runner._journal.flushes, 0)
            self.assertLess(self.runner.journal_status()['pending_bytes'], 262144)
            self.runner.log({'type': 'end'})
        rows = self.rows()[:-1]
        self.assertEqual(len(rows), 180)
        self.assertEqual(len({(r['worker'], r['n']) for r in rows}), 180)
        for worker in range(3):
            self.assertEqual([r['n'] for r in rows if r['worker'] == worker], list(range(60)))


if __name__ == '__main__': unittest.main()
