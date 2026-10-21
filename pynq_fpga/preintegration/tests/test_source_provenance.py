import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_provenance as provenance


class SourceProvenanceTests(unittest.TestCase):
    def test_testbenches_board_and_firmware_build_inputs_are_bound(self):
        sources=provenance.current_identity()['sources']
        for name in ('fpga/tb/tb_car_board_video_wrapper.sv',
                     'preintegration/tb/tb_axis32_to_rgb24.sv',
                     'fpga/board/board_manifest.json',
                     'host/c_build/build_car_c_dll.ps1',
                     'workspace/stm32_pynq对接版/safe_startup.c',
                     'workspace/stm32_pynq对接版/safe_stm32f103c8.ld',
                     'workspace/stm32预备程序/build_safe.ps1'):
            self.assertIn(name,sources)

    def test_new_rtl_test_input_changes_identity_and_is_not_silently_ignored(self):
        before=provenance.current_identity()
        with tempfile.NamedTemporaryFile(suffix='.sv',dir=provenance.ROOT/'fpga/tb',delete=False) as stream:
            test_input=Path(stream.name)
            stream.write(b'// temporary provenance regression input\n')
        try:
            after=provenance.current_identity()
            name=test_input.relative_to(provenance.ROOT).as_posix()
            self.assertNotEqual(before,after)
            self.assertEqual(after['sources'][name],provenance.sha256(test_input))
        finally:test_input.unlink()
        self.assertEqual(before,provenance.current_identity())

    def test_generated_candidate_index_is_not_a_build_input(self):
        before=provenance.current_identity()
        with tempfile.NamedTemporaryFile(suffix='.json',dir=provenance.ROOT/'preintegration',delete=False) as stream:
            index=Path(stream.name)
            stream.write(b'{"status":"LAB_ONLY_CANDIDATE"}')
        try:self.assertEqual(before,provenance.current_identity())
        finally:index.unlink()

    def test_production_identity_has_actual_risk_parameters(self):
        identity = provenance.current_identity()
        self.assertEqual(identity['integrated_id'], '0xC425100A')
        self.assertEqual(identity['risk_parameters']['REACTION_MS'], 150)
        self.assertEqual(identity['risk_parameters']['COMMAND_LEASE_TICKS'], 25_000_000)
        self.assertIn('fpga/rtl/car_qei_odometry.v', identity['sources'])
        self.assertIn('preintegration/vivado/create_integrated_candidate.tcl', identity['sources'])

    def test_stale_candidate_is_rejected_and_artifact_hashes_bound(self):
        identity = {'schema':'car-build-source/v1','integrated_id':'0xC4251008',
                    'sources':{'test.v':'hash'}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(provenance,'current_identity',return_value=identity):
            source = Path(tmp)/'source.json'
            source.write_text(json.dumps(identity))
            self.assertEqual(provenance.check(source), identity)
            bit,hwh,out = [Path(tmp)/name for name in ('x.bit','x.hwh','binding.json')]
            bit.write_bytes(b'bitstream'); hwh.write_bytes(b'XML')
            provenance.bind(source,bit,hwh,out)
            payload = json.loads(out.read_text())
            self.assertEqual(payload['artifacts']['bit']['sha256'], provenance.sha256(bit))
            self.assertEqual(payload['source_identity'], identity)
            source.write_text(json.dumps({**identity,'integrated_id':'0xC4251006'}))
            with self.assertRaisesRegex(ValueError,'stale'):
                provenance.check(source)
