"""Production video lifecycle regression; camera/DMA/MMIO fixtures are software only."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'host'));sys.path.insert(0,str(ROOT/'preintegration/host'))
import tempfile
from unittest.mock import patch
from wireless_runtime import VideoOnlyRunner
from wireless_core import VideoHub,IntentMailbox
class Client:
    def verify_contract(self):pass
class Video:
    def __init__(self,fail_halt):self.fail_halt=fail_halt;self.stopped=False
    def start(self):raise RuntimeError('injected partial DMA startup')
    def stop(self):
        self.stopped=True
        if self.fail_halt:raise RuntimeError('injected DMA halt failure; buffers retained')
class CleanupTests(unittest.TestCase):
    def test_summary_requires_confirmed_DMA_stop(self):
        for fail_halt in (True,False):
            with self.subTest(fail_halt=fail_halt),tempfile.TemporaryDirectory() as folder:
                video=Video(fail_halt)
                runner=VideoOnlyRunner(Client(),None,video=video,source=object(),native=None,
                    hub=VideoHub(),intent_mailbox=IntentMailbox(),output_dir=folder,identity={},hardware=False)
                with patch.object(runner,'step',return_value=None):summary=runner.run(.1)
                self.assertTrue(video.stopped)
                self.assertEqual(summary['resources_closed'],not fail_halt)
                self.assertFalse(summary['passed'])
