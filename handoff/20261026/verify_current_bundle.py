"""Offline validation of the current r17b handoff; never opens hardware."""
from pathlib import Path
import hashlib,json,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
BUNDLE=ROOT/'pynq_fpga/release/v011_uart_recovery_20261026_r17b'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    manifest=json.loads((BUNDLE/'lab_manifest.json').read_text('utf8'))
    console=json.loads((BUNDLE/'console_manifest.json').read_text('utf8'))
    assert manifest['integrated_id']=='0xC425100B'
    assert manifest['classification']=='LAB_ONLY_NO_MOTOR_NON_RELEASE'
    assert console['classification']=='CONTROLLED_CONSOLE_NOT_RELEASE'
    assert console['production_release_approved'] is False
    assert console['infrared_policy']=='warning_only'
    assert sha(BUNDLE/'lab_manifest.json')==console['base_manifest_sha256']
    checked={}
    for group in ('runtime_files','wireless_files'):
        checked.update(manifest.get(group,{}))
    for group in ('files','desktop_files'):
        checked.update(console[group])
    for value in manifest['artifacts'].values():
        assert sha(BUNDLE/value['file'])==value['sha256'],value['file']
    for name,value in checked.items():
        assert sha(BUNDLE/name)==value,name
    for ext,expected in manifest['source_identity']['stm32_firmware'].items():
        assert sha(BUNDLE/('stm32_hybrid_v3.'+ext))==expected,ext
        assert sha(ROOT/('stm32_pynq对接版/build_safe/safe_car.'+ext))==expected,ext
    # The ARM recovery source snapshot is separate from the inherited FPGA build identity.
    recovery=BUNDLE/'uart_recovery_sources'
    count=0
    for file in recovery.rglob('*'):
        if file.is_file():
            relative=file.relative_to(recovery)
            assert sha(file)==sha(ROOT/relative),str(relative)
            count+=1
    snapshot=json.loads((ROOT/'handoff/20261026/status_snapshot.json').read_text('utf8'))
    assert snapshot['pynq']['uart_recovered'] is False
    assert snapshot['full_vehicle_acceptance']=='NOT_PASSED'
    archive=BUNDLE.with_suffix('.zip')
    expected=json.loads((ROOT/'handoff/20261026/archive_manifest.json').read_text('utf8'))['latest_package_sha256']
    assert sha(archive)==expected
    with zipfile.ZipFile(archive)as z:
        assert z.testzip() is None
        for item in z.infolist():
            if item.is_dir() or '__pycache__' in Path(item.filename).parts:
                continue  # Frozen archive contains optional Python bytecode; Git omits caches.
            assert hashlib.sha256(z.read(item)).hexdigest()==sha(BUNDLE/item.filename),item.filename
    subprocess.run([sys.executable,str(BUNDLE/'deployment_check.py')],check=True)
    print(json.dumps({'bundle':'r17b','file_identities_checked':len(checked),'recovery_sources_checked':count,'package_identity':'PASS','hardware_acceptance':'NOT_PASSED','historical_r2_r3_manifest':'retained as history, not current source identity'}))
if __name__=='__main__':main()

