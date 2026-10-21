"""A fresh wireless bit can load existing calibration before readiness, no board calls."""
import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'preintegration/host'))
import wireless_runtime as runtime


class StartupTests(unittest.TestCase):
    def test_video_only_never_constructs_uart_or_applies_readiness_gate(self):
        self.video_only_case([])
    def test_headless_does_not_construct_browser_or_discover_network(self):
        with patch('socket.socket') as socket:
            self.video_only_case(['--headless'])
            socket.assert_not_called()
    def test_network_unreachable_still_runs_and_cleans_up(self):
        with patch('socket.socket') as socket:
            socket.return_value.__enter__.return_value.connect.side_effect=OSError('network unreachable')
            self.video_only_case([])
    def video_only_case(self,extra):
        client=MagicMock();runner=MagicMock();runner.run.return_value={'passed':True}
        library=SimpleNamespace(lib=SimpleNamespace(wv_version=lambda:b'car-video/2;libjpeg-turbo/3.1.2'))
        with tempfile.TemporaryDirectory() as tmp:
            native=Path(tmp)/'native.fixture';native.write_bytes(b'fixture')
            with patch.object(runtime,'verify_package'),patch.object(runtime,'verify_wireless',return_value={}), \
                 patch.object(runtime,'NativeLibrary',return_value=library),patch.object(runtime,'DeviceLease'), \
                 patch.object(runtime,'open_verified_overlay',return_value=SimpleNamespace(ip_dict={})), \
                 patch.object(runtime,'validate_ip_dict'),patch.object(runtime,'PerceptionClient',return_value=client), \
                 patch.object(runtime,'PynqMMIO'),patch.object(runtime,'wait_for_acquisition') as ready, \
                 patch.object(runtime,'session_identity',return_value={}),patch('pynq_link.HybridCarLink') as uart, \
                 patch.object(runtime,'WirelessBoardVideo'),patch.object(runtime,'Camera'), \
                 patch.object(runtime,'VideoOnlyRunner',return_value=runner),patch.object(runtime,'WirelessServer') as server:
                server.return_value.__enter__.return_value=SimpleNamespace(port=8080,token='offline')
                self.assertEqual(runtime.main(['--video-only','--native',str(native),'--evidence-dir',str(Path(tmp)/'session')]+extra),0)
                uart.assert_not_called();ready.assert_not_called()
                runner.run.assert_called_once_with(1800)
                if '--headless' in extra:server.assert_not_called()
    def test_video_only_rejects_calibration_before_hardware(self):
        with patch.object(runtime,'verify_package') as verify:
            with self.assertRaises(SystemExit):runtime.main(['--video-only','--calibration','fixture'])
            verify.assert_not_called()
    def test_invalid_video_settings_fail_before_package_or_hardware(self):
        with patch.object(runtime,'verify_package') as verify:
            with self.assertRaises(SystemExit) as error:runtime.main(['--motor-disconnected','--video-mode','manual','--fps','23'])
            self.assertEqual(error.exception.code,2);verify.assert_not_called()
    def test_calibration_precedes_readiness_after_new_overlay(self):
        events=[];config=MagicMock();config.apply.side_effect=lambda *a,**k:events.append('calibration')
        config.payload.return_value={'source':'offline fixture'}
        client=MagicMock();runner=MagicMock();runner.run.return_value={'passed':True}
        library=SimpleNamespace(lib=SimpleNamespace(wv_version=lambda:b'car-video/2;libjpeg-turbo/3.1.2'))
        with tempfile.TemporaryDirectory() as tmp:
            native=Path(tmp)/'native.fixture';native.write_bytes(b'fixture')
            with patch.object(runtime,'verify_package'),patch.object(runtime,'verify_wireless',return_value={}), \
                 patch.object(runtime,'NativeLibrary',return_value=library),patch.object(runtime,'DeviceLease'), \
                 patch.object(runtime,'open_verified_overlay',return_value=SimpleNamespace(ip_dict={})), \
                 patch.object(runtime,'validate_ip_dict'),patch.object(runtime,'PerceptionClient',return_value=client), \
                 patch.object(runtime,'PynqMMIO'),patch.object(runtime.CalibrationConfig,'load',return_value=config), \
                 patch.object(runtime,'wait_for_acquisition',side_effect=lambda c:events.append('ready') or {}), \
                 patch.object(runtime,'session_identity',return_value={}),patch('pynq_link.HybridCarLink'), \
                 patch.object(runtime,'WirelessBoardVideo'),patch.object(runtime,'Camera'), \
                 patch.object(runtime,'WirelessRunner',return_value=runner),patch.object(runtime,'WirelessServer') as server:
                server.return_value.__enter__.return_value=SimpleNamespace(port=8080,token='offline')
                self.assertEqual(runtime.main(['--motor-disconnected','--calibration','fixture','--native',str(native),'--evidence-dir',str(Path(tmp)/'session')]),0)
            self.assertEqual(events,['calibration','ready']);config.apply.assert_called_once_with(client,motor_disconnected=True)


if __name__=='__main__':unittest.main()
