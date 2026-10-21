import json, os, sys, time
from pathlib import Path
PACKAGE = Path('/home/xilinx/video_opt_20261011_candidate_a')
sys.path.insert(0, str(PACKAGE))
os.chdir(PACKAGE)
from lab_acceptance import verify_package
from overlay_session import DeviceLease, open_verified_overlay
from board_runtime import validate_ip_dict
from perception_client import PerceptionClient, PynqMMIO
import car_regs as reg

bit = PACKAGE/'task7_8_LAB_ONLY.bit'
hwh = bit.with_suffix('.hwh')
with DeviceLease():
    manifest = verify_package(bit, hwh, PACKAGE/'lab_manifest.json')
    print(json.dumps({'phase': 'package_verified', 'classification': manifest['classification'],
        'contract': manifest['integrated_id'], 'package': str(PACKAGE)}), flush=True)
    overlay = open_verified_overlay(bit, hwh)
    validate_ip_dict(overlay.ip_dict)
    io = PynqMMIO(0x43C00000, 0x1000)
    client = PerceptionClient(io)
    client.verify_contract()
    print(json.dumps({'phase': 'overlay_loaded', 'bitfile': overlay.bitfile_name,
        'id': hex(io.read32(reg.ID_VERSION)), 'control': hex(io.read32(reg.CTRL)),
        'left_scale': io.read32(reg.QEI0_SCALE), 'right_scale': io.read32(reg.QEI1_SCALE)}), flush=True)
    records = []
    for index in range(30):
        ticks, shot, decision = client.sample_and_decide()
        row = {'index': index, 't': time.monotonic(), 'epoch': shot.epoch,
            'left_position': shot.qei0_position, 'right_position': shot.qei1_position,
            'left_info': io.read32(reg.QEI0_INFO), 'right_info': io.read32(reg.QEI1_INFO),
            'left_meta': io.read32(reg.QEI0_META), 'right_meta': io.read32(reg.QEI1_META),
            'left_period': shot.qei0_period, 'right_period': shot.qei1_period}
        records.append(row)
        time.sleep(.2)
    print(json.dumps({'phase': 'baseline', 'records': records}), flush=True)
