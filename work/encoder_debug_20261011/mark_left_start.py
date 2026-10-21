import json, time
from pathlib import Path
session = Path('/home/xilinx/encoder_debug_20261011/session01')
status = json.loads((session/'status.json').read_text())
if status['state'] != 'running':
    print(status)
    raise RuntimeError('monitor is not running')
rows = (session/'samples.jsonl').read_text().splitlines()
last = json.loads(rows[-1])
marker = {'phase': 'left_one_forward_start', 'marked_at': time.monotonic(), 'sample': last}
with (session/'markers.jsonl').open('a') as stream:
    stream.write(json.dumps(marker)+'\n')
print(json.dumps({'status': status, 'marker': marker}))
