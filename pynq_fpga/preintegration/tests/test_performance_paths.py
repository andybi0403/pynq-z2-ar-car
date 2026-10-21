"""Exact-output, allocation-ownership and quantile regressions for hot paths."""
import random
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from board_runtime import Task78BoardRuntime
from frame_metadata import encode,stamp_bgr0
from frame_pipeline import FrameMetrics,FRAME_BYTES
from test_frame_metadata import association


class PerformancePathTests(unittest.TestCase):
    def test_dma_path_matches_all_pixels_and_keeps_source_immutable(self):
        source=bytes(range(256))*(FRAME_BYTES//256)
        destination=bytearray(FRAME_BYTES);submitted=[]
        runtime=Task78BoardRuntime(None,SimpleNamespace(writechannel=SimpleNamespace(
            writeframe=lambda frame:submitted.append(frame))),None,None,None,running=True)
        runtime.newframe=lambda:destination
        runtime.write_associated(source,encode(association()))
        self.assertIs(submitted[0],destination)
        self.assertEqual(bytes(destination),stamp_bgr0(source,association()))
        self.assertEqual(source,bytes(range(256))*(FRAME_BYTES//256))

    def test_invalid_prefix_and_size_fail_before_dma_buffer_allocation(self):
        runtime=Task78BoardRuntime(None,None,None,None,None,running=True)
        with patch.object(runtime,'newframe') as allocate:
            words=encode(association());words[0]^=1
            with self.assertRaises(ValueError):runtime.write_associated(bytes(FRAME_BYTES),words)
            with self.assertRaises(ValueError):runtime.write_associated(b'short',encode(association()))
            allocate.assert_not_called()

    def test_copy_failure_returns_unsubmitted_dma_buffer(self):
        class Buffer(bytearray):
            freed=False
            def freebuffer(self):self.freed=True
        buffer=Buffer(10)
        runtime=Task78BoardRuntime(None,None,None,None,None,running=True)
        runtime.newframe=lambda:buffer
        with self.assertRaises(ValueError):runtime.write_associated(bytes(FRAME_BYTES),encode(association()))
        self.assertTrue(buffer.freed)

    def test_window_quantiles_match_independent_bounded_history_sort(self):
        rng=random.Random(4251009)
        for count in (0,1,2,3,10,54000):
            metrics=FrameMetrics();now=0;intervals=[]
            for i in range(count):
                if i:
                    interval=rng.randrange(1,100000000);intervals.append(interval);now+=interval
                metrics.observe(now)
            result=metrics.summary();ordered=sorted(intervals[-8192:])
            self.assertEqual(result['frames'],count)
            self.assertEqual(len(metrics.intervals_ns),min(max(0,count-1),8192))
            self.assertIn('last_8192',result['interval_scope'])
            for p in (50,95,99):
                expected=ordered[round((len(ordered)-1)*p/100)]/1e6 if ordered else None
                self.assertEqual(result[f'interval_p{p}_ms'],expected)
