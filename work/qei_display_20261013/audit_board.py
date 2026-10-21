import json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=root/'pynq_fpga/preintegration/evidence/qei_display_20261013'
raw=(out/'board_samples.jsonl').read_bytes();rows=[json.loads(l) for l in raw.splitlines()]
b=json.loads((out/'board_result.json').read_text('utf8'))
assert hashlib.sha256(raw).hexdigest()==b['raw_archive']['sha256']
def s32(v):return v if v<2**31 else v-2**32
r={'status':'PASS','samples':len(rows),'seconds':rows[-1]['elapsed_s']-rows[0]['elapsed_s'],'stationary_assumption_display_samples':sum(row['motion_display']['mode']=='stationary_assumption' for row in rows),'control_permits':sum(row['control_permit'] for row in rows),'raw_sha256':hashlib.sha256(raw).hexdigest(),'wheels':[]}
for i in range(2):
    key=f'QEI{i}_POS';delta=[s32((c['registers'][key]-a['registers'][key])&0xffffffff) for a,c in zip(rows,rows[1:])]
    r['wheels'].append({'net_count':sum(delta),'max_sample_delta_counts':max(map(abs,delta),default=0),'last_illegal':(rows[-1]['registers'][f'QEI{i}_INFO']>>4)&255,'raw_velocity_peak_mm_s':max(abs(s32(row['registers'][f'QEI{i}_VEL']))/65536 for row in rows)})
assert len(rows)==b['samples'] and r['control_permits']==0 and r['stationary_assumption_display_samples']==len(rows)
file=out/'board_independent_audit.json';assert not file.exists();file.write_text(json.dumps(r,ensure_ascii=False,indent=2),'utf8');print(json.dumps(r,ensure_ascii=False))
