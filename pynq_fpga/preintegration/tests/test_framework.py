import json
import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "camera"))

from check_ae_gate import inspect_handoffs
from board_runtime import Task78BoardRuntime, validate_artifact_pair, validate_ip_dict
from frame_pipeline import (
    FrameMetrics, TripleBufferQueue, build_ffmpeg_command, color_bars_bgr0,
    copy_frame, read_exact,
)
from hwh_contract import audit_hwh
from lab_acceptance import (
    camera_metric_mismatches, decode_risk_state, main as lab_main, run_mmio,
    run_safety_loop, run_sensor_check, run_uart_stop, sensor_mismatches,
    verify_package,
)
from perception_client import Odometry
from probe_uvc import parse_dshow_modes
from video_contract import FrameFreshnessGuard, VideoMode, aligned_stride, ddr_traffic_bytes_per_second


class ContractTests(unittest.TestCase):
    HWH = """<EDKSYSTEM>
      <MODULES>
        <MODULE INSTANCE="control_slot_stub" MODTYPE="axi_control_slot_stub" />
        <MODULE INSTANCE="hdmi_dynclk" MODTYPE="axi_dynclk" />
        <MODULE INSTANCE="hdmi_vtc" MODTYPE="v_tc" />
        <MODULE INSTANCE="video_irq_concat" MODTYPE="xlconcat">
          <PORT NAME="dout"><CONNECTION INSTANCE="ps7" PORT="IRQ_F2P"/></PORT>
        </MODULE>
        <MODULE INSTANCE="ps7" MODTYPE="processing_system7" />
        <MODULE INSTANCE="video_vdma" MODTYPE="axi_vdma">
          <PORT NAME="mm2s_introut"><CONNECTION INSTANCE="video_irq_concat" PORT="In0"/></PORT>
        </MODULE>
        <MODULE INSTANCE="hdmi_hpd_gpio" MODTYPE="axi_gpio">
          <PORT NAME="ip2intc_irpt"><CONNECTION INSTANCE="video_irq_concat" PORT="In1"/></PORT>
        </MODULE>
        <MODULE INSTANCE="hdmi_rgb2dvi" MODTYPE="rgb2dvi" />
        <MODULE INSTANCE="hdmi_axis_to_video" MODTYPE="v_axi4s_vid_out">
          <PORT NAME="s_axis_video_tdata" LEFT="23" RIGHT="0" DIR="I" />
        </MODULE>
        <MODULE INSTANCE="osd_slot_stub" MODTYPE="axis_register_slice">
          <PORT NAME="aclk" CLKFREQUENCY="100000000" DIR="I" />
          <PORT NAME="aresetn" POLARITY="ACTIVE_LOW" DIR="I" />
        </MODULE>
      </MODULES>
      <MEMRANGE INSTANCE="control_slot_stub" BASEVALUE="0x43C00000" HIGHVALUE="0x43C00FFF" />
      <MEMRANGE INSTANCE="video_vdma" BASEVALUE="0x43000000" HIGHVALUE="0x4300FFFF" />
      <MEMRANGE INSTANCE="hdmi_dynclk" BASEVALUE="0x43C10000" HIGHVALUE="0x43C1FFFF" />
      <MEMRANGE INSTANCE="hdmi_vtc" BASEVALUE="0x43C20000" HIGHVALUE="0x43C2FFFF" />
      <MEMRANGE INSTANCE="hdmi_hpd_gpio" BASEVALUE="0x41230000" HIGHVALUE="0x4123FFFF" />
      <PORTS>
        <PORT NAME="hdmi_out_clk_n"/><PORT NAME="hdmi_out_clk_p"/>
        <PORT NAME="hdmi_out_data_n"/><PORT NAME="hdmi_out_data_p"/>
        <PORT NAME="hdmi_tx_hpdn" DIR="I"/>
      </PORTS>
    </EDKSYSTEM>"""

    def test_lab_sample_count_guard_applies_to_direct_callers(self):
        """底层入口也必须拒绝空/单样本运行，不能依赖CLI参数检查。"""
        missing = Path("missing")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence.json"
            with self.assertRaisesRegex(ValueError, "at least 2"):
                run_mmio(missing, missing, missing, output, 0, 0.0)
            with self.assertRaisesRegex(ValueError, "at least 2"):
                run_sensor_check(
                    missing, missing, missing, output, 1, 0.0,
                    {"us_valid": 1},
                )

    def test_qei_config_cli_fails_closed_before_any_hardware_access(self):
        """qei-config必须显式给profile或左右scale，且必须先确认电机断开。"""
        missing = Path("missing")
        base = ["qei-config", "--bit", str(missing), "--hwh", str(missing),
                "--manifest", str(missing)]
        cases = [
            base,  # no --motor-disconnected
            base + ["--motor-disconnected"],  # neither profile nor scales
            base + ["--motor-disconnected", "--qei-profile",
                    "TT_48_ORIGINAL_WHEEL_FRONT_2", "--left-scale", "5362"],
            base + ["--motor-disconnected", "--left-scale", "5362"],
        ]
        for argv in cases:
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = lab_main(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn("LAB_QEI_CONFIG_FAIL", errors.getvalue(), argv)
            self.assertNotIn("Traceback", errors.getvalue())

        # Parameter-valid invocation reaches package verification (which must
        # still fail on the missing artifact pair); no evidence file written.
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "qei_config.json"
            with redirect_stderr(errors):
                code = lab_main(base + ["--motor-disconnected", "--qei-profile",
                                        "TT_48_ORIGINAL_WHEEL_FRONT_2",
                                        "--evidence-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("LAB_QEI_CONFIG_FAIL", errors.getvalue())
            self.assertFalse(output.exists())

    def test_malformed_hwh_has_clean_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            bit = folder / "candidate.bit"
            hwh = folder / "candidate.hwh"
            manifest = folder / "manifest.json"
            bit.write_bytes(b"bit")
            hwh.write_text("<not-xml>\x00", encoding="utf-8")
            manifest.write_text("{}", encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                code = lab_main([
                    "contract", "--bit", str(bit), "--hwh", str(hwh),
                    "--manifest", str(manifest),
                ])
            self.assertEqual(code, 1)
            self.assertIn("LAB_CONTRACT_FAIL: hwh not well-formed", errors.getvalue())
            self.assertNotIn("Traceback", errors.getvalue())

    def test_risk_state_decode_exposes_command_baseline(self):
        decoded = decode_risk_state(0x00020007)
        self.assertTrue(decoded["stop"])
        self.assertEqual(decoded["level"], 3)
        self.assertEqual(decoded["reason_bits"], 2)
        self.assertTrue(decoded["command_invalid"])
        self.assertFalse(decoded["command_stale"])

    def test_640x480_budget(self):
        mode = VideoMode(640, 480, 30)
        self.assertEqual(mode.frame_bytes, 1228800)
        self.assertEqual(aligned_stride(640, 4), 2560)
        self.assertEqual(ddr_traffic_bytes_per_second(mode), 147456000)

    def test_invalid_contract_values(self):
        with self.assertRaises(ValueError):
            VideoMode(0, 480, 30).validate()
        with self.assertRaises(ValueError):
            aligned_stride(640, 3, 48)
        with self.assertRaises(ValueError):
            ddr_traffic_bytes_per_second(VideoMode(1, 1, 1), 0)
        registers = {
            "US_DATA": 888,
            "US_META": 0x80000003,
            "IR_STATUS": 0x4,
            "IR_META": 0x80000007,
            "RISK_STATE": 0,
        }
        expected = {
            "us_valid": 1, "us_fault": 0,
            "distance_min": 850, "distance_max": 900,
            "ir_valid": 1, "ir_mask": 0, "ir_stable": 1,
            "risk_stop": 0,
        }
        self.assertEqual(sensor_mismatches(registers, expected), [])
        expected["ir_mask"] = 1
        expected["risk_stop"] = 1
        errors = sensor_mismatches(registers, expected)
        self.assertTrue(any(item.startswith("ir_mask:") for item in errors))
        self.assertTrue(any(item.startswith("risk_stop:") for item in errors))

    def test_frame_freshness_needs_sequence_progress(self):
        guard = FrameFreshnessGuard(timeout_ms=200)
        self.assertFalse(guard.valid(0))
        self.assertTrue(guard.observe(1, 10))
        self.assertFalse(guard.observe(1, 100))
        self.assertTrue(guard.valid(210))
        self.assertFalse(guard.valid(211))

    def test_dshow_parser(self):
        text = "pixel_format=yuyv422  min s=1280x720 fps=30 max s=1280x720 fps=30\n" \
               "pixel_format=nv12  min s=1280x720 fps=30 max s=1280x720 fps=30"
        modes = parse_dshow_modes(text)
        self.assertEqual([m["pixel_format"] for m in modes], ["yuyv422", "nv12"])
        self.assertEqual(modes[0]["width"], 1280)

    def test_gate_requires_all_explicit_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for task in "ABCDE":
                (folder / f"night_20260918_{task}.md").write_text("Status: PASS\n", encoding="utf-8")
            self.assertEqual(inspect_handoffs(folder), [])
            (folder / "night_20260918_C.md").write_text("Status: PARTIAL\n", encoding="utf-8")
            self.assertTrue(any(item.startswith("C:") for item in inspect_handoffs(folder)))

    def test_framework_manifest_is_isolated(self):
        data = json.loads((ROOT / "manifests" / "framework.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "PREINTEGRATION_ONLY")
        self.assertFalse(data["integration_gate"]["bitstream_allowed"])
        self.assertEqual(data["integration_gate"]["required_handoffs"], list("ABCDE"))
        self.assertEqual(data["video"]["pixel_lane_order"], "UNVERIFIED_UNTIL_COLOR_BARS_ON_BOARD")
        self.assertEqual(data["video"]["hpd_signal"], "HDMI_TX_HPDN_ACTIVE_LOW_INPUT")
        self.assertIn("video_vdma/mm2s_introut", data["video"]["interrupts"])
        self.assertTrue(data["generated_hwh_contract"]["mm2s_interrupt_to_ps"])

    def test_verification_manifest_points_to_final_evidence(self):
        data = json.loads(
            (ROOT / "manifests" / "verification_20260919.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(data["status"], "CURRENT_ENVIRONMENT_PASS_HARDWARE_UNVERIFIED")
        self.assertEqual(data["python_tests"], 20)
        self.assertEqual(data["implementation"]["status"], "FULLY_ROUTED")
        self.assertGreaterEqual(data["implementation"]["wns_ns"], 0)
        self.assertGreaterEqual(data["implementation"]["whs_ns"], 0)
        self.assertFalse(data["gates"]["release_bitstream_generated"])
        evidence_root = ROOT.parents[1]
        software_rtl = evidence_root / data["logs"]["software_rtl"]
        synthesis_log = evidence_root / data["logs"]["synthesis"]
        self.assertTrue(software_rtl.is_dir(), f"missing software/RTL evidence: {software_rtl}")
        self.assertTrue(synthesis_log.is_file(), f"missing synthesis log: {synthesis_log}")
        self.assertEqual(synthesis_log.parent, software_rtl)
        synth_text = synthesis_log.read_text(encoding="utf-8-sig", errors="replace")
        self.assertIn("PREINTEGRATION_FRAMEWORK_SYNTH_PASS", synth_text)
        for forbidden in ("Timing 38-249", "Designutils 20-1307", "Common 17-55"):
            self.assertNotIn(forbidden, synth_text)
        for key in ("implementation", "timing_report", "drc_report", "io_report"):
            evidence = evidence_root / data["logs"][key]
            self.assertTrue(evidence.is_file(), f"missing {key}: {evidence}")

        final_log = (ROOT.parents[1] / data["logs"]["implementation"])
        text = final_log.read_text(encoding="utf-8-sig", errors="replace")
        for forbidden in ("CRITICAL WARNING:", "ERROR:", "Timing 38-249",
                          "Designutils 20-1307", "Common 17-55"):
            self.assertNotIn(forbidden, text)

        integrated = json.loads(
            (ROOT / "manifests" / "integrated_verification_20260919.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(integrated["status"],
                         "INTEGRATED_CANDIDATE_PASS_HARDWARE_UNVERIFIED")
        self.assertFalse(integrated["production"]["placeholder_present"])
        self.assertEqual(integrated["production"]["integrated_id"],
                         "0xC4251006")
        self.assertGreaterEqual(integrated["verification"]["wns_ns"], 0)
        self.assertGreaterEqual(integrated["verification"]["whs_ns"], 0)
        self.assertFalse(integrated["release_gate"]["bitstream_generated"])
        for key in ("implementation", "timing_report", "drc_report", "io_report"):
            evidence = ROOT.parents[1] / integrated["logs"][key]
            self.assertTrue(evidence.is_file(), f"missing integrated {key}: {evidence}")

        lab = ROOT.parent / "lab" / "task7_8_lab_only_20260919"
        package = verify_package(
            lab / "task7_8_LAB_ONLY.bit",
            lab / "task7_8_LAB_ONLY.hwh",
            lab / "lab_manifest.json", allow_legacy_contract=True,
        )
        self.assertEqual(package["classification"],
                         "LAB_ONLY_NO_MOTOR_NON_RELEASE")
        self.assertFalse(package["contracts"]["motor_output_allowed"])
        with tempfile.TemporaryDirectory() as temporary:
            tampered = json.loads(json.dumps(package))
            tampered["artifacts"]["bit"]["sha256"] = "0" * 64
            bad_manifest = Path(temporary) / "lab_manifest.json"
            bad_manifest.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_package(
                    lab / "task7_8_LAB_ONLY.bit",
                    lab / "task7_8_LAB_ONLY.hwh",
                    bad_manifest, allow_legacy_contract=True,
                )

    def test_board_runtime_rejects_stale_overlay_contract(self):
        good = {
            name: {"phys_addr": base, "addr_range": span}
            for name, (base, span) in {
                "video_vdma": (0x43000000, 0x10000),
                "car_system": (0x43C00000, 0x1000),
                "hdmi_dynclk": (0x43C10000, 0x10000),
                "hdmi_vtc": (0x43C20000, 0x10000),
                "hdmi_hpd_gpio": (0x41230000, 0x10000),
            }.items()
        }
        self.assertEqual(validate_ip_dict(good)["video_vdma"]["phys_addr"],
                         0x43000000)
        bad = {name: dict(value) for name, value in good.items()}
        bad["video_vdma"]["phys_addr"] = 0xDEADBEEF
        with self.assertRaisesRegex(ValueError, "video_vdma address mismatch"):
            validate_ip_dict(bad)
        stale = {name: dict(value) for name, value in good.items()}
        stale["control_slot_stub"] = stale.pop("car_system")
        with self.assertRaisesRegex(ValueError, "placeholder overlay"):
            validate_ip_dict(stale)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                validate_artifact_pair(folder / "candidate.bit", folder / "candidate.hwh")

    def test_board_runtime_ownership_and_active_low_hpd(self):
        class Channel:
            def __init__(self, value): self.value = value
            def read(self): return self.value
        class GPIO:
            def __init__(self, value): self.channel1 = Channel(value)
        class Display:
            def __init__(self): self.mode_value = None; self.started = False
            def mode(self, value): self.mode_value = value
            def start(self): self.started = True
            def stop(self): self.started = False
        class MM2S:
            def __init__(self): self.mode = None; self.running = False; self.last = None
            def start(self): self.running = True
            def stop(self): self.running = False
            def newframe(self): return bytearray(640 * 480 * 4)
            def writeframe(self, frame): self.last = bytes(frame)
        class VDMA:
            def __init__(self): self.writechannel = MM2S()

        display, vdma = Display(), VDMA()
        runtime = Task78BoardRuntime(
            object(), vdma, display, GPIO(0),
            lambda width, height, bpp, fps: (width, height, bpp, fps),
        )
        self.assertTrue(runtime.monitor_connected)
        runtime.start()
        self.assertEqual(vdma.writechannel.mode, (640, 480, 32, 30))
        runtime.write_bytes(bytes(640 * 480 * 4))
        self.assertEqual(len(vdma.writechannel.last), 640 * 480 * 4)
        runtime.stop()
        self.assertFalse(display.started)

        disconnected = Task78BoardRuntime(
            object(), VDMA(), Display(), GPIO(1), runtime.video_mode_type
        )
        with self.assertRaisesRegex(RuntimeError, "monitor not detected"):
            disconnected.start()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "motor-disconnected"):
                run_uart_stop("unused", 1.0, Path(tmp) / "uart.json", False)
            with self.assertRaisesRegex(ValueError, "motor-disconnected"):
                run_safety_loop(
                    Path("missing.bit"), Path("missing.hwh"), Path("missing.json"),
                    "unused", 1.0, 0.05, Path(tmp) / "safety.json", False,
                )

            class FreshStopLink:
                def __init__(self):
                    self.state_seq = 0
                    self.state = None
                def start(self): pass
                def stop_request(self):
                    self.state = {"left": 0, "right": 0, "lock": 1,
                                  "fault": 1, "mm": 0, "ir": 0, "drop": 0}
                    self.state_seq += 1
                def close(self): pass

            output = Path(tmp) / "fresh_uart.json"
            run_uart_stop("unused", 0.03, output, True,
                          link_factory=FreshStopLink)
            proof = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(proof["fresh_after_request"])
            self.assertLessEqual(proof["first_safe_latency_ms"], 300.0)

            class StaleStopLink(FreshStopLink):
                def __init__(self):
                    self.state_seq = 1
                    self.state = {"left": 0, "right": 0, "lock": 1,
                                  "fault": 1, "mm": 0, "ir": 0, "drop": 0}
                def stop_request(self): pass

            with self.assertRaisesRegex(RuntimeError, "no fresh.*after STOP"):
                run_uart_stop("unused", 0.03, Path(tmp) / "stale_uart.json", True,
                              link_factory=StaleStopLink)

            class FakeClient:
                def __init__(self): self.epoch = 0
                def verify_contract(self): pass
                def sample_and_decide(self):
                    self.epoch += 1
                    sample = lambda data=0: SimpleNamespace(
                        data=data, timestamp=self.epoch, valid=True,
                        sequence=self.epoch,
                    )
                    shot = SimpleNamespace(
                        epoch=self.epoch,
                        ultrasonic=sample(888), infrared=sample(4),
                        qei0_position=0, qei0_period=0, qei0_info=0,
                        qei0_velocity_q16=0, qei0=sample(0),
                        qei1_position=0, qei1_period=0, qei1_info=0,
                        qei1_velocity_q16=0, qei1=sample(0),
                        risk_state=0x00020007, risk_required_mm=250,
                        risk=sample(0), command_state=0,
                        command_timestamp=self.epoch,
                        odometry0=Odometry(), odometry1=Odometry(),
                    )
                    return self.epoch, shot, SimpleNamespace(
                        permit=False, reasons=("command_invalid",)
                    )

            class SafeLoopLink(FreshStopLink):
                def update_sample(self, valid, mm, ir, sample_ts):
                    self.last_sample = (valid, mm, ir, sample_ts)
                def update_command(self, left, right):
                    if (left, right) != (0, 0):
                        raise AssertionError("safety-loop issued non-zero command")

            safety_output = Path(tmp) / "safety.json"
            run_safety_loop(
                Path("unused.bit"), Path("unused.hwh"), Path("unused.json"),
                "unused", 0.02, 0.002, safety_output, True,
                client_factory=FakeClient, link_factory=SafeLoopLink,
            )
            safety = json.loads(safety_output.read_text(encoding="utf-8"))
            self.assertTrue(safety["passed"])
            self.assertFalse(safety["release_sent"])
            self.assertFalse(safety["nonzero_command_sent"])
            self.assertTrue(all(item["zero_command"] for item in safety["timeline"]))
            self.assertEqual(safety["baseline_pl_risk"]["reason_bits"], 2)
            self.assertTrue(safety["baseline_pl_risk"]["command_invalid"])
            self.assertEqual(len(safety["risk_reason_changes"]), 1)
            self.assertTrue(all("pl_risk" in item for item in safety["timeline"]))

    def test_fixed_open_source_snapshots(self):
        expected = {
            "PYNQ": "e054c09c52db3244ef35c8ae08a2e62c1e4955fd",
            "PYNQ-Z2_sobel_filter_HDMI": "71a4409d76470fac7daed6552b9b3188ffe69d8f",
        }
        for name, sha in expected.items():
            head = (ROOT.parent / "third_party" / name / ".git" / "HEAD").read_text(encoding="utf-8").strip()
            self.assertTrue(head.startswith("ref:"))
            ref = head.split(" ", 1)[1]
            value = (ROOT.parent / "third_party" / name / ".git" / ref).read_text(encoding="utf-8").strip()
            self.assertEqual(value, sha)

    def test_ascii_board_repo_matches_user_hardware_sources(self):
        source = ROOT.parents[1] / "pynq-z2资料" / "board_files" / "pynq-z2" / "A.0"
        mirror = ROOT / "board_repo" / "pynq-z2" / "A.0"
        for name in ("board.xml", "part0_pins.xml", "preset.xml", "pynq_z2.jpg"):
            source_hash = hashlib.sha256((source / name).read_bytes()).digest()
            mirror_hash = hashlib.sha256((mirror / name).read_bytes()).digest()
            self.assertEqual(source_hash, mirror_hash, name)

    def test_hwh_contract_and_address_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "framework.hwh"
            path.write_text(self.HWH, encoding="utf-8")
            result = audit_hwh(path)
            self.assertEqual((result.control_base, result.control_size),
                             (0x43C00000, 0x1000))
            self.assertEqual((result.video_bits, result.video_clock_hz),
                             (24, 100_000_000))
            self.assertTrue(result.hpd_is_input)
            self.assertTrue(result.interrupts_to_ps)
            path.write_text(self.HWH.replace('NAME="hdmi_tx_hpdn" DIR="I"',
                                             'NAME="hdmi_tx_hpdn" DIR="O"'),
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "HPDN must be an input"):
                audit_hwh(path)
            path.write_text(self.HWH.replace('PORT="In0"', 'PORT="In9"'),
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "interrupts must route"):
                audit_hwh(path)
            path.write_text(self.HWH.replace("0x43C0", "0x43D0"),
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "control window"):
                audit_hwh(path)

    def test_ffmpeg_bgr0_command_is_argument_safe(self):
        command = build_ffmpeg_command(
            Path("ffmpeg"), backend="dshow", device="Logi C270 HD WebCam"
        )
        self.assertIn("video=Logi C270 HD WebCam", command)
        self.assertIn("scale=640:480:flags=bilinear,fps=30", command)
        self.assertEqual(command[command.index("-pix_fmt") + 1], "bgr0")
        with self.assertRaises(ValueError):
            build_ffmpeg_command(Path("ffmpeg"), backend="unknown", device="x")

    def test_color_bars_match_little_endian_axis_lanes(self):
        frame = color_bars_bgr0(6, 1)
        self.assertEqual(frame[0:4], bytes((0, 0, 255, 0)))
        self.assertEqual(frame[8:12], bytes((0, 255, 0, 0)))
        self.assertEqual(frame[16:20], bytes((255, 0, 0, 0)))
        words = [int.from_bytes(frame[i:i + 4], "little") & 0xFFFFFF
                 for i in (0, 8, 16)]
        self.assertEqual(words, [0xFF0000, 0x00FF00, 0x0000FF])

    def test_partial_frame_read_and_buffer_copy(self):
        class Chunked(io.BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 3))
        frame = read_exact(Chunked(b"abcdefgh"), 8)
        self.assertEqual(frame, b"abcdefgh")
        target = bytearray(8)
        copy_frame(frame, target)
        self.assertEqual(target, frame)
        with self.assertRaises(ValueError):
            copy_frame(b"short", target)
        with self.assertRaises(EOFError):
            read_exact(Chunked(b"short"), 8)

    def test_frame_metrics_reports_gap_and_percentiles(self):
        metrics = FrameMetrics(expected_fps=10)
        for stamp in (0, 100_000_000, 200_000_000, 500_000_000):
            metrics.observe(stamp)
        summary = metrics.summary()
        self.assertEqual(summary["frames"], 4)
        self.assertEqual(summary["inferred_drops"], 2)
        self.assertEqual(summary["interval_p50_ms"], 100)
        self.assertEqual(summary["interval_p99_ms"], 300)
        failures = camera_metric_mismatches(summary, 8.0, 250.0, 0.10)
        self.assertTrue(any(item.startswith("interval_p95_ms:") for item in failures))
        self.assertTrue(any(item.startswith("inferred_drop_rate:") for item in failures))
        passing = {
            "frames": 900, "inferred_drops": 0, "measured_fps": 29.8,
            "interval_p95_ms": 35.0,
        }
        self.assertEqual(camera_metric_mismatches(passing, 25.0, 50.0, 0.05), [])
        self.assertEqual(passing["inferred_drop_rate"], 0)
        with self.assertRaises(ValueError):
            FrameMetrics(expected_fps=0)

    def test_triple_buffer_ownership_prevents_overwrite(self):
        queue = TripleBufferQueue(frame_bytes=4)
        for value in (b"aaaa", b"bbbb", b"cccc"):
            queue.submit(value)
        self.assertEqual(queue.states(), ("READY", "READY", "READY"))
        with self.assertRaises(BufferError):
            queue.submit(b"dddd")

        first = queue.acquire_display()
        self.assertIsNotNone(first)
        index, sequence, view = first
        self.assertEqual((sequence, bytes(view)), (0, b"aaaa"))
        with self.assertRaises(BufferError):
            queue.submit(b"dddd")
        queue.release_display(index)
        reused, new_sequence = queue.submit(b"dddd")
        self.assertEqual((reused, new_sequence), (index, 3))
        self.assertEqual(bytes(queue.buffers[reused]), b"dddd")
        with self.assertRaises(ValueError):
            queue.release_display(reused)


if __name__ == "__main__":
    unittest.main()
