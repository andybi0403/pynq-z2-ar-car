"""Exercise the production PowerShell selector, including duplicate rejection."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HELPER=Path(__file__).resolve().parents[1]/'package_inputs.ps1'


@unittest.skipUnless(shutil.which('powershell'), 'Windows PowerShell packaging tool unavailable')
class PackagingInputsTests(unittest.TestCase):
    def invoke(self,root):
        script="& { param($helper,$root) $ErrorActionPreference='Stop'; . $helper; Get-CarLinkSource -WorkspaceRoot $root }"
        return subprocess.run(['powershell','-NoProfile','-Command',script,str(HELPER),str(root)],
                              capture_output=True,text=True,timeout=15)

    def test_nested_audit_copy_cannot_shadow_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            production=root/'production/pc/pynq_link.py'
            backup=root/'project/audit/before/production/pc/pynq_link.py'
            for p in (production,backup):
                p.parent.mkdir(parents=True);p.write_text('# selector fixture\n')
            result=self.invoke(root)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(Path(result.stdout.strip()),production)

    def test_zero_or_two_authoritative_sources_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertNotEqual(self.invoke(root).returncode,0)
            for name in ('production','unexpected_second_project'):
                p=root/name/'pc/pynq_link.py';p.parent.mkdir(parents=True);p.write_text('# duplicate\n')
            result=self.invoke(root)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('found 2',result.stderr)


if __name__=='__main__':unittest.main()
