"""Disconnected-motor display diagnostic; explicit stationary display assumption."""
import base64,hashlib,json,os,sys,time,zlib
from pathlib import Path
PACKAGE=Path('/home/xilinx/qei_display_20261013_candidate_r2')
sys.path.insert(0,str(PACKAGE));os.chdir(PACKAGE)
from lab_acceptance import verify_package
from overlay_session import DeviceLease,open_verified_overlay
from board_runtime import validate_ip_dict
from perception_client import PerceptionClient,PynqMMIO,evaluate_snapshot
from perception_replay import snapshot_registers
from qei_quality import QeiDisplayFilter,BENCH_FILTER_TICKS
from motion_display import MotionDisplayEstimator
import car_regs as reg
session=Path('/home/xilinx/qei_display_20261013_evidence/bench_r2')
session.mkdir(parents=True,exist_ok=False)
rows=[];result={'kind':'DISPLAY_ESTIMATE_BENCH','scope':'actual board display-layer diagnostic; no motion or joint acceptance',
 'stationary_display_assumed':True,'motor_commands_sent':False,'target_seconds':60,
 'temporary_nominal_scale_not_measured':True,'package':str(PACKAGE)}
with DeviceLease():
    bit=PACKAGE/'task7_8_LAB_ONLY.bit';hwh=bit.with_suffix('.hwh')
    manifest=verify_package(bit,hwh,PACKAGE/'lab_manifest.json')
    overlay=open_verified_overlay(bit,hwh,download=True);validate_ip_dict(overlay.ip_dict)
    io=PynqMMIO(0x43c00000,0x1000);client=PerceptionClient(io);client.verify_contract()
    result['bit_sha256']=manifest['artifacts']['bit']['sha256']
    result['configuration']=MotionDisplayEstimator(stationary_assumed=True).configuration()
    median=QeiDisplayFilter();display=MotionDisplayEstimator(stationary_assumed=True)
    try:
        client.configure_qei_filters(BENCH_FILTER_TICKS,BENCH_FILTER_TICKS,motor_disconnected=True)
        client.configure_qei_profile('TT_48_ORIGINAL_WHEEL_FRONT_2')
        start=time.monotonic()
        with (session/'samples.jsonl').open('x') as log:
            while time.monotonic()-start<result['target_seconds']:
                shot=client.snapshot();ticks=client.read_pl_ticks64()
                before=evaluate_snapshot(shot,ticks&0xffffffff)
                clean=median.update(shot,ticks&0xffffffff)
                estimate=display.update(shot,clean,ticks)
                after=evaluate_snapshot(shot,ticks&0xffffffff)
                assert before==after and not before.permit
                row={'elapsed_s':time.monotonic()-start,'pl_ticks64':ticks,'epoch':shot.epoch,
                     'registers':snapshot_registers(shot),'control_permit':before.permit,
                     'measured_speed_valid':all(s.valid for s in clean),'motion_display':estimate}
                rows.append(row);log.write(json.dumps(row)+'\n');log.flush();time.sleep(.05)
        result['completed']=True
    finally:
        client.disable_risk_permit();client.invalidate_qei_scales()
        result['final_registers']={n:io.read32(getattr(reg,n)) for n in ('QEI0_SCALE','QEI1_SCALE','QEI0_FILTER','QEI1_FILTER','RISK_ENABLE')}
        result['safe_unconfigured']=all(result['final_registers'][n]==0 for n in ('QEI0_SCALE','QEI1_SCALE','RISK_ENABLE'))
        (session/'result.json').write_text(json.dumps(result),'utf8')
result['samples']=len(rows);result['observed_seconds']=rows[-1]['elapsed_s']-rows[0]['elapsed_s']
result['zero_estimated_samples']=sum(r['motion_display']['speed_mm_s']==r['motion_display']['displacement_mm']==r['motion_display']['travelled_mm']==0 for r in rows)
result['invalid_measurement_samples']=sum(not r['measured_speed_valid'] for r in rows)
result['control_permits']=sum(r['control_permit'] for r in rows)
result['illegal_last']=[(rows[-1]['registers'][f'QEI{i}_INFO']>>4)&255 for i in (0,1)]
raw=(session/'samples.jsonl').read_bytes()
result['raw_archive']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'zlib_base64':base64.b64encode(zlib.compress(raw,9)).decode()}
(session/'result.json').write_text(json.dumps(result),'utf8')
assert result['zero_estimated_samples']==result['samples'] and result['control_permits']==0 and result['safe_unconfigured']
print(json.dumps(result),flush=True)
