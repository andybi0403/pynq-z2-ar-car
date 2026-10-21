"""Exercise actual worker concurrency and failure evidence without hardware."""
import json
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "host"))
sys.path.insert(0, str(PROJECT / "preintegration" / "host"))
from perception_client import PerceptionSnapshot, Sample
from frame_pipeline import RawFrameSource,FRAME_BYTES
from system_runtime import JointRunner,wait_for_acquisition


class Link:
    def __init__(self):
        self.state = None
        self.state_seq = 0
        self.state_rx_time = None
        self.closed = False
        self.commands = []
        self.stops = 0
    def start(self): pass
    def stop_request(self): self.stops += 1
    def close(self): self.closed = True
    def update_sample(self, *args): pass
    def update_command(self, left, right): self.commands.append((left, right))
    def limit_command(self, left, right): self.commands.append((left, right))
    def release_request(self): raise AssertionError("LAB_ONLY emitted PREL")


class Client:
    def __init__(self, link, freeze=False):
        self.link, self.epoch, self.freeze = link, 0, freeze
        self.command = 0
        self.command_ts = 0
    def verify_contract(self): pass
    def publish_car_status(self, car, age_s): self.last_display = (car, age_s)
    def display_diagnostics(self): return {"OSD_ERRORS":0, "DISPLAY_FRAMES":0}
    def read_pl_ticks64(self): return time.monotonic_ns() // 10
    def set_command(self, *, forward, valid):
        self.command = int(forward) | int(valid) << 1
        self.command_ts = self.read_pl_ticks64() & 0xffffffff
    def sample_and_decide(self):
        from types import SimpleNamespace
        now = time.monotonic()
        self.link.state = {"left": 0, "right": 0, "lock": 1, "fault": 1, "mm":1000,"ir":0,"drop":0}
        self.link.state_seq += 1
        self.link.state_rx_time = now
        ticks = self.read_pl_ticks64() & 0xffffffff
        if not self.freeze: self.epoch += 1
        sample = Sample(0, ticks, True, self.epoch & 65535)
        shot = PerceptionSnapshot(
            self.epoch, Sample(1000, ticks, True, 1), Sample(4, ticks, True, 1),
            0, 1000, 0, sample, 0, 1000, 0, sample, 0, 100, sample,
            self.command, self.command_ts)
        return ticks, shot, SimpleNamespace(permit=True, reasons=())


class Video:
    def __init__(self, block=False):
        self.block = block
        self.released = threading.Event()
        self.started = False
        self.stopped = False
        self.metadata_words=[]
    def start(self): self.started = True
    def write_bytes(self, frame):
        self.metadata_words.append([int.from_bytes(frame[i:i+4],'little') for i in range(0,72,4)])
        if self.block: self.released.wait(10)
    def write_associated(self, frame, words):
        from frame_metadata import prefix_bgr0
        self.write_bytes(prefix_bgr0(words) + frame[72:])
    def stop(self): self.stopped = True; self.released.set()


