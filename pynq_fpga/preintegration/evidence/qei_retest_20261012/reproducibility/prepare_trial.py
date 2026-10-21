"""Prepare reproducible bounded board trials from the prior verified sampler."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
base = (ROOT/'work/qei_opt_20261011/board_trial.py').read_text('utf8')
base = base.replace("'physical_motion_expected':False", "'physical_motion_expected':False,'physical_stationary_confirmed':True,'operator_confirmation_date':'2026-10-12'")
base = base.replace("'filtered':(info>>20)&255,", "'filtered':(info>>20)&255,'overrun':(info>>12)&255,'odometry_epoch':getattr(shot,f'odometry{i}').epoch,")
base = base.replace("'filtered_end':values[-1]['filtered'],", "'filtered_end':values[-1]['filtered'],'overrun_start':values[0]['overrun'],'overrun_end':values[-1]['overrun'],'nonzero_raw_velocity_samples':sum(v['raw_velocity_q16']!=0 for v in values),'maximum_abs_raw_velocity_q16':max(abs(v['raw_velocity_q16']) for v in values),'first_quality_fault_s':next((r['elapsed_s'] for r in rows if r[side]['quality_faults']),None),")
for name, package, duration in (
    ('round1', 'qei_quality_20261012_candidate_r1', 300),
    ('round2', 'qei_retest_20261012_candidate_r2', 480),
):
    source = base.replace('/home/xilinx/qei_quality_20261012_candidate_r1', '/home/xilinx/'+package)
    source = source.replace('/home/xilinx/qei_quality_20261012_evidence/bench_r1', '/home/xilinx/qei_retest_20261012_evidence/'+name)
    source = source.replace("'duration_target_s':120", "'duration_target_s':"+str(duration))
    destination = ROOT/'work/qei_retest_20261012'/(name+'_board.py')
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(source, 'utf8')
evidence = ROOT/'pynq_fpga/preintegration/evidence/qei_retest_20261012/operator_confirmation.json'
evidence.write_text(json.dumps({'date_local':'2026-10-12','motor_power_physically_disconnected':True,'nobody_turning_wheels':True,'source':'direct user reply to this chat'},ensure_ascii=False,indent=2),'utf8')
