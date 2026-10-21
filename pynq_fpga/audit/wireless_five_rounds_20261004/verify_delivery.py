"""Read-only final candidate, ZIP and complete source binding check. No board IO."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parent
record = json.loads((ROOT / 'preintegration/latest_candidate.json').read_text(encoding='utf-8'))
assert record['status'] == 'LAB_ONLY_CANDIDATE'
assert record['name'] == 'v09_wireless720_five_20261004_r3'
assert all(stage['status'] == 'PASS' for stage in record['stages'])
folder = Path(record['package_dir'])
archive = Path(record['zip_path'])
assert hashlib.sha256(archive.read_bytes()).hexdigest() == record['zip_sha256']
sys.path.insert(0, str(folder))
from deployment_check import inspect
from wireless_runtime import verify_wireless

deployment = inspect(folder)
assert deployment['passed'] and not deployment['overlay_loaded'] and not deployment['serial_opened']
wireless = verify_wireless(folder / 'lab_manifest.json', folder / 'task7_8_LAB_ONLY.hwh')
manifest = json.loads((folder / 'lab_manifest.json').read_text(encoding='utf-8-sig'))
inventory = json.loads((AUDIT / 'source_inventory.json').read_text(encoding='utf-8'))
assert {item['path']: item['sha256'] for item in inventory['files']} == manifest['source_identity']['sources']
with zipfile.ZipFile(archive) as zipped:
    assert zipped.testzip() is None
    for name in ('lab_manifest.json', 'task7_8_LAB_ONLY.bit', 'task7_8_LAB_ONLY.hwh',
                 *manifest['runtime_files'], *wireless):
        assert zipped.read(name) == (folder / name).read_bytes(), name
result = {'schema': 'car-delivery-verification/v1', 'passed': True,
          'candidate': record['name'], 'zip_sha256': record['zip_sha256'],
          'source_files': inventory['total_files'], 'runtime_files': len(manifest['runtime_files']),
          'wireless_files': len(wireless), 'timing': manifest['timing'],
          'deployment': deployment, 'hardware_performance': 'PENDING'}
(AUDIT / 'round5_evidence/delivery_verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
