"""Actual child-process tests: stalled camera, full pipes and cleanup."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from frame_pipeline import RawFrameSource
import board_runtime


class FrameFailureTests(unittest.TestCase):
    def source(self, script, timeout=1.0):
        return RawFrameSource([sys.executable, "-u", "-c", script],
                              frame_bytes=8, timeout_s=timeout)

    def test_stalled_camera_deadline_kills_child_and_workers(self):
        source = self.source("import time; time.sleep(20)", 0.15)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            with source:
                source.read()
        self.assertLess(time.monotonic() - started, 3)
        self.assertIsNotNone(source.process.poll())
        self.assertTrue(all(not w.is_alive() for w in source._workers))

    def test_stderr_larger_than_pipe_does_not_block_video(self):
        script = ("import sys; sys.stderr.buffer.write(b'x'*200000); "
                  "sys.stderr.flush(); sys.stdout.buffer.write(b'abcdefgh'); "
                  "sys.stdout.flush()")
        with self.source(script, 3) as source:
            self.assertEqual(source.read(), b"abcdefgh")
            self.assertIsNone(source.read())
            self.assertLessEqual(len(source.diagnostics), 65536)

    def test_partial_frame_reports_eof_and_cleans_child(self):
        source = self.source("import sys; sys.stdout.buffer.write(b'abc')")
        with self.assertRaisesRegex(EOFError, "missing 5"):
            with source:
                source.read()
        self.assertIsNotNone(source.process.poll())

    def test_nonzero_decoder_exit_is_not_clean_eof(self):
        with self.source("import sys; sys.stderr.write('bad camera'); sys.exit(7)") as source:
            with self.assertRaisesRegex(RuntimeError, "exited 7.*bad camera"):
                source.read()

    def test_abandoned_full_queue_stops_workers(self):
        source = self.source("import sys; sys.stdout.buffer.write(b'x'*1000000)")
        with source:
            self.assertEqual(source.read(), b"xxxxxxxx")
        self.assertTrue(all(not w.is_alive() for w in source._workers))

    def test_main_cleans_hdmi_on_camera_exception(self):
        class Runtime:
            stopped = False
            def start(self, **kwargs): pass
            def stop(self): self.stopped = True
        runtime = Runtime()
        with patch.object(board_runtime.Task78BoardRuntime, "open", return_value=runtime), \
             patch.object(board_runtime, "RawFrameSource", side_effect=OSError("camera removed")):
            code = board_runtime.main(["--bit", "x.bit", "--hwh", "x.hwh",
                                       "--ffmpeg", "ffmpeg", "--camera-device", "/dev/video0"])
        self.assertEqual(code, 1)
        self.assertTrue(runtime.stopped)


if __name__ == "__main__":
    unittest.main()
