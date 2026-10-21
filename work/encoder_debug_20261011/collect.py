import base64, hashlib, json, zlib
from pathlib import Path
session = Path('/home/xilinx/encoder_debug_20261011/session01')
files = {}
for name in ('status.json', 'samples.jsonl', 'markers.jsonl', 'monitor.py', 'monitor.log'):
    p = session/name
    if p.exists():
        body = p.read_bytes()
        files[name] = {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
            'zlib_base64': base64.b64encode(zlib.compress(body, 9)).decode()}
print(json.dumps({'session': str(session), 'files': files}))
