import json
from pathlib import Path
session = Path('/home/xilinx/encoder_debug_20261011/session01')
status = json.loads((session/'status.json').read_text())
last = json.loads((session/'samples.jsonl').read_text().splitlines()[-1])
marker = json.loads((session/'markers.jsonl').read_text().splitlines()[-1])
before = marker['sample']
print(json.dumps({'state': status['state'], 'phase': marker['phase'], 'latest': last,
    'left_delta': last['left'] - before['left'], 'right_delta': last['right'] - before['right'],
    'left_illegal_added': last['left_illegal'] - before['left_illegal'],
    'right_illegal_added': last['right_illegal'] - before['right_illegal'],
    'temperature_c': status.get('temperature_c'), 'remaining_seconds': status.get('remaining_seconds')}))
