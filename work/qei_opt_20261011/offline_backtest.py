"""Run current production quality checks on preserved pre-change observations."""
import hashlib,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pynq_fpga/host'))
from qei_quality import fault_reasons
output=Path('C:/Users/39909/Documents/Codex/2026-10-11/p-g/outputs/qei_algorithm_20261012')
output.mkdir(parents=True,exist_ok=True)
source=output.parent/'encoder_debug_20261011/round3/round3_01_baseline_samples.jsonl'
raw=source.read_bytes();rows=[json.loads(line) for line in raw.splitlines()]
result={'kind':'PREVIOUS_RAW_OBSERVATIONS_PRODUCTION_QUALITY_BACKTEST','source':str(source),
    'source_sha256':hashlib.sha256(raw).hexdigest(),'hardware_samples':len(rows),
    'policy_sha256':hashlib.sha256((ROOT/'pynq_fpga/host/qei_quality.py').read_bytes()).hexdigest(),
    'limitations':'Previous records lack ODOM fault and QEI timestamp. Only observed illegal counters and velocity saturation are checked. No reconstruction of full control decision or display warmup.','channels':{}}
for side in ('left','right'):
    reasons=[fault_reasons(r[side+'_info'],False,r[side+'_velocity_q16']) for r in rows]
    result['channels'][side]={'quality_rejected_samples':sum(bool(r) for r in reasons),
        'reasons':dict(Counter(reason for group in reasons for reason in group)),
        'position_net_delta':rows[-1][side]-rows[0][side],
        'raw_velocity_valid':sum(r[side+'_valid'] for r in rows)}
destination=output/'历史原始数据质量回放.json'
assert not destination.exists();destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
