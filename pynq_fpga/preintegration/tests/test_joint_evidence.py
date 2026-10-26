from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from joint_evidence import inspect,sha256
import test_joint_runtime as fixtures


class JointEvidenceTests(unittest.TestCase):
    def test_advisory_ir_does_not_block_acquisition_but_health_check_reports_it(self):
        from joint_evidence import acquisition_failures
        raw={'US_META':0x80000001,'US_DATA':1000,'IR_META':0,'IR_STATUS':0,
             'QEI0_META':0x80000001,'QEI1_META':0x80000001,'RISK_META':0x80000001,
             'QEI0_INFO':0,'QEI1_INFO':0,'QEI0_VEL':0,'QEI1_VEL':0,
             'ODOM0_META':0,'ODOM1_META':0}
        self.assertEqual(acquisition_failures(raw,require_infrared=False),[])
        self.assertIn('ir acquisition invalid',acquisition_failures(raw))
        raw['US_META']=0
        self.assertIn('us acquisition invalid',acquisition_failures(raw,require_infrared=False))

    def test_shutdown_submission_is_validated_but_not_counted_as_active_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            records=[json.loads(row) for row in journal.read_text().splitlines()]
            baseline=inspect(journal,summary,minimum_duration_s=0,require_hardware=False)
            # Exercise this format deterministically rather than depending on
            # thread scheduling at session termination.
            records=[r for r in records if r['type']!='frame_shutdown_submission']
            frame=next(r for r in reversed(records) if r['type']=='frame')
            from frame_metadata import encode
            closing={**frame,'frame_id':frame['frame_id']+1}
            event={'type':'frame_shutdown_submission','frame_id':closing['frame_id'],
                   'received_host_ns':frame['received_host_ns'],
                   'submitted_host_ns':records[-1]['ended_host_ns'],
                   'display_metadata_words':encode(closing)}
            records.insert(-1,event)
            self.rewrite(journal,summary,records)
            result=inspect(journal,summary,minimum_duration_s=0,require_hardware=False)
            self.assertEqual(result['passed'],baseline['passed'])
            event['frame_id']+=1
            self.rewrite(journal,summary,records)
            with self.assertRaisesRegex(ValueError,'shutdown frame metadata identity'):
                inspect(journal,summary,minimum_duration_s=0,require_hardware=False)

    def test_valid_sampled_sofs_are_counted_and_future_sof_still_fails(self):
        # Synthetic branch fixture; missing calibration/package/physical
        # evidence must still prevent a hardware PASS.
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            records=[json.loads(row) for row in journal.read_text().splitlines()]
            records[0]['hardware']=True
            records[0]['started_host_ns']-=3_000_000_000
            frames=[row for row in records if row['type']=='frame']
            observed=[]
            for row in records:
                if row['type']!='status':continue
                prior=[f for f in frames if f['submitted_host_ns']<=row['host_monotonic_ns']]
                if not prior:continue
                frame=prior[-1];ticks=frame['estimated_frame_pl_ticks64']
                sof=ticks+1000
                row['display'].update({'DISPLAY_FRAME_ID':frame['frame_id'],
                    'DISPLAY_FRAME_STATE':(frame['epoch']<<16)|3,
                    'DISPLAY_FRAME_TS_LO':ticks&0xffffffff,'DISPLAY_FRAME_TS_HI':ticks>>32,
                    'DISPLAY_FRAME_AGE':1000,'DISPLAY_HEADER_ERRORS':0,
                    'DISPLAY_TAG_COUNT':frame['frame_id']+1,'DISPLAY_REPEATS':0,
                    'DISPLAY_FRAME_SOF_LO':sof&0xffffffff,'DISPLAY_FRAME_SOF_HI':sof>>32})
                observed.append(row)
            self.assertTrue(observed)
            data=json.loads(summary.read_text());data['hardware']=True
            data['duration_observed_s']+=3;summary.write_text(json.dumps(data))
            self.rewrite(journal,summary,records)
            result=inspect(journal,summary,minimum_duration_s=0,require_hardware=True)
            self.assertFalse(result['passed'])
            self.assertGreater(result['sampled_osd_acceptance_ms']['count'],0)
            self.assertNotIn('no sampled OSD acceptance timing evidence',result['failures'])
            self.assertIn('expected package/configuration identity is missing',result['failures'])
            observed[-1]['display']['DISPLAY_FRAME_SOF_HI']+=1
            self.rewrite(journal,summary,records)
            result=inspect(journal,summary,minimum_duration_s=0,require_hardware=True)
            self.assertIn('OSD acceptance timestamp beyond observed PL clock',result['failures'])

    def rewrite(self,journal,summary,records):
        journal.write_text('\n'.join(json.dumps(row) for row in records)+'\n',encoding='utf-8')
        data=json.loads(summary.read_text());data['journal_sha256']=sha256(journal)
        summary.write_text(json.dumps(data),encoding='utf-8')

    def record(self,tmp):
        runner=fixtures.JointTests().runner(tmp);result=runner.run(.3)
        self.assertTrue(result['passed'],result['failures'])
        return Path(tmp)/'joint.jsonl',Path(tmp)/'joint_summary.json'
    def test_real_thread_log_replays_metrics_and_cannot_grant_hardware_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            result=inspect(journal,summary,minimum_duration_s=.2,require_hardware=False)
            self.assertTrue(result['passed'],result['failures'])
            result=inspect(journal,summary,minimum_duration_s=1800,require_hardware=True)
            self.assertFalse(result['passed'])
            self.assertIn('hardware evidence is missing; software fixture cannot pass',result['failures'])
            self.assertIn('active session shorter than required duration',result['failures'])
    def test_altered_timing_summary_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            data=json.loads(summary.read_text());data['association_metrics']['receive_to_submit_ms']['p95']=0
            summary.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'timing metrics'):
                inspect(journal,summary,minimum_duration_s=0,require_hardware=False)
    def test_rehashing_a_false_raw_frame_association_cannot_bypass_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            rows=[json.loads(row) for row in journal.read_text().splitlines()]
            frame=next(row for row in rows if row['type']=='frame')
            frame['sample_age_ms']['us']+=1
            journal.write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
            data=json.loads(summary.read_text());data['journal_sha256']=sha256(journal);summary.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'association differs'):
                inspect(journal,summary,minimum_duration_s=0,require_hardware=False)
    def test_missing_end_or_wrong_identity_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                inspect(journal,summary,expected_identity={'different':True},minimum_duration_s=0,require_hardware=False)
            rows=journal.read_text().splitlines();journal.write_text('\n'.join(rows[:-1])+'\n')
            data=json.loads(summary.read_text());data['journal_sha256']=sha256(journal);summary.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'incomplete'):
                inspect(journal,summary,minimum_duration_s=0,require_hardware=False)

    def test_consistently_rehashed_invalid_sensor_cannot_pass_healthy_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            records=[json.loads(row) for row in journal.read_text().splitlines()]
            for row in records:
                raw=row.get('registers')
                if raw is not None:raw['US_META'] &= 0x7fffffff
                if row['type']=='frame':
                    from frame_metadata import encode
                    row['display_metadata_words']=encode(row)
            self.rewrite(journal,summary,records)
            result=inspect(journal,summary,minimum_duration_s=.2,require_hardware=False)
            self.assertFalse(result['passed'])
            self.assertIn('us acquisition invalid',result['failures'])

    def test_frozen_pl_clock_rejected_even_with_increasing_epochs(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            records=[json.loads(row) for row in journal.read_text().splitlines()]
            ticks=next(row['pl_ticks64'] for row in records if row['type']=='sample')
            for row in records:
                if row['type']=='sample':
                    row['pl_ticks64']=ticks;row['clock_anchor']['pl_ticks64']=ticks
            self.rewrite(journal,summary,records)
            with self.assertRaisesRegex(ValueError,'elapsed time'):
                inspect(journal,summary,minimum_duration_s=0,require_hardware=False)

    def test_claimed_hardware_display_identity_cannot_reference_unknown_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal,summary=self.record(tmp)
            records=[json.loads(row) for row in journal.read_text().splitlines()]
            # Synthetic tamper case, explicitly never a hardware PASS fixture.
            records[0]['hardware']=True;records[0]['started_host_ns']-=3_000_000_000
            for row in records:
                if row['type']=='status':
                    row['display'].update({'DISPLAY_FRAME_ID':0xffffffff,'DISPLAY_FRAME_STATE':3,
                        'DISPLAY_FRAME_TS_LO':0,'DISPLAY_FRAME_TS_HI':0,'DISPLAY_FRAME_AGE':0,
                        'DISPLAY_HEADER_ERRORS':0,'DISPLAY_TAG_COUNT':1,'DISPLAY_REPEATS':0,
                        'DISPLAY_FRAME_SOF_LO':0,'DISPLAY_FRAME_SOF_HI':0})
            report=json.loads(summary.read_text());report['hardware']=True
            report['duration_observed_s']+=3
            summary.write_text(json.dumps(report))
            self.rewrite(journal,summary,records)
            result=inspect(journal,summary,minimum_duration_s=0,require_hardware=True)
            self.assertFalse(result['passed'])
            self.assertIn('displayed frame identity differs from submitted historical state',result['failures'])
