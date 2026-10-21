import glob, hashlib, json, os
from pathlib import Path
facts = {'manifests': []}
for root in ('/home/xilinx', '/boot', '/opt'):
    for directory, dirs, files in os.walk(root):
        depth = len(Path(directory).relative_to(root).parts)
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('lib', 'share', 'include', 'node_modules', '__pycache__')]
        if depth >= 4:
            dirs[:] = []
        if 'lab_manifest.json' in files:
            p = Path(directory)/'lab_manifest.json'
            facts['manifests'].append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
try:
    from pynq import PL
    facts['pl_bitfile_name'] = PL.bitfile_name
except Exception as exc:
    facts['pl_error'] = repr(exc)
print(json.dumps(facts))
