"""Load only the verified new Overlay and enable its existing PS UART1 node."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import os
import sys
import time

PACKAGE=Path('/home/xilinx/edge_console_v010_uart_role_fix_20261014_r3')
PLATFORM=Path('/home/xilinx/stm32_sensors_platform_20261013')
sys.path.insert(0,str(PACKAGE))
os.chdir(PACKAGE)
from lab_acceptance import verify_package,CONTROL_BASE,CONTROL_LENGTH
from wireless_runtime import verify_wireless
from overlay_session import DeviceLease,open_verified_overlay
from board_runtime import validate_ip_dict
from perception_client import PerceptionClient,PynqMMIO
from pynq.devicetree import DeviceTreeSegment
import car_regs as reg

parser=argparse.ArgumentParser()
parser.add_argument('--enable-risk-evaluation',action='store_true',
                    help='enable risk calculation for the existing LAB_ONLY runtime; never enables motor commands')
args=parser.parse_args()

dtbo=base64.b64decode('0A3+7QAAAScAAAA4AAABDAAAACgAAAARAAAAEAAAAAAAAAAbAAAA1AAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAFmcmFnbWVudEAwAAAAAAADAAAAFQAAAAAvYXhpL3NlcmlhbEBlMDAwMTAwMAAAAAAAAAABX19vdmVybGF5X18AAAAAAwAAAAUAAAAMb2theQAAAAAAAAACAAAAAgAAAAFmcmFnbWVudEAxAAAAAAADAAAACQAAAAAvYWxpYXNlcwAAAAAAAAABX19vdmVybGF5X18AAAAAAwAAABUAAAATL2F4aS9zZXJpYWxAZTAwMDEwMDAAAAAAAAAAAgAAAAIAAAACAAAACXRhcmdldC1wYXRoAHN0YXR1cwBzZXJpYWwxAA==')
assert hashlib.sha256(dtbo).hexdigest()=='08b08a51bcc82ef50473764bb1bef7048e8b2a1fbf9f8704763161616c8cbac2'
PLATFORM.mkdir(exist_ok=True)
dtbo_path=PLATFORM/'pynq_car_uart1.dtbo'
if dtbo_path.exists():assert dtbo_path.read_bytes()==dtbo
else:dtbo_path.write_bytes(dtbo)

with DeviceLease():
    bit=PACKAGE/'task7_8_LAB_ONLY.bit'
    hwh=PACKAGE/'task7_8_LAB_ONLY.hwh'
    manifest=verify_package(bit,hwh,PACKAGE/'lab_manifest.json')
    verify_wireless(PACKAGE/'lab_manifest.json',hwh)
    overlay=open_verified_overlay(bit,hwh,download=True)
    checked=validate_ip_dict(overlay.ip_dict)
    io=PynqMMIO(CONTROL_BASE,CONTROL_LENGTH)
    client=PerceptionClient(io)
    client.verify_contract()
    client.set_command(forward=False,valid=False)
    client.disable_risk_permit()
    client.invalidate_qei_scales()
    # Preparation stays stopped by default. The runtime launcher enables
    # calculation after revoking the command and both calibration scales.
    if args.enable_risk_evaluation:io.write32(reg.RISK_ENABLE,1)
    io.write32(reg.EXT_SENSOR_MODE,1)
    assert io.read32(reg.ID_VERSION)==0xC425100A
    assert io.read32(reg.EXT_SENSOR_MODE)==1
    base=Path('/sys/firmware/devicetree/base')
    console_node=base/'axi/serial@e0000000'
    console_before=(console_node/'status').read_bytes()
    target=base/'axi/serial@e0001000'
    assert (target/'reg').read_bytes()==bytes.fromhex('e000100000001000')
    segment=DeviceTreeSegment(str(dtbo_path))
    if not segment.is_dtbo_applied():segment.insert()
    deadline=time.monotonic()+5
    while not Path('/dev/ttyPS1').exists() and time.monotonic()<deadline:time.sleep(.05)
    assert Path('/dev/ttyPS1').is_char_device(), 'UART1 driver did not bind'
    assert (target/'status').read_bytes()==b'okay\0'
    assert (console_node/'status').read_bytes()==console_before
    device=Path('/sys/class/tty/ttyPS1/device').resolve()
    nodes=[p/'of_node' for p in (device,*device.parents) if (p/'of_node/reg').exists()]
    assert nodes and nodes[0].joinpath('reg').read_bytes()==bytes.fromhex('e000100000001000')
    result={'kind':'HYBRID_OVERLAY_AND_UART_READY','package':str(PACKAGE),
            'contract':hex(io.read32(reg.ID_VERSION)),'ip_dict_checked':checked,
            'bit_sha256':manifest['artifacts']['bit']['sha256'],
            'hwh_sha256':manifest['artifacts']['hwh']['sha256'],
            'sensor_source':manifest['sensor_source'],'ext_sensor_mode':io.read32(reg.EXT_SENSOR_MODE),
            'uart_device':'/dev/ttyPS1','uart_of_node':str(nodes[0].resolve()),
            'uart_dtbo_sha256':hashlib.sha256(dtbo).hexdigest(),
            'debug_console_preserved':True,
            'qei_scale':[io.read32(reg.QEI0_SCALE),io.read32(reg.QEI1_SCALE)],
            'risk_enable':io.read32(reg.RISK_ENABLE),'motor_command_sent':False,
            'risk_evaluation_requested':args.enable_risk_evaluation,
            'kernel_messages':os.popen('dmesg | tail -n 10').read()}
    (PLATFORM/'load_receipt.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
