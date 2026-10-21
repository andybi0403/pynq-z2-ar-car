"""Extract and independently audit a hardware trial without hiding bad rows."""
import base64, hashlib, json, sys, zlib
from collections import Counter
from pathlib import Path

envelope=Path(sys.argv[1]);destination=Path(sys.argv[2])
destination.mkdir(parents=True,exist_ok=False)
job=json.loads(envelope.read_text('utf8'))
assert job['returncode']==0 and job['pc_network_mutated'] is False
result=next(json.loads(line) for line in job['output'].splitlines()
            if line.startswith('{') and json.loads(line).get('kind')=='QEI_QUALITY_TRIAL')
archive=result['raw_archive']
raw=zlib.decompress(base64.b64decode(archive.pop('zlib_base64')))
assert len(raw)==archive['bytes'] and hashlib.sha256(raw).hexdigest()==archive['sha256']
(destination/'samples.jsonl').write_bytes(raw)
rows=[json.loads(line) for line in raw.splitlines()]
assert len(rows)==result['samples'] and result['completed'] and result['safe_unconfigured']
assert result['physical_stationary_confirmed']
audit={'kind':'INDEPENDENT_QEI_BENCH_AUDIT','hardware':True,
       'samples':len(rows),'observed_seconds':rows[-1]['elapsed_s']-rows[0]['elapsed_s'],
       'zero_motor_commands':not result['motor_commands_sent'],
       'control_permits':sum(bool(r['control_permit']) for r in rows),
       'final_unconfigured':all(result['final_registers'][n]==0 for n in ('QEI0_SCALE','QEI1_SCALE','RISK_ENABLE')),
       'channels':{}}
def delta(a,b):return ((a-b+(1<<31))%(1<<32))-(1<<31)
for side in ('left','right'):
    values=[r[side] for r in rows]
    observed=sum(abs(delta(b['position'],a['position'])) for a,b in zip(values,values[1:]))
    positions=delta(values[-1]['position'],values[0]['position'])
    diagnostic_bad=[r for r in rows if r[side]['illegal'] or r[side]['overrun'] or r[side]['quality_faults']]
    display_bad=sum(bool(r[side]['display_valid']) for r in diagnostic_bad)
    audit['channels'][side]={'net_delta':positions,'observed_abs_delta':observed,
        'illegal_first':values[0]['illegal'],'illegal_last':values[-1]['illegal'],
        'overrun_last':values[-1]['overrun'],'diagnostic_bad_samples':len(diagnostic_bad),
        'bad_display_valid_samples':display_bad,
        'nonzero_raw_velocity_samples':sum(v['raw_velocity_q16']!=0 for v in values),
        'nonzero_display_velocity_samples':sum(v['display_valid'] and v['display_velocity_q16']!=0 for v in values),
        'reason_counts':dict(Counter(reason for v in values for reason in v['quality_faults'])),
        'stationary_input_pass':observed==0 and not diagnostic_bad}
    expected=result['channels'][side]
    assert positions==expected['net_delta'] and observed==expected['observed_abs_delta']
    assert display_bad==0
    for r in rows:
        v=r[side]
        if v['display_valid']:
            assert ((r['pl_ticks64']-v['display_source_timestamp'])&0xffffffff)<20_000_000
audit['containment_pass']=audit['control_permits']==0 and audit['final_unconfigured'] and all(c['bad_display_valid_samples']==0 for c in audit['channels'].values())
audit['stationary_input_pass']=all(c['stationary_input_pass'] for c in audit['channels'].values())
assert audit['containment_pass']
(destination/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
(destination/'independent_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(audit,ensure_ascii=False,indent=2))
