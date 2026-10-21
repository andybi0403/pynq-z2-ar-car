"""One 60-second production HybridCarLink -> PL acceptance, STOP/Q1 only."""
from pathlib import Path
import base64,json,sys,zlib
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tmp'))
from video_six_uart_exec_20261009 import execute
source=(ROOT/'pynq_fpga/preintegration/evidence/car_full_check_20261014/uart_final.py').read_text(encoding='utf8')
source=source.replace('/full_check_20261014/uart_final','/uart_live_fix_20261014/normal_boot_acceptance_30s_r1')
source=source.replace('OUT.mkdir(exist_ok=False)','OUT.mkdir(parents=True,exist_ok=False)')
source=source.replace("'duration_target_s':15","'duration_target_s':30")
source=source.replace('time.monotonic()-start<15','time.monotonic()-start<30')
source=source.replace("result['state_reports']>=20 and result['valid_us_pl_samples']>0 and result['valid_ir_pl_samples']>0",
 "result['state_reports']>=150 and result['sensor_errors']==0 and result['transport_error'] is None and result['valid_us_pl_samples']>len(rows)*.9 and result['valid_ir_pl_samples']>len(rows)*.9")
source=source.replace('print(json.dumps(result))',"result['tx_zlib_base64']=base64.b64encode(zlib.compress(b'\\n'.join(transport.tx),9)).decode()\nprint(json.dumps(result))")
print('Starting 30-second normal-boot production UART/STM32 sensor/PL bridge verification',flush=True)
r=execute(source,seconds=90,root=True,password=None)
(OUT/'normal_boot_acceptance_transport.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
if r['returncode']:
 print(r['output'][-3000:]);raise SystemExit(r['returncode'])
j=next(json.loads(l) for l in r['output'].splitlines() if l.startswith('{') and json.loads(l).get('kind')=='HYBRID_UART_PL_TRIAL')
for key,name in [('samples_zlib_base64','normal_boot_samples.jsonl'),('rx_zlib_base64','normal_boot_uart_rx.bin'),('tx_zlib_base64','normal_boot_uart_tx.bin')]:
 (OUT/name).write_bytes(zlib.decompress(base64.b64decode(j.pop(key))))
(OUT/'normal_boot_acceptance_summary.json').write_text(json.dumps(j,indent=2),encoding='utf8')
print(json.dumps(j,indent=2),flush=True)
if not j['passed']:raise SystemExit(1)
