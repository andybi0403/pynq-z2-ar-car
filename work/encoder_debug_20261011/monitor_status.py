import json
from pathlib import Path
p = Path('/home/xilinx/encoder_debug_20261011/session01')
status = p/'status.json'
print(status.read_text() if status.exists() else json.dumps({'state':'pending'}))
if status.exists() and json.loads(status.read_text())['state'] != 'running':
    print((p/'monitor.log').read_text()[-2000:])
