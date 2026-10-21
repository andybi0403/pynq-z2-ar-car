import base64,hashlib,json,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'pynq_fpga/preintegration/evidence/qei_display_20261013'
job=json.loads((OUT/'board_trial_uart.json').read_text('utf8'))
assert job['returncode']==0 and job['pc_network_mutated'] is False
result=next(json.loads(l) for l in job['output'].splitlines() if l.startswith('{') and json.loads(l).get('kind')=='DISPLAY_ESTIMATE_BENCH')
archive=result['raw_archive'];raw=zlib.decompress(base64.b64decode(archive.pop('zlib_base64')))
assert len(raw)==archive['bytes'] and hashlib.sha256(raw).hexdigest()==archive['sha256']
rows=[json.loads(l) for l in raw.splitlines()]
assert len(rows)==result['samples'] and result['completed'] and result['safe_unconfigured']
assert all(r['motion_display']['estimated'] and r['motion_display']['mode']=='stationary_assumption' and
           r['motion_display']['speed_mm_s']==r['motion_display']['travelled_mm']==r['motion_display']['displacement_mm']==0 and
           not r['control_permit'] for r in rows)
for name,data in (('board_samples.jsonl',raw),('board_result.json',json.dumps(result,ensure_ascii=False,indent=2).encode('utf8'))):
    file=OUT/name;assert not file.exists();file.write_bytes(data)
print(json.dumps(result,ensure_ascii=False,indent=2))
