import json, os, signal, sys, time, traceback
from pathlib import Path
PACKAGE = Path('/home/xilinx/video_opt_20261011_candidate_a')
SESSION = Path('/home/xilinx/encoder_debug_20261011/session01')
sys.path.insert(0, str(PACKAGE))
os.chdir(PACKAGE)
from lab_acceptance import verify_package
from overlay_session import DeviceLease, open_verified_overlay
from board_runtime import validate_ip_dict
from perception_client import PerceptionClient, PynqMMIO
import car_regs as reg

def publish(status):
    tmp = SESSION/'status.tmp'
    tmp.write_text(json.dumps(status), 'utf8')
    tmp.replace(SESSION/'status.json')

def temperature():
    p = Path('/sys/bus/iio/devices/iio:device0')
    try:
        return (float((p/'in_temp0_raw').read_text()) + float((p/'in_temp0_offset').read_text())) * float((p/'in_temp0_scale').read_text()) / 1000
    except OSError:
        return None

with DeviceLease():
    bit = PACKAGE/'task7_8_LAB_ONLY.bit'
    hwh = bit.with_suffix('.hwh')
    manifest = verify_package(bit, hwh, PACKAGE/'lab_manifest.json')
    overlay = open_verified_overlay(bit, hwh, download=False)
    validate_ip_dict(overlay.ip_dict)
    io = PynqMMIO(0x43C00000, 0x1000)
    client = PerceptionClient(io)
    client.verify_contract()
    if io.read32(reg.QEI0_SCALE) or io.read32(reg.QEI1_SCALE):
        raise RuntimeError('expected both channels initially uncalibrated')
    status = {'state': 'starting', 'package': str(PACKAGE), 'contract': hex(reg.INTEGRATED_ID),
        'temporary_nominal': True, 'profile': 'TT_48_ORIGINAL_WHEEL_FRONT_2',
        'motor_command_sent': False, 'physical_electrical_verified': False}
    publish(status)
    started = time.monotonic()
    first = None
    try:
        client.disable_risk_permit()
        client.configure_qei_profile('TT_48_ORIGINAL_WHEEL_FRONT_2')
        time.sleep(.25)
        with (SESSION/'samples.jsonl').open('x') as stream:
            while time.monotonic() - started < 600 and not (SESSION/'stop').exists():
                shot = client.snapshot()
                info0, info1 = io.read32(reg.QEI0_INFO), io.read32(reg.QEI1_INFO)
                row = {'t': time.monotonic(), 'epoch': shot.epoch,
                    'left': shot.qei0_position, 'right': shot.qei1_position,
                    'left_info': info0, 'right_info': info1,
                    'left_illegal': (info0 >> 4) & 255, 'right_illegal': (info1 >> 4) & 255,
                    'left_filtered': (info0 >> 20) & 255, 'right_filtered': (info1 >> 20) & 255,
                    'left_sequence': shot.qei0.sequence, 'right_sequence': shot.qei1.sequence,
                    'left_valid': shot.qei0.valid, 'right_valid': shot.qei1.valid}
                if first is None:
                    first = row.copy()
                stream.write(json.dumps(row)+'\n')
                stream.flush()
                if shot.epoch % 10 == 0 or status['state'] == 'starting':
                    status.update(state='running', first=first, latest=row,
                        remaining_seconds=round(600-(time.monotonic()-started)), temperature_c=temperature())
                    publish(status)
                    if status['temperature_c'] is not None and status['temperature_c'] > 80:
                        raise RuntimeError('temperature exceeded conservative bench threshold')
                time.sleep(.1)
    except BaseException as exc:
        status['error'] = repr(exc)
        traceback.print_exc()
    finally:
        try:
            client.invalidate_qei_scales()
            status['left_scale_final'] = io.read32(reg.QEI0_SCALE)
            status['right_scale_final'] = io.read32(reg.QEI1_SCALE)
            status['scales_cleared'] = True
        except Exception as exc:
            status['cleanup_error'] = repr(exc)
            status['scales_cleared'] = False
        status['state'] = 'stopped'
        publish(status)
