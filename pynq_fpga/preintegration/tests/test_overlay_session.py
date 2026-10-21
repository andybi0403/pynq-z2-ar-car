import json
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from overlay_session import (DeviceLease, open_verified_overlay,
                             _pynq_loaded_state, _pynq_record_download)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bit, self.hwh = self.root / "x.bit", self.root / "x.hwh"
        self.bit.write_bytes(b"bit"); self.hwh.write_bytes(b"hwh")
        self.record = self.root / "identity.json"
        self.device = SimpleNamespace(timestamp="", loaded=False, scales=(0, 0), downloads=0)
        device = self.device
        class Overlay:
            def __init__(inner, path, download=False):
                inner.device = device
                inner.path = path
            def is_loaded(inner): return device.loaded
            def download(inner):
                device.downloads += 1
                device.timestamp = str(device.downloads)
                device.loaded = True
                device.active_path = inner.path
                device.scales = (0, 0)
        self.factory = Overlay

    def tearDown(self): self.tmp.cleanup()
    def open(self, download=None):
        return open_verified_overlay(self.bit, self.hwh, download=download,
                                     overlay_factory=self.factory, state_path=self.record,
                                     loaded_state_reader=lambda: (
                                         self.device.active_path if self.device.loaded else None,
                                         self.device.timestamp if self.device.loaded else None))

    def test_auto_attach_preserves_calibration_and_downloads_once(self):
        self.open()
        self.device.scales = (5000, 6000)
        self.open(); self.open(False)
        self.assertEqual(self.device.downloads, 1)
        self.assertEqual(self.device.scales, (5000, 6000))

    def test_in_place_artifact_change_refuses_attachment(self):
        self.open(); self.bit.write_bytes(b"different bit")
        with self.assertRaisesRegex(RuntimeError, "hashes/timestamp differ"): self.open()
        self.assertEqual(self.device.downloads, 1)

    def test_stale_or_missing_identity_cannot_prove_current_load(self):
        with self.assertRaisesRegex(RuntimeError, "not loaded"): self.open(False)
        self.open(); self.device.timestamp = "another-download"
        with self.assertRaises(RuntimeError): self.open(False)
        self.record.unlink()
        with self.assertRaises(RuntimeError): self.open()

    def test_explicit_reload_resets_scales_and_updates_identity(self):
        self.open(); self.device.scales = (1, 2)
        self.open(True)
        self.assertEqual(self.device.downloads, 2)
        self.assertEqual(self.device.scales, (0, 0))
        self.assertEqual(json.loads(self.record.read_text())["device_timestamp"], "2")

    def test_new_process_without_device_timestamp_uses_persistent_load_identity(self):
        self.open()
        self.device.scales = (5000, 6000)
        persistent = (str(self.bit.resolve()), self.device.timestamp)
        # PYNQ's fresh EmbeddedDevice has no timestamp attribute. Public PL
        # retrieves the prior download identity from persistent global state.
        class FreshOverlay:
            def __init__(inner, path, download=False):
                inner.device = SimpleNamespace(bitfile_name=path)
            def is_loaded(inner): return True
            def download(inner): raise AssertionError("attachment reprogrammed FPGA")
        overlay = open_verified_overlay(
            self.bit, self.hwh, overlay_factory=FreshOverlay,
            loaded_state_reader=lambda: persistent, state_path=self.record)
        self.assertFalse(hasattr(overlay.device, "timestamp"))
        self.assertEqual(self.device.downloads, 1)
        self.assertEqual(self.device.scales, (5000, 6000))

    def test_constructor_claiming_requested_path_does_not_prove_programming(self):
        state = {"path": None, "timestamp": None, "downloads": 0}
        class MetadataOverlay:
            def __init__(inner, path, download=False): inner.path = path
            def is_loaded(inner): return True  # PYNQ 3.0.1 metadata side effect
            def download(inner):
                state.update(path=inner.path, timestamp="actual-download")
                state["downloads"] += 1
        def open_it(mode):
            return open_verified_overlay(
                self.bit, self.hwh, download=mode, overlay_factory=MetadataOverlay,
                loaded_state_reader=lambda: (state["path"], state["timestamp"]),
                state_path=self.record)
        with self.assertRaisesRegex(RuntimeError, "not loaded"):
            open_it(False)
        self.assertEqual(state["downloads"], 0)
        open_it(None)
        self.assertEqual(state["downloads"], 1)
        state.update(path=str(self.root/'other.bit'), timestamp="external-download")
        with self.assertRaisesRegex(RuntimeError, "not loaded"):
            open_it(False)
        self.assertEqual(state["downloads"], 1)

    def test_pynq_generation_survives_different_process_local_timestamp(self):
        boot_check = Mock()
        sdk = SimpleNamespace(
            initial_global_state_file_boot_check=boot_check,
            global_state_file_exists=lambda: True,
            load_global_state=lambda: SimpleNamespace(
                bitfile_name=str(self.bit), timestamp="before-programming"))
        local = SimpleNamespace(PL=SimpleNamespace(
            bitfile_name=str(self.bit), timestamp="after-programming"))
        with patch.dict(sys.modules, {'pynq':local, 'pynq.pl_server.global_state':sdk}):
            self.assertEqual(_pynq_loaded_state(), (str(self.bit), "before-programming"))
        boot_check.assert_called_once()

    def test_cold_boot_sdk_state_cannot_authorize_attachment(self):
        sdk = SimpleNamespace(
            initial_global_state_file_boot_check=Mock(),
            global_state_file_exists=lambda: False,
            load_global_state=Mock(side_effect=AssertionError("stale record read")))
        with patch.dict(sys.modules, {'pynq.pl_server.global_state':sdk}):
            self.assertEqual(_pynq_loaded_state(), (None, None))

    def test_cached_metadata_download_publishes_completed_identity(self):
        class State:
            def __init__(inner, **fields):
                inner.fields = fields
                inner.shutdown = {}
            def add(inner, name, addr): inner.shutdown[name] = addr
        save = Mock()
        sdk = SimpleNamespace(GlobalState=State, save_global_state=save)
        overlay = SimpleNamespace(
            bitfile_name=str(self.bit),
            device=SimpleNamespace(name='embedded_xrt0', timestamp='completed-load'),
            parser=SimpleNamespace(_from_cache=True, mem_dict={'PSDDR':{'size':42}},
                ip_dict={'shutdown':{'type':'xilinx.com:ip:dfx_axi_shutdown_manager:1.0',
                                    'phys_addr':4096}}))
        with patch.dict(sys.modules, {'pynq.pl_server.global_state':sdk}):
            _pynq_record_download(overlay)
        state = save.call_args.args[0]
        self.assertEqual(state.fields['bitfile_name'], str(self.bit))
        self.assertEqual(state.fields['timestamp'], 'completed-load')
        self.assertEqual(state.fields['psddr'], {'size':42})
        self.assertEqual(state.shutdown, {'shutdown':4096})

    def test_os_lock_excludes_another_owner_and_releases(self):
        path = self.root / "device.lock"
        with DeviceLease(path):
            with self.assertRaisesRegex(RuntimeError, "another process"):
                with DeviceLease(path): pass
        # File still exists; it is not falsely treated as a live owner.
        with DeviceLease(path): pass


if __name__ == "__main__": unittest.main()
