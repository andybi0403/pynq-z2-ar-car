"""Read-only history recomputation; writes a local audit, never contacts hardware."""
from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parent.parent
repo=root/'pynq-z2-ar-car-f9fdb1ce3f7c8c57ac554a2e23a42994ee2469a9'
expected={
 'round1':'89db86b3167f9c62eb3825e19185c7b2cd30a8d08d845eb410f1ae04d3aad8a1',
 'round2':'bc3ba59ceb042f20f20da74bc47a5c1182d990c495658b48c2a7730f6ab60959'
}
def delta(a,b):return ((a-b+(1<<31))%(1<<32))-(1<<31)
result={'scope':'local history and latest evidence only; no hardware operation','rounds':{},'source_hashes':{},'latest_controls':{}}
for name,digest in expected.items():
 p=repo/'pynq_fpga/preintegration/evidence/qei_retest_20261012'/name/'samples.jsonl'
 data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();rows=[json.loads(line) for line in data.decode('utf8').splitlines() if line.strip()]
 summary={'sha256':sha,'matches_received_review_hash':sha==digest,'sample_count':len(rows),'channels':{}}
 for side in ['left','right']:
  values=[r[side]['position'] for r in rows]
  summary['channels'][side]={'position_first':values[0],'position_last':values[-1],'net_count_mod32':delta(values[-1],values[0]),'absolute_steps_between_samples':sum(abs(delta(b,a)) for a,b in zip(values,values[1:])),'illegal_first':rows[0][side]['illegal'],'illegal_last':rows[-1][side]['illegal'],'illegal_max':max(r[side]['illegal'] for r in rows),'overrun_max':max(r[side]['overrun'] for r in rows)}
 result['rounds'][name]=summary
for name in ['car_qei.v','car_board_video_wrapper.v']:
 p=repo/'pynq_fpga/fpga/rtl'/name
 result['source_hashes'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['board_gpio_path_readback-161237.json','board_gpio_jb1_ground_check-163921.json']:
 log=json.loads((root/'硬件检查_20261027'/name).read_text(encoding='utf8'));inner=json.loads(log['output'].strip())
 result['latest_controls'][name]={'host_time':log['time'],'returncode':log['returncode'],'restored':inner['restored'],'restored_id':inner['restored_id'],'scales':inner['scales_after_restore']}
 if 'expected_JB1_tracks' in inner:result['latest_controls'][name].update(expected_JB1_tracks=inner['expected_JB1_tracks'],B_states=sorted({v for t in inner['trials'] for v in t['input_states']}))
 if 'expected_JB1_low' in inner:result['latest_controls'][name].update(expected_JB1_low=inner['expected_JB1_low'],B_states=sorted(set(inner['B_input_states'])),JB1_values=inner['JB1_values'])
out=root/'硬件检查_20261027/历史复核_本机独立核验.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=True,indent=2))
