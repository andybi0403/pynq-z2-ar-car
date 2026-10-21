"""Replay real captures through production decoders; estimates remain labelled."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pynq_fpga/host'))
from perception_client import PerceptionClient,evaluate_snapshot
from perception_replay import ReplayRegisterIO
from qei_quality import QeiDisplayFilter
from motion_display import MotionDisplayEstimator
import car_regs as reg
OUT=ROOT/'pynq_fpga/preintegration/evidence/qei_display_20261013'
OUT.mkdir(parents=True,exist_ok=True)
summary={'scope':'offline replay of actual hardware captures; not a new board test','stationary_source':'direct user confirmation preserved in qei_retest_20261012/operator_confirmation.json','rounds':[]}
for name in ('round1','round2'):
    source=ROOT/'pynq_fpga/preintegration/evidence/qei_retest_20261012'/name/'samples.jsonl'
    original=source.read_bytes();rows=[json.loads(l) for l in original.splitlines()]
    records=[{'pl_ticks':r['pl_ticks64'],'epoch':r['epoch'],'registers':r['registers']} for r in rows]
    io=ReplayRegisterIO({'contract_id':reg.INTEGRATED_ID},records);client=PerceptionClient(io)
    median=QeiDisplayFilter();estimate=MotionDisplayEstimator(stationary_assumed=True)
    destination=OUT/(name+'_display_replay.jsonl');assert not destination.exists()
    permits=0;faulted=0;bad_measurement_still_invalid=0;zero_estimates=0
    with destination.open('x',encoding='utf8') as output:
        for row in rows:
            shot=client.snapshot();ticks64=client.read_pl_ticks64();ticks=ticks64&0xffffffff
            before=evaluate_snapshot(shot,ticks)
            clean=median.update(shot,ticks)
            display=estimate.update(shot,clean,ticks64)
            assert before==evaluate_snapshot(shot,ticks)
            assert before.permit==row['control_permit']
            permits+=int(before.permit)
            faults=any(row[s]['quality_faults'] for s in ('left','right'))
            faulted+=int(faults)
            bad_measurement_still_invalid+=int(faults and not all(s.valid for s in clean))
            assert display['estimated'] and display['mode']=='stationary_assumption'
            assert display['speed_mm_s']==display['displacement_mm']==display['travelled_mm']==0
            zero_estimates+=1
            output.write(json.dumps({'elapsed_s':row['elapsed_s'],'raw_left_mm_s':shot.qei0_velocity_q16/65536,
                'raw_right_mm_s':shot.qei1_velocity_q16/65536,'measured_speed_valid':all(s.valid for s in clean),
                'control_permit':before.permit,'motion_display':display},ensure_ascii=False)+'\n')
    assert source.read_bytes()==original
    assert permits==0 and faulted==bad_measurement_still_invalid and zero_estimates==len(rows)
    summary['rounds'].append({'name':name,'samples':len(rows),'control_permits':permits,'faulted_samples':faulted,
        'faults_not_promoted_to_measured':bad_measurement_still_invalid,'stable_zero_estimates':zero_estimates,
        'original_sha256':hashlib.sha256(original).hexdigest(),'replay_sha256':hashlib.sha256(destination.read_bytes()).hexdigest()})
target=OUT/'replay_summary.json';assert not target.exists();target.write_text(json.dumps(summary,indent=2),'utf8')
print(json.dumps(summary,indent=2))
