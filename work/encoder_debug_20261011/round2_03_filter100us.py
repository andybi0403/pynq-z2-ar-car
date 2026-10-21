TRIAL_NAME = 'round2_03_filter100us'
FILTER_TICKS = 10000
DURATION = 45
import base64, hashlib, json, os, sys, time, zlib
from pathlib import Path

PACKAGE = Path('/home/xilinx/video_opt_20261011_candidate_a')
sys.path.insert(0, str(PACKAGE))
os.chdir(PACKAGE)
from lab_acceptance import verify_package
from overlay_session import DeviceLease, open_verified_overlay
from board_runtime import validate_ip_dict
from perception_client import PerceptionClient, PynqMMIO
import car_regs as reg

def temperature():
    p = Path('/sys/bus/iio/devices/iio:device0')
    return (float((p/'in_temp0_raw').read_text()) + float((p/'in_temp0_offset').read_text())) * float((p/'in_temp0_scale').read_text()) / 1000

# TRIAL_NAME, FILTER_TICKS and DURATION are inserted by the local runner.
session = Path('/home/xilinx/encoder_debug_20261011/round2') / TRIAL_NAME
session.mkdir(parents=True, exist_ok=False)
rows = []
result = {'trial': TRIAL_NAME, 'filter_ticks': FILTER_TICKS, 'target_seconds': DURATION,
          'physical_stationary_confirmed': True, 'motor_commands_sent': False,
          'temporary_nominal_profile': 'TT_48_ORIGINAL_WHEEL_FRONT_2'}
with DeviceLease():
    bit = PACKAGE/'task7_8_LAB_ONLY.bit'
    hwh = bit.with_suffix('.hwh')
    verify_package(bit, hwh, PACKAGE/'lab_manifest.json')
    # Reset each trial, including the saturating illegal-transition counters.
    overlay = open_verified_overlay(bit, hwh, download=True)
    validate_ip_dict(overlay.ip_dict)
    io = PynqMMIO(0x43C00000, 0x1000)
    client = PerceptionClient(io)
    client.verify_contract()
    originals = {r: io.read32(r) for r in (reg.QEI0_FILTER, reg.QEI1_FILTER)}
    result['id'] = hex(io.read32(reg.ID_VERSION))
    result['temperature_start_c'] = temperature()
    try:
        client.disable_risk_permit()
        for r in originals:
            io.write32(r, FILTER_TICKS)
            if io.read32(r) != FILTER_TICKS:
                raise RuntimeError('filter readback mismatch')
        client.configure_qei_profile('TT_48_ORIGINAL_WHEEL_FRONT_2')
        time.sleep(1.0)
        start = time.monotonic()
        with (session/'samples.jsonl').open('x') as stream:
            while time.monotonic() - start < DURATION:
                shot = client.snapshot()
                infos = (io.read32(reg.QEI0_INFO), io.read32(reg.QEI1_INFO))
                row = {'t': time.monotonic(), 'epoch': shot.epoch,
                       'left': shot.qei0_position, 'right': shot.qei1_position,
                       'left_info': infos[0], 'right_info': infos[1],
                       'left_illegal': (infos[0] >> 4) & 255, 'right_illegal': (infos[1] >> 4) & 255,
                       'left_filtered': (infos[0] >> 20) & 255, 'right_filtered': (infos[1] >> 20) & 255,
                       'left_sequence': shot.qei0.sequence, 'right_sequence': shot.qei1.sequence}
                rows.append(row)
                stream.write(json.dumps(row)+'\n')
                stream.flush()
                if len(rows) % 100 == 0 and temperature() > 80:
                    raise RuntimeError('temperature threshold exceeded')
                time.sleep(.1)
        result['completed'] = True
    finally:
        client.invalidate_qei_scales()
        for r, value in originals.items():
            io.write32(r, value)
        result['final_registers'] = {name: io.read32(getattr(reg, name)) for name in
            ('QEI0_SCALE', 'QEI1_SCALE', 'QEI0_FILTER', 'QEI1_FILTER', 'RISK_ENABLE')}
        result['temperature_end_c'] = temperature()
        result['restored'] = (result['final_registers']['QEI0_SCALE'] == 0 and
                              result['final_registers']['QEI1_SCALE'] == 0 and
                              result['final_registers']['RISK_ENABLE'] == 0 and
                              all(io.read32(r) == v for r, v in originals.items()))
        (session/'result.json').write_text(json.dumps(result), 'utf8')

result['samples'] = len(rows)
result['observed_seconds'] = rows[-1]['t'] - rows[0]['t']
for channel in ('left', 'right'):
    values = [r[channel] for r in rows]
    result[channel] = {'start': values[0], 'end': values[-1], 'net_delta': values[-1]-values[0],
                       'min': min(values), 'max': max(values),
                       'observed_abs_delta': sum(abs(b-a) for a,b in zip(values,values[1:])),
                       'illegal_start': rows[0][channel+'_illegal'], 'illegal_end': rows[-1][channel+'_illegal'],
                       'filtered_start': rows[0][channel+'_filtered'], 'filtered_end': rows[-1][channel+'_filtered']}
raw = (session/'samples.jsonl').read_bytes()
result['archive'] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                     'zlib_base64': base64.b64encode(zlib.compress(raw, 9)).decode('ascii')}
(session/'result.json').write_text(json.dumps(result), 'utf8')
print(json.dumps(result), flush=True)
