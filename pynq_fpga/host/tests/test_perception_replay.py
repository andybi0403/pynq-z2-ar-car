import json
import pathlib
import sys
import tempfile
import unittest

HOST = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST))

import car_regs as reg
from perception_client import (
    ContractError, PerceptionClient, snapshot_to_link_sample,
)
from perception_replay import (
    ReplayRegisterIO, load_jsonl, main, replay,
)

import test_night_a_loop as night_a


FIXTURE = HOST / "replays" / "safety_timeline_v1.jsonl"


class ReplayTests(unittest.TestCase):
    def _decision_for(self, updates, *, pl_ticks=10_000_000):
        header, records = load_jsonl(FIXTURE)
        record = json.loads(json.dumps(records[0]))
        record["pl_ticks"] = pl_ticks
        record["expected"] = {"permit": True, "reasons": []}
        record["registers"].update(updates)
        io = ReplayRegisterIO(header, [record])
        client = PerceptionClient(io, snapshot_attempts=1)
        client.verify_contract()
        shot = client.snapshot()
        now32 = client.read_pl_ticks64() & 0xFFFFFFFF
        from perception_client import evaluate_snapshot
        return evaluate_snapshot(shot, now32)

    def test_timeline_uses_production_client(self):
        results = replay(FIXTURE)
        self.assertEqual(len(results), 6)
        self.assertTrue(results[0][2].permit)
        self.assertEqual(results[1][2].reasons, ("us_stale", "risk_stop"))
        self.assertTrue(all(item[2].permit for item in results[2:]))

    def test_corrupt_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "bad.jsonl"
            path.write_text('{"type":"header"\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                load_jsonl(path)

    def test_version_error_is_fail_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "wrong-version.jsonl"
            lines = FIXTURE.read_text(encoding="utf-8").splitlines()
            header = json.loads(lines[0])
            header["contract_version"] = reg.CONTRACT_VERSION - 1
            path.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n",
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contract_version"):
                load_jsonl(path)

    def test_bad_record_reports_first_event_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "bad-record.jsonl"
            lines = FIXTURE.read_text(encoding="utf-8").splitlines()
            item = json.loads(lines[1])
            del item["registers"]["US_TS"]
            path.write_text("\n".join([lines[0], json.dumps(item)]) + "\n",
                            encoding="utf-8")
            self.assertEqual(main(["--transport", "replay", "--input", str(path)]), 1)

    def test_epoch_freeze_and_tear_are_rejected(self):
        header, records = load_jsonl(FIXTURE)
        for fault in ("epoch_freeze", "epoch_tear"):
            broken = [dict(records[0], fault=fault)]
            client = PerceptionClient(ReplayRegisterIO(header, broken), snapshot_attempts=1)
            client.verify_contract()
            with self.assertRaises(ContractError, msg=fault):
                client.snapshot()

    def test_qei_ir_command_and_wrap_faults(self):
        qei = self._decision_for({"QEI0_META": 1})
        self.assertIn("qei0_invalid", qei.reasons)
        ir = self._decision_for({"IR_STATUS": 5})
        self.assertIn("ir_obstacle", ir.reasons)
        command = self._decision_for({"CMD_TS": 0}, pl_ticks=25_000_000)
        self.assertIn("command_stale", command.reasons)
        near_wrap = {
            "US_TS": 0xFFFFFFF8, "QEI0_TS": 0xFFFFFFF8,
            "QEI1_TS": 0xFFFFFFF8, "RISK_TS": 0xFFFFFFF8,
            "CMD_TS": 0xFFFFFFF8,
        }
        self.assertTrue(self._decision_for(near_wrap, pl_ticks=5).permit)

    def test_replay_to_real_c_stop_and_explicit_recovery(self):
        results = replay(FIXTURE)
        c = night_a.CLoop()
        # Establish a real-C moving baseline using the production protocol.
        for ms in (0, 100, 200, 300):
            c.feed_frame(night_a.build_p(0, 0, True, 1000, (ms // 100) % 10, 0, "pynq"), ms)
        c.feed_frame(b"$PREL#", 310)
        self.assertFalse(c.s.latched)
        self.assertTrue(c.feed_frame(night_a.build_p(800, 800, True, 1000, 4, 0, "pynq"), 320))

        now = [0.5]
        link = night_a.CarLink("/dev/null", ser=night_a.MockSerial(), clock_fn=lambda: now[0])

        def frame_for(result, ms, left, right, seq):
            _, shot, decision = result
            now[0] = ms / 1000.0
            sensor = snapshot_to_link_sample(shot, result[0]["pl_ticks"] & 0xFFFFFFFF)
            link.update_sample(sensor.valid, sensor.distance_mm,
                               sensor.infrared_mask, now[0])
            link.update_command(left, right)
            kind, payload = link._decide(now[0])
            if kind == "rel":
                return b"$PREL#"
            if kind in ("drive", "idle_ok"):
                lval, rval, valid, mm, ir = payload
                return night_a.build_p(lval, rval, valid, mm, seq, ir, "pynq")
            return night_a.build_p(0, 0, False, 0, seq, 0, "pynq")

        stale_frame = frame_for(results[1], 500, 800, 800, 5)
        c.feed_frame(stale_frame, 500)
        self.assertTrue(c.s.latched)
        self.assertFalse(c.log[-1][2])

        for seq, (ms, result) in enumerate(zip((600, 700, 800, 900), results[2:]), 6):
            c.feed_frame(frame_for(result, ms, 0, 0, seq), ms)
        link.release_request()
        now[0] = 0.91
        kind, _ = link._decide(now[0])
        self.assertEqual(kind, "rel")
        c.feed_frame(b"$PREL#", 910)
        self.assertFalse(c.s.latched)
        self.assertFalse(c.log[-1][2])

        # PREL authorizes only stopped state; a later new intent restores motion.
        now[0] = 1.0
        link.update_sample(True, 1000, 0, now[0])
        link.update_command(800, 800)
        kind, payload = link._decide(now[0])
        self.assertEqual(kind, "drive")
        c.feed_frame(night_a.build_p(payload[0], payload[1], payload[2],
                                    payload[3], 1, payload[4], "pynq"), 1000)
        self.assertTrue(c.log[-1][2])

    def test_ir_obstacle_reaches_real_c_as_valid_ir(self):
        header, records = load_jsonl(FIXTURE)
        record = json.loads(json.dumps(records[0]))
        record["registers"]["IR_STATUS"] = 5
        record["registers"]["RISK_STATE"] = (1 << 23) | 1
        record["expected"] = {"permit": False,
                              "reasons": ["ir_obstacle", "risk_stop"]}
        io = ReplayRegisterIO(header, [record])
        client = PerceptionClient(io, snapshot_attempts=1)
        now_ticks, shot, decision = client.sample_and_decide()
        self.assertFalse(decision.permit)
        sensor = snapshot_to_link_sample(shot, now_ticks & 0xFFFFFFFF)
        self.assertEqual((sensor.valid, sensor.infrared_mask), (True, 1))

        c = night_a.CLoop()
        frame = night_a.build_p(0, 0, sensor.valid, sensor.distance_mm,
                                0, sensor.infrared_mask, "pynq")
        c.feed_frame(frame, 0)
        self.assertTrue(c.s.reason & night_a.FAULT_IR)
        self.assertFalse(c.s.reason & 8)  # FAULT_SENSOR


if __name__ == "__main__":
    unittest.main()