class JointTests(unittest.TestCase):
    def test_display_estimate_does_not_promote_bad_measurements_or_control(self):
        from dataclasses import replace
        from perception_client import evaluate_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            runner=self.runner(tmp,video=False)
            runner._journal=io.StringIO();runner._baseline_car_seq=0;runner._started=time.monotonic()
            original=runner.client.sample_and_decide
            def bad_sample():
                ticks,s,_=original()
                s=replace(s,qei0_info=255<<4,qei1_info=255<<4,
                          qei0_velocity_q16=8000*65536,qei1_velocity_q16=8000*65536)
                return ticks,s,evaluate_snapshot(s,ticks)
            runner.client.sample_and_decide=bad_sample
            for _ in range(4):runner.step()
            result=runner.status_snapshot();status=result['latest']['status']
            self.assertFalse(status['speed_valid']);self.assertIsNone(status['speed_mm_s'])
            self.assertEqual(status['raw_speed_mm_s'],8000)
            self.assertTrue(status['motion_display']['available'])
            self.assertTrue(status['motion_display']['estimated'])
            self.assertEqual(status['motion_display']['speed_mm_s'],0)
            self.assertEqual(status['motion_display']['mode'],'locked_zero_estimate')
            self.assertFalse(result['latest']['control']['permit'])
            self.assertTrue(all(c==(0,0) for c in runner.link.commands))
            saved=runner.latest['status']['motion_display']['available']
            with runner._state_lock:
                runner.latest['status']['published_monotonic_ns']=time.monotonic_ns()-300_000_000
            self.assertFalse(runner.status_snapshot()['latest']['status']['motion_display']['available'])
            self.assertEqual(saved,runner.latest['status']['motion_display']['available'])

    def test_browser_speed_warms_up_then_fault_disappears_immediately_and_retains_raw(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            runner=self.runner(tmp,video=False)
            runner._journal=io.StringIO();runner._baseline_car_seq=0
            runner._started=time.monotonic()
            runner.step();runner.step()
            self.assertFalse(runner.status_snapshot()['latest']['status']['speed_valid'])
            runner.step()
            self.assertTrue(runner.status_snapshot()['latest']['status']['speed_valid'])
            original=runner.client.sample_and_decide
            def bad_sample():
                ticks,shot,decision=original()
                return ticks,replace(shot,qei1_info=255<<4),decision
            runner.client.sample_and_decide=bad_sample
            runner.step()
            status=runner.status_snapshot()['latest']['status']
            self.assertFalse(status['speed_valid']);self.assertIsNone(status['speed_mm_s'])
            self.assertEqual(status['raw_speed_mm_s'],0)
            self.assertIn('qei1_illegal_transition',status['speed_quality_reasons'])

    def test_browser_reads_cannot_refresh_the_selected_median_or_stopped_telemetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=self.runner(tmp,video=False);runner._started=time.monotonic()
            runner._journal=io.StringIO();runner._baseline_car_seq=0
            for _ in range(3):runner.step()
            with runner._state_lock:
                status=runner.latest['status']
                status['speed_source_ages_ticks']=[19_000_000,19_000_000]
                status['published_monotonic_ns']=time.monotonic_ns()-20_000_000
            result=runner.status_snapshot()
            self.assertTrue(result['telemetry_fresh'])
            self.assertFalse(result['latest']['status']['speed_valid'])
            self.assertIsNone(result['latest']['status']['speed_mm_s'])
            with runner._state_lock:
                runner.latest['status']['published_monotonic_ns']=time.monotonic_ns()-300_000_000
            self.assertIsNone(runner.status_snapshot()['latest']['status']['speed_mm_s'])

    def test_startup_requires_stable_healthy_samples_and_invalidates_command(self):
        from types import SimpleNamespace
        client=Client(Link());client.io=SimpleNamespace(read32=lambda address:0)
        report=wait_for_acquisition(client,timeout_s=.5,stable_s=.1)
        self.assertGreaterEqual(report['checks'],3)
        self.assertGreaterEqual(report['stable_s'],.1)
        self.assertEqual(client.command,0)

    def test_startup_frozen_epoch_fails_without_starting_formal_session(self):
        from types import SimpleNamespace
        client=Client(Link(),freeze=True);client.io=SimpleNamespace(read32=lambda address:0)
        with self.assertRaisesRegex(RuntimeError,'epoch froze'):
            wait_for_acquisition(client,timeout_s=.2,stable_s=.1)
        self.assertEqual(client.command,0)

    def test_stuck_driver_cleanup_is_failure_and_uart_still_closes(self):
        release=threading.Event()
        class StuckVideo(Video):
            def start(self):release.wait(10);super().start()
            def stop(self):release.wait(10);super().stop()
        with tempfile.TemporaryDirectory() as tmp:
            runner=self.runner(tmp);runner.video=StuckVideo()
            before=time.monotonic()
            try:
                result=runner.run(.1)
                self.assertLess(time.monotonic()-before,5)
                self.assertTrue(runner.link.closed)
                self.assertFalse(result['passed'])
                self.assertTrue(any('resource termination unconfirmed' in item for item in result['failures']))
                self.assertIn('video worker did not terminate',result['failures'])
                self.assertTrue((Path(tmp)/'joint_summary.json').is_file())
            finally:
                release.set();runner._worker.join(1)

    def test_slow_video_start_does_not_delay_control_or_leak_after_session_end(self):
        class SlowVideo(Video):
            def start(self):time.sleep(.2);super().start()
        with tempfile.TemporaryDirectory() as tmp:
            runner=self.runner(tmp);runner.video=SlowVideo()
            result=runner.run(.1)
            self.assertGreaterEqual(result['samples'],2)
            self.assertFalse(result['passed'])  # no video frames before deadline
            self.assertTrue(runner.video.stopped)
            self.assertFalse(runner._worker.is_alive())
            rows=[json.loads(line) for line in (Path(tmp)/'joint.jsonl').read_text().splitlines()]
            times=[row['host_monotonic_ns'] for row in rows if row['type']=='sample']
            self.assertLess(max(b-a for a,b in zip(times,times[1:])),150_000_000)

    def test_same_car_reception_is_not_republished_to_extend_display_lease(self):
        class StickyClient(Client):
            def __init__(self,link):
                super().__init__(link);self.published=[];self.saved=None
            def sample_and_decide(self):
                result=super().sample_and_decide()
                if self.saved is None:
                    self.saved=(self.link.state,self.link.state_seq,self.link.state_rx_time)
                else:
                    self.link.state,self.link.state_seq,self.link.state_rx_time=self.saved
                return result
            def publish_car_status(self,car,age_s):self.published.append((car,age_s))
        with tempfile.TemporaryDirectory() as tmp:
            link=Link();client=StickyClient(link)
            runner=JointRunner(client,link,output_dir=tmp,identity={})
            runner._started=time.monotonic();runner._baseline_car_seq=0
            with (Path(tmp)/'joint.jsonl').open('w') as stream:
                runner._journal=stream
                runner.step();runner.step();runner.step()
                self.assertEqual(len(client.published),1)
                client.saved=(link.state,link.state_seq,time.monotonic()-.8)
                runner.step()
                self.assertEqual(len(client.published),1)
                self.assertFalse(runner.status_snapshot()['latest']['status']['car_valid'])

    def test_configuration_is_deferred_to_mmio_owner(self):
        from calibration_config import CalibrationConfig,WheelCalibration
        with tempfile.TemporaryDirectory() as tmp:
            runner=self.runner(tmp,video=False)
            runner._started=time.monotonic();runner._baseline_car_seq=0
            config=CalibrationConfig(WheelCalibration(5362),WheelCalibration(5400),'operator measurement',True)
            with (Path(tmp)/'joint.jsonl').open('w') as stream, patch.object(CalibrationConfig,'apply',return_value=config.payload()) as apply:
                runner._journal=stream
                runner.enqueue_action('calibration',config.payload())
                apply.assert_not_called()
                runner.step()
                apply.assert_called_once_with(runner.client,motor_disconnected=True)
                self.assertTrue(runner.action_status['applied'])
                self.assertEqual(runner.identity['calibration'],config.payload())
    def runner(self, folder, *, freeze=False, block=False, video=True):
        link = Link()
        client = Client(link, freeze)
        display = Video(block) if video else None
        script = f"import sys,time\nframe=b'12345678'*{FRAME_BYTES//8}\nwhile True:\n sys.stdout.buffer.write(frame);sys.stdout.flush();time.sleep(.03)"
        source = RawFrameSource([sys.executable, "-u", "-c", script],
                                frame_bytes=FRAME_BYTES) if video else None
        return JointRunner(client, link, video=display, source=source,
                           output_dir=folder, identity={"fixture": True}, hardware=False)

    def test_one_session_concurrent_video_control_logs_association(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner(tmp)
            result = runner.run(.3)
            self.assertTrue(result["passed"], result["failures"])
            self.assertFalse(result["hardware"])
            self.assertGreaterEqual(result["samples"], 5)
            self.assertGreater(result["frames"], 0)
            events = [json.loads(line) for line in (Path(tmp)/"joint.jsonl").read_text().splitlines()]
            self.assertTrue(all(e["valid"] for e in events if e["type"] == "frame"))
            recorded=[e['display_metadata_words'] for e in events
                      if e['type'] in ('frame','frame_shutdown_submission')]
            self.assertEqual(recorded,runner.video.metadata_words)
            self.assertTrue(all(c == (0, 0) for c in runner.link.commands))
            self.assertTrue(runner.link.closed and runner.video.stopped)

    def test_completed_shutdown_submission_is_logged_without_active_frame_credit(self):
        class OneFrame:
            frame_sequence=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):
                self.last_received_ns=time.monotonic_ns()
                return b'\0'*FRAME_BYTES
        with tempfile.TemporaryDirectory() as tmp:
            runner=self.runner(tmp,video=False)
            runner._journal=io.StringIO();runner._baseline_car_seq=0;runner._started=time.monotonic()
            runner.step();runner.source=OneFrame()
            class CloseOnSubmission(Video):
                def write_associated(self,frame,words):
                    super().write_associated(frame,words)
                    runner.stop_event.set()
            runner.video=CloseOnSubmission()
            runner._video_loop()
            events=[json.loads(line) for line in runner._journal.getvalue().splitlines()]
            closing=[e for e in events if e['type']=='frame_shutdown_submission']
            self.assertEqual(len(closing),1)
            self.assertEqual([e['display_metadata_words'] for e in closing],runner.video.metadata_words)
            self.assertEqual(runner.frames,0)
            self.assertFalse(any(e['type']=='frame' for e in events))

    def test_blocked_video_does_not_block_control_and_is_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner(tmp, block=True)
            result = runner.run(.3)
            self.assertGreaterEqual(result["samples"], 5)
            self.assertFalse(result["passed"])
            self.assertIn("no camera frames submitted", result["failures"])
            self.assertFalse(runner._worker.is_alive())
            self.assertTrue(runner.link.closed)

    def test_frozen_snapshot_records_failure_and_stops_both_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner(tmp, freeze=True)
            result = runner.run(.3)
            self.assertFalse(result["passed"])
            self.assertTrue(any("epoch froze" in s for s in result["failures"]))
            self.assertTrue((Path(tmp)/"joint_summary.json").is_file())
            self.assertFalse(runner._worker.is_alive())
            self.assertTrue(runner.link.closed and runner.video.stopped)


if __name__ == "__main__": unittest.main()
