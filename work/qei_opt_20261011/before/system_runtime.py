"""One Overlay, one MMIO owner, independent video/control and joint evidence.

    The hardware CLI is LAB_ONLY and zero-output only. Motion-capable policy
    is exercised offline through ControlSupervisor and production C tests.
    This runner cannot silently unlock a chassis or turn a lab package into
    a release. A decoded frame timestamp is not a measured exposure time.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys
import threading
import queue
import copy
import time
import uuid

HERE = Path(__file__).resolve().parent
if not (HERE / "perception_client.py").is_file():
    PROJECT = HERE.parents[1]
    sys.path.insert(0, str(PROJECT / "host"))
    sys.path.insert(0, str(PROJECT.parent / "stm32预备程序" / "pc"))

from board_runtime import Task78BoardRuntime, validate_ip_dict
from overlay_session import DeviceLease, open_verified_overlay, artifact_identity
from frame_association import FrameAssociator
from frame_metadata import encode as encode_frame_metadata
from association_metrics import AssociationMetrics
from joint_evidence import sha256, acquisition_failures
from runtime_identity import session_identity
from frame_pipeline import RawFrameSource, FrameMetrics, build_ffmpeg_command
from lab_acceptance import verify_package, CONTROL_BASE, CONTROL_LENGTH
from perception_client import PerceptionClient, PynqMMIO
from perception_replay import snapshot_registers
from control_supervisor import ControlSupervisor
from calibration_config import CalibrationConfig
import car_regs as reg


def sample_fresh(sample, ticks):
    return sample.valid and ((ticks-sample.timestamp)&0xFFFFFFFF) < 20_000_000


def wait_for_acquisition(client, *, timeout_s=5, stable_s=.3):
    """Bounded pre-session readiness; never hide bad samples inside the test."""
    if not math.isfinite(timeout_s) or not math.isfinite(stable_s) or not 0 < stable_s < timeout_s:
        raise ValueError('invalid acquisition readiness interval')
    deadline=time.monotonic()+timeout_s
    ready_since=None; previous_epoch=None; checks=0; failures=['no samples']
    require_odometry=bool(client.io.read32(reg.QEI0_SCALE) and client.io.read32(reg.QEI1_SCALE))
    try:
        while time.monotonic()<deadline:
            # New stationary bench command, not a renewed driving request.
            client.set_command(forward=False,valid=True)
            ticks,shot,_=client.sample_and_decide()
            checks+=1
            failures=acquisition_failures(snapshot_registers(shot),require_odometry=require_odometry)
            if shot.epoch==previous_epoch:failures.append('snapshot epoch froze')
            previous_epoch=shot.epoch
            for name,sample in [('US',shot.ultrasonic),('QEI0',shot.qei0),('QEI1',shot.qei1),('RISK',shot.risk)]:
                if not sample_fresh(sample,ticks):failures.append(name+' stale')
            if shot.qei0_velocity_q16 or shot.qei1_velocity_q16:
                failures.append('wheels are not stationary')
            now=time.monotonic()
            if failures:ready_since=None
            elif ready_since is None:ready_since=now
            elif now-ready_since>=stable_s:
                return {'schema':'car-startup-readiness/v1','checks':checks,
                        'stable_s':now-ready_since,'odometry_required':require_odometry}
            time.sleep(min(.05,max(0,deadline-now)))
        raise RuntimeError('acquisition readiness timed out: '+', '.join(failures or ['stable interval incomplete']))
    finally:
        client.set_command(forward=False,valid=False)


class JointRunner:
    """Control owns MMIO; the video worker consumes published snapshots only."""
    def __init__(self, client, link, *, video=None, source=None,
                 output_dir, identity, hardware=False, interval_s=0.05, intent_mailbox=None):
        if not math.isfinite(interval_s) or not 0.005 <= interval_s <= 0.1:
            raise ValueError("control interval must be between 5 and 100ms")
        if (video is None) != (source is None):
            raise ValueError("video runtime and frame source must be given together")
        self.client, self.link, self.video, self.source = client, link, video, source
        self.output_dir = Path(output_dir)
        self.identity = dict(identity)
        self.hardware = bool(hardware)
        self.interval_s = interval_s
        self.control = ControlSupervisor(client, link, motion_allowed=False)
        self.intent_mailbox = intent_mailbox
        self.associator = FrameAssociator()
        self.metrics = FrameMetrics()
        self.association_metrics = AssociationMetrics()
        self.stop_event = threading.Event()
        self._journal_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self.latest = None
        self.failures = []
        self.samples = 0
        self.frames = 0
        self.previous_epoch = None
        self.first_stop_response_ms = None
        self._intent_seq = 0
        self._worker = None
        self._journal = None
        self._last_display_car_seq = None
        self.actions = queue.Queue(maxsize=4)
        self.action_status = None

    def log(self, item):
        with self._journal_lock:
            self._journal.write(json.dumps(item, sort_keys=True) + "\n")
            self._journal.flush()

    def fail(self, reason):
        with self._state_lock:
            self.failures.append(str(reason))
        self.stop_event.set()

    def cleanup_bounded(self, name, cleanup, timeout_s=1):
        """A stuck display driver must not prevent UART shutdown/evidence."""
        errors=[]
        def invoke():
            try:cleanup()
            except Exception as exc:errors.append(exc)
        worker=threading.Thread(target=invoke,daemon=True,name='cleanup-'+name)
        worker.start();worker.join(timeout_s)
        if worker.is_alive():self.fail(f'cleanup {name}: timed out; resource termination unconfirmed')
        elif errors:self.fail(f'cleanup {name}: {errors[0]}')

    def step(self):
        try:
            action = self.actions.get_nowait()
        except queue.Empty:
            action = None
        if action:
            self.control.stop()
            if action["kind"] == "calibration":
                try:
                    config = action["config"]
                    config.apply(self.client, motor_disconnected=True)
                    with self._state_lock:
                        self.identity["calibration"] = config.payload()
                    self.action_status = {"kind": "calibration", "applied": True}
                    self.log({"type": "calibration", "configuration": config.payload()})
                except Exception as exc:
                    self.action_status = {"kind": "calibration", "applied": False, "error": str(exc)}
                    raise
            else:
                self.fail("operator requested stop")
                return
        # Explicit bench policy: synthesize NEW ZERO intentions only. The
        # production supervisor never renews an old upstream driving request.
        if self.intent_mailbox is None:
            self._intent_seq += 1
            self.control.submit_intent(self._intent_seq, 0, 0)
        else:
            kind, intent = self.intent_mailbox.consume()
            if kind == 'stop': self.control.stop()
            elif kind == 'intent': self.control.submit_intent(*intent)
        ticks, shot, decision = self.control.tick()
        if self.previous_epoch == shot.epoch:
            raise RuntimeError("snapshot epoch froze in joint session")
        self.previous_epoch = shot.epoch
        before = time.monotonic_ns()
        ticks64 = self.client.read_pl_ticks64()
        after = time.monotonic_ns()
        registers = snapshot_registers(shot)
        anchor = self.associator.publish(
            host_before_ns=before, host_after_ns=after, pl_ticks64=ticks64,
            registers=registers, epoch=shot.epoch,
        )
        event = {"type": "sample", "index": self.samples,
                 "host_monotonic_ns": after, "pl_ticks64": ticks64,
                 "registers": registers, "control": decision,
                 "clock_anchor": {k: v for k, v in anchor.items() if k != "registers"}}
        self.samples += 1
        with self._state_lock:
            self.latest = event
        self.log(event)
        if hasattr(self.link, "status_snapshot"):
            car, car_sequence, car_received = self.link.status_snapshot()
        else:
            car, car_sequence = self.link.state, self.link.state_seq
            car_received = self.link.state_rx_time
        car_age = None if car_received is None else time.monotonic() - car_received
        if car_sequence != self._last_display_car_seq:
            self.client.publish_car_status(car, car_age)
            self._last_display_car_seq = car_sequence
        diagnostics = self.client.display_diagnostics()
        status = {"epoch": shot.epoch, "distance_mm": shot.ultrasonic.data & 4095,
                  "published_monotonic_ns": time.monotonic_ns(),
                  "distance_valid": sample_fresh(shot.ultrasonic, ticks) and ((shot.ultrasonic.data>>12)&15)==0,
                  "speed_mm_s": (shot.qei0_velocity_q16+shot.qei1_velocity_q16)/131072,
                  "speed_valid": sample_fresh(shot.qei0, ticks) and sample_fresh(shot.qei1, ticks),
                  "displacement_mm": shot.displacement_q16/65536,
                  "travelled_mm": shot.travelled_q16/65536,
                  "odometry_valid": shot.odometry_valid,
                  "risk_level": (shot.risk_state >> 1) & 3,
                  "risk_reasons": (shot.risk_state >> 16) & 65535,
                  "pl_stop": bool(shot.risk_state & 1),
                  "car": car, "car_age_s": car_age,
                  "car_sequence": car_sequence,
                  "car_valid": car is not None and car_age is not None and 0 <= car_age < .7,
                  "display": diagnostics}
        with self._state_lock:
            self.latest["status"] = status
        self.log({"type": "status", "host_monotonic_ns": time.monotonic_ns(), **status})
        if car_sequence > self._baseline_car_seq:
            if car is not None and (car["left"] != 0 or car["right"] != 0):
                raise RuntimeError("STM32 reported nonzero PWM in LAB_ONLY session")
            if car and car["lock"] and self.first_stop_response_ms is None:
                self.first_stop_response_ms = (time.monotonic() - self._started) * 1000
                if self.first_stop_response_ms > 300:
                    raise RuntimeError("fresh locked-zero STOP response exceeded 300ms")

    def _video_loop(self):
        try:
            self.video.start()
            if self.stop_event.is_set():return
            with self.source:
                while not self.stop_event.is_set():
                    frame = self.source.read()
                    if frame is None:
                        raise EOFError("camera stream ended during joint session")
                    received = self.source.last_received_ns
                    association = self.associator.associate(self.source.frame_sequence,received)
                    if not association['valid']:
                        raise RuntimeError('frame association failed: '+association['reason'])
                    words=encode_frame_metadata(association)
                    self.video.write_associated(frame,words)
                    submitted = time.monotonic_ns()
                    if self.stop_event.is_set():
                        return
                    association['submitted_host_ns']=submitted
                    association['receive_to_submit_ms']=(submitted-received)/1_000_000
                    association['display_metadata_words']=words
                    self.log({"type": "frame", **association})
                    self.association_metrics.observe(association)
                    if not association["valid"]:
                        raise RuntimeError("frame association failed: " + association["reason"])
                    self.metrics.observe(received)
                    self.frames += 1
        except Exception as exc:
            if not self.stop_event.is_set():
                self.fail(f"video: {type(exc).__name__}: {exc}")
        finally:
            try:self.video.stop()
            except Exception as exc:self.fail(f'cleanup video worker: {exc}')

    def status_snapshot(self):
        with self._state_lock:
            result = copy.deepcopy({"running": self._journal is not None and not self.stop_event.is_set(),
                    "hardware": self.hardware, "motion_allowed": False,
                    "samples": self.samples, "frames": self.frames,
                    "failures": list(self.failures), "identity": dict(self.identity),
                    "action": self.action_status,
                    "latest": self.latest})
        status = (result["latest"] or {}).get("status", {})
        age_s = (time.monotonic_ns()-status.get("published_monotonic_ns",0))/1e9
        result["telemetry_fresh"] = 0 <= age_s < .2
        if status.get("car_age_s") is not None:
            status["car_age_s"] += max(0,age_s)
            status["car_valid"] &= status["car_age_s"] < .7
        if not result["telemetry_fresh"]:
            for name in ("distance_valid", "speed_valid", "odometry_valid", "car_valid"):
                status[name] = False
            status["pl_stop"] = None
        return result

    def enqueue_action(self, kind, payload=None):
        if self.stop_event.is_set() or self._journal is None:
            raise RuntimeError("session is not running")
        if kind not in ("stop", "calibration"):
            raise ValueError("unsupported operator action")
        item = {"kind": kind}
        if kind == "calibration":
            item["config"] = CalibrationConfig.from_payload(payload)
        self.actions.put_nowait(item)
        return {"queued": True, "kind": kind}

    def run(self, duration_s):
        if not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("duration must be positive and finite")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._started = time.monotonic()
        self._started_ns = time.monotonic_ns()
        self.session_id = str(uuid.uuid4())
        self._baseline_car_seq = self.link.state_seq
        self._journal = (self.output_dir / "joint.jsonl").open("w", encoding="utf-8")
        self.log({"type": "header", "schema": "car-joint-session/v1",
                  "hardware": self.hardware, "identity": self.identity,
                  "motor_disconnected": True, "motion_allowed": False,
                  "session_id": self.session_id, "started_host_ns": self._started_ns,
                  "contract_version": reg.CONTRACT_VERSION, "contract_id": reg.INTEGRATED_ID,
                  "tick_hz": 100_000_000, "video_enabled": self.video is not None,
                  "control_interval_s": self.interval_s,
                  "duration_requested_s": duration_s})
        try:
            self.client.verify_contract()
            self.link.start()
            self.control.stop()
            # Publish a clock anchor before the first camera frame arrives.
            self.step()
            if self.video is not None:
                self._worker = threading.Thread(target=self._video_loop, daemon=True)
                self._worker.start()
            deadline = self._started + duration_s
            next_tick = time.monotonic() + self.interval_s
            while time.monotonic() < deadline and not self.stop_event.is_set():
                delay = min(next_tick, deadline) - time.monotonic()
                if delay > 0:
                    self.stop_event.wait(delay)
                if self.stop_event.is_set() or time.monotonic() >= deadline:
                    break
                self.step()
                next_tick += self.interval_s
                if time.monotonic() - next_tick >= self.interval_s:
                    raise RuntimeError("control schedule missed more than one interval")
            if self.first_stop_response_ms is None:
                self.fail("no fresh locked-zero $CAR after STOP request")
            if self.video is not None and self.frames < 1:
                self.fail("no camera frames submitted")
        except KeyboardInterrupt:
            self.fail("operator interrupted session")
        except Exception as exc:
            self.fail(f"control: {type(exc).__name__}: {exc}")
        finally:
            self._ended = time.monotonic()
            self._ended_ns = time.monotonic_ns()
            self.stop_event.set()
            for name, cleanup in (("control", self.control.stop),
                                  ("source", self.source.close if self.source else None)):
                if cleanup is not None:
                    if name=='control':
                        try:cleanup()
                        except Exception as exc:self.fail(f'cleanup control: {exc}')
                    else:self.cleanup_bounded(name,cleanup)
            if self.video is not None and not getattr(self.video,'worker_owned_shutdown',False):
                self.cleanup_bounded('video',self.video.stop)
            if self._worker is not None:
                self._worker.join(timeout=3)
                if self._worker.is_alive():
                    self.fail("video worker did not terminate")
            # Do not free DMA storage while codec/DMA workers still own it.
            if self.video is not None and (self._worker is None or not self._worker.is_alive()):
                self.cleanup_bounded('video', self.video.stop)
            try: self.link.close()
            except Exception as exc: self.fail(f"cleanup UART: {exc}")
            self.log({"type":"end", "ended_host_ns":self._ended_ns,
                      "cleanup_ended_host_ns":time.monotonic_ns(),
                      "session_id":self.session_id,"samples":self.samples,"frames":self.frames,
                      "failures":self.failures})
            self._journal.close()
        result = {"schema": "car-joint-summary/v1", "hardware": self.hardware,
                  "identity": self.identity, "duration_requested_s": duration_s,
                  "duration_observed_s": self._ended - self._started,
                  "cleanup_duration_s": time.monotonic() - self._ended,
                  "samples": self.samples, "frames": self.frames,
                  "first_stop_response_ms": self.first_stop_response_ms,
                  "video_enabled": self.video is not None,
                  "video_metrics": self.metrics.summary(), "failures": self.failures,
                  "passed": not self.failures, "motion_allowed": False,
                  "release_sent": False}
        result["session_id"] = self.session_id
        result["association_metrics"] = self.association_metrics.summary()
        result["journal_sha256"] = sha256(self.output_dir/"joint.jsonl")
        (self.output_dir / "joint_summary.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="single-session no-motor joint test")
    parser.add_argument("--bit", type=Path, default=HERE / "task7_8_LAB_ONLY.bit")
    parser.add_argument("--hwh", type=Path, default=HERE / "task7_8_LAB_ONLY.hwh")
    parser.add_argument("--manifest", type=Path, default=HERE / "lab_manifest.json")
    parser.add_argument("--motor-disconnected", action="store_true")
    parser.add_argument("--port", default="/dev/ttyPS1")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--camera-device", default="/dev/video0")
    parser.add_argument("--ffmpeg", type=Path, default=Path("/usr/bin/ffmpeg"))
    parser.add_argument("--evidence-dir", type=Path, default=HERE / "evidence" / "joint")
    parser.add_argument("--left-scale", type=lambda x: int(x, 0))
    parser.add_argument("--right-scale", type=lambda x: int(x, 0))
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--web-port", type=int)
    parser.add_argument("--web-bind", default="127.0.0.1")
    parser.add_argument("--web-linger", type=float, default=60,
                        help="seconds to keep downloads available after the session")
    args = parser.parse_args(argv)
    if not args.motor_disconnected:
        parser.error("joint test requires --motor-disconnected")
    if (args.left_scale is None) != (args.right_scale is None):
        parser.error("both measured scales must be given together")
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("duration must be positive and finite")
    if args.calibration is not None and args.left_scale is not None:
        parser.error("select a calibration file or an explicit scale pair")
    if args.web_port is not None and not 0 <= args.web_port <= 65535:
        parser.error("web port must be 0..65535")
    if not math.isfinite(args.web_linger) or not 0 <= args.web_linger <= 300:
        parser.error("web linger must be between 0 and 300 seconds")
    try:
        calibration = CalibrationConfig.load(args.calibration) if args.calibration else None
        verify_package(args.bit, args.hwh, args.manifest)
        with DeviceLease():
            overlay = open_verified_overlay(args.bit, args.hwh)
            validate_ip_dict(overlay.ip_dict)
            client = PerceptionClient(PynqMMIO(CONTROL_BASE, CONTROL_LENGTH))
            client.verify_contract()
            if calibration is not None:
                calibration.apply(client, motor_disconnected=True)
            if args.left_scale is not None:
                client.configure_qei_scales(args.left_scale, args.right_scale)
            startup=wait_for_acquisition(client)
            args.evidence_dir.mkdir(parents=True,exist_ok=True)
            (args.evidence_dir/'startup_readiness.json').write_text(
                json.dumps(startup,indent=2)+'\n',encoding='utf-8')
            video = Task78BoardRuntime.from_overlay(overlay) if args.video else None
            source = RawFrameSource(build_ffmpeg_command(
                args.ffmpeg, backend="v4l2", device=args.camera_device)) if args.video else None
            from pynq_link import CarLink
            calibration_identity = calibration.payload() if calibration else {
                "source": "live register readback; measurement provenance unverified",
                "left_scale": client.io.read32(reg.QEI0_SCALE),
                "right_scale": client.io.read32(reg.QEI1_SCALE),
            }
            identity = session_identity(args.bit,args.hwh,args.manifest,calibration_identity)
            link = CarLink(args.port, baud=9600, proto="pynq")
            runner = JointRunner(client, link, video=video, source=source,
                                 output_dir=args.evidence_dir,
                                 identity=identity, hardware=True)
            invoked = False
            try:
                if args.web_port is None:
                    invoked = True
                    summary = runner.run(args.duration)
                else:
                    from status_server import StatusServer
                    with StatusServer(runner, args.web_bind, args.web_port) as server:
                        print(f"状态页面：http://{args.web_bind}:{server.port}/#token={server.token}")
                        invoked = True
                        summary = runner.run(args.duration)
                        if args.web_linger:
                            print("运行已结束，页面暂时保留，供下载日志与验收摘要。")
                            threading.Event().wait(args.web_linger)
            finally:
                if not invoked:
                    link.close()
            print("JOINT_SESSION_" + ("PASS" if summary["passed"] else "FAIL")
                  + " " + json.dumps(summary, sort_keys=True))
            return 0 if summary["passed"] else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"JOINT_SESSION_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__": raise SystemExit(main())
