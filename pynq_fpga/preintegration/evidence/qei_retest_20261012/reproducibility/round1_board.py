"""Executed on PYNQ by bounded UART helper; disconnected motor bench only."""
import base64,hashlib,json,os,sys,time,zlib
from collections import Counter
from pathlib import Path
PACKAGE=Path('/home/xilinx/qei_quality_20261012_candidate_r1')
sys.path.insert(0,str(PACKAGE));os.chdir(PACKAGE)
from lab_acceptance import verify_package
from overlay_session import DeviceLease,open_verified_overlay
from board_runtime import validate_ip_dict
from perception_client import PerceptionClient,PynqMMIO,evaluate_snapshot
from perception_replay import snapshot_registers
from qei_quality import BENCH_FILTER_TICKS,QeiDisplayFilter,snapshot_fault_reasons
import car_regs as reg

def temperature():
    p=Path('/sys/bus/iio/devices/iio:device0')
    return (float((p/'in_temp0_raw').read_text())+float((p/'in_temp0_offset').read_text()))*float((p/'in_temp0_scale').read_text())/1000

session=Path('/home/xilinx/qei_retest_20261012_evidence/round1')
session.mkdir(parents=True,exist_ok=False)
rows=[];result={'kind':'QEI_QUALITY_TRIAL','duration_target_s':300,
    'physical_motion_expected':False,'physical_stationary_confirmed':True,'operator_confirmation_date':'2026-10-12','motor_disconnected_confirmed_in_session':True,
    'motor_commands_sent':False,'temporary_scale_profile':'TT_48_ORIGINAL_WHEEL_FRONT_2',
    'rollout_calibrated':False,'package':str(PACKAGE),'filter_ticks':BENCH_FILTER_TICKS}
with DeviceLease():
    bit=PACKAGE/'task7_8_LAB_ONLY.bit';hwh=bit.with_suffix('.hwh')
    manifest=verify_package(bit,hwh,PACKAGE/'lab_manifest.json')
    overlay=open_verified_overlay(bit,hwh,download=True)
    validate_ip_dict(overlay.ip_dict)
    io=PynqMMIO(0x43c00000,0x1000);client=PerceptionClient(io)
    client.verify_contract();result['contract_id']=hex(io.read32(reg.ID_VERSION))
    result['bit_sha256']=manifest['artifacts']['bit']['sha256']
    result['temperature_start_c']=temperature();display=QeiDisplayFilter()
    try:
        client.configure_qei_filters(BENCH_FILTER_TICKS,BENCH_FILTER_TICKS,motor_disconnected=True)
        client.configure_qei_profile(result['temporary_scale_profile'])
        result['temporary_scales']=[io.read32(reg.QEI0_SCALE),io.read32(reg.QEI1_SCALE)]
        start=time.monotonic()
        with (session/'samples.jsonl').open('x') as log:
            while time.monotonic()-start<result['duration_target_s']:
                shot=client.snapshot();now64=client.read_pl_ticks64();ticks=now64&0xffffffff
                smooth=display.update(shot,ticks);decision=evaluate_snapshot(shot,ticks)
                row={'elapsed_s':time.monotonic()-start,'pl_ticks64':now64,
                    'registers':snapshot_registers(shot),'epoch':shot.epoch,
                    'control_permit':decision.permit,'control_reasons':decision.reasons}
                for i,side in enumerate(('left','right')):
                    sample=getattr(shot,f'qei{i}');info=getattr(shot,f'qei{i}_info')
                    row[side]={'position':getattr(shot,f'qei{i}_position'),
                        'raw_velocity_q16':getattr(shot,f'qei{i}_velocity_q16'),
                        'raw_valid':sample.valid,'sequence':sample.sequence,'timestamp':sample.timestamp,
                        'illegal':(info>>4)&255,'filtered':(info>>20)&255,'overrun':(info>>12)&255,'odometry_epoch':getattr(shot,f'odometry{i}').epoch,
                        'quality_faults':snapshot_fault_reasons(shot,i),
                        'display_valid':smooth[i].valid,'display_velocity_q16':smooth[i].value_q16,
                        'display_reasons':smooth[i].reasons,'display_source_timestamp':smooth[i].source_timestamp}
                rows.append(row);log.write(json.dumps(row)+'\n');log.flush()
                if len(rows)%100==0 and temperature()>80:raise RuntimeError('temperature threshold')
                time.sleep(.05)
        result['completed']=True
    finally:
        client.disable_risk_permit();client.invalidate_qei_scales()
        result['final_registers']={n:io.read32(getattr(reg,n)) for n in
            ('QEI0_SCALE','QEI1_SCALE','QEI0_FILTER','QEI1_FILTER','RISK_ENABLE')}
        result['temperature_end_c']=temperature()
        result['safe_unconfigured']=all(result['final_registers'][n]==0 for n in ('QEI0_SCALE','QEI1_SCALE','RISK_ENABLE'))
        (session/'result.json').write_text(json.dumps(result),'utf8')

def delta(a,b):return ((a-b+(1<<31))%(1<<32))-(1<<31)
result['samples']=len(rows);result['observed_seconds']=rows[-1]['elapsed_s']-rows[0]['elapsed_s']
result['unexpected_control_permits']=sum(r['control_permit'] for r in rows)
result['channels']={}
for side in ('left','right'):
    values=[r[side] for r in rows];faulted=[v for v in values if v['quality_faults']]
    result['channels'][side]={'start':values[0]['position'],'end':values[-1]['position'],
        'net_delta':delta(values[-1]['position'],values[0]['position']),
        'observed_abs_delta':sum(abs(delta(b['position'],a['position'])) for a,b in zip(values,values[1:])),
        'illegal_start':values[0]['illegal'],'illegal_end':values[-1]['illegal'],
        'filtered_end':values[-1]['filtered'],'overrun_start':values[0]['overrun'],'overrun_end':values[-1]['overrun'],'nonzero_raw_velocity_samples':sum(v['raw_velocity_q16']!=0 for v in values),'maximum_abs_raw_velocity_q16':max(abs(v['raw_velocity_q16']) for v in values),'first_quality_fault_s':next((r['elapsed_s'] for r in rows if r[side]['quality_faults']),None),'raw_valid_samples':sum(v['raw_valid'] for v in values),
        'quality_fault_samples':len(faulted),'faulted_samples_displayed_as_valid':sum(v['display_valid'] for v in faulted),
        'display_valid_samples':sum(v['display_valid'] for v in values),
        'display_reasons':dict(Counter(reason for v in values for reason in v['display_reasons']))}
raw=(session/'samples.jsonl').read_bytes()
result['raw_archive']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
    'zlib_base64':base64.b64encode(zlib.compress(raw,9)).decode()}
(session/'result.json').write_text(json.dumps(result),'utf8')
print(json.dumps(result),flush=True)
assert result['safe_unconfigured'] and result['unexpected_control_permits']==0
assert all(c['faulted_samples_displayed_as_valid']==0 for c in result['channels'].values())
