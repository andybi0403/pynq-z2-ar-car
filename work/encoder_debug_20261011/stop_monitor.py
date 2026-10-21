import json, time
from pathlib import Path
session = Path('/home/xilinx/encoder_debug_20261011/session01')
last = json.loads((session/'samples.jsonl').read_text().splitlines()[-1])
with (session/'markers.jsonl').open('a') as stream:
    stream.write(json.dumps({'phase': 'capture_stopped_for_illegal_edges', 'marked_at': time.monotonic(), 'sample': last})+'\n')
(session/'stop').touch()
for _ in range(30):
    status = json.loads((session/'status.json').read_text())
    if status['state'] == 'stopped':
        print(json.dumps(status))
        break
    time.sleep(.1)
else:
    raise RuntimeError('monitor has not confirmed cleanup')
