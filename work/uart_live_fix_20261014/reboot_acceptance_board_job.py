from pathlib import Path
import json,subprocess,sys
assert not Path('/dev/ttyPS1').exists(), 'post-reboot driver unexpectedly already active'
r=subprocess.run([sys.executable,'/home/xilinx/stm32_sensors_platform_20261013/prepare_hybrid.py'],capture_output=True,text=True,check=True)
j=json.loads(r.stdout)
assert j['package']=='/home/xilinx/edge_console_v010_uart_role_fix_20261014_r3'
assert j['risk_enable']==0 and j['qei_scale']==[0,0] and j['debug_console_preserved']
print(json.dumps(dict(kind='POST_REBOOT_STARTUP_ENTRY_PROOF',initial_UART_driver_absent=True,receipt=j)))
"""Actual UART v3 -> PS bridge -> PL snapshots; STOP/query only."""
from pathlib import Path
import base64
import collections
import hashlib
import json
import os
import sys
import time
import zlib
import serial

PACKAGE=Path('/home/xilinx/edge_console_v010_uart_role_fix_20261014_r3')
OUT=Path('/home/xilinx/stm32_sensors_platform_20261013/uart_live_fix_20261014/reboot_acceptance_30s_r1')
OUT.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(PACKAGE));os.chdir(PACKAGE)
from overlay_session import DeviceLease,open_verified_overlay
from lab_acceptance import verify_package,CONTROL_BASE,CONTROL_LENGTH
from perception_client import PerceptionClient,PynqMMIO
from perception_replay import snapshot_registers
from pynq_link import HybridCarLink
import car_regs as reg

class RecordedSerial:
    def __init__(self):
        self.inner=serial.Serial('/dev/ttyPS1',115200,timeout=.02,write_timeout=.2)
        self.rx=bytearray();self.tx=[]
    def read(self,n):
        data=self.inner.read(n);self.rx.extend(data);return data
    def write(self,data):
        self.tx.append(bytes(data));return self.inner.write(data)
    def close(self):self.inner.close()
    def __getattr__(self,name):return getattr(self.inner,name)

result={'kind':'HYBRID_UART_PL_TRIAL','hardware':True,'motor_commands':'query and PSTOP only',
        'sensor_joint_acceptance':False,'duration_target_s':30,'package':str(PACKAGE)}
rows=[]
with DeviceLease():
    bit=PACKAGE/'task7_8_LAB_ONLY.bit';hwh=bit.with_suffix('.hwh')
    manifest=verify_package(bit,hwh,PACKAGE/'lab_manifest.json')
    overlay=open_verified_overlay(bit,hwh,download=False)
    client=PerceptionClient(PynqMMIO(CONTROL_BASE,CONTROL_LENGTH))
    client.verify_contract();client.disable_risk_permit();client.invalidate_qei_scales()
    transport=RecordedSerial();link=HybridCarLink('/dev/ttyPS1',ser=transport)
    try:
        client.attach_sensor_link(link);link.start();start=time.monotonic()
        with (OUT/'samples.jsonl').open('x') as log:
            while time.monotonic()-start<30:
                ticks,shot,decision=client.sample_and_decide()
                report=link.sensor_snapshot();state,seq,stamp=link.status_snapshot()
                row={'elapsed_s':time.monotonic()-start,'pl_ticks':ticks,'epoch':shot.epoch,
                     'report':report,'state':state,'state_sequence':seq,
                     'registers':snapshot_registers(shot),'permit':decision.permit,
                     'reason':list(decision.reasons)}
                rows.append(row);log.write(json.dumps(row)+'\n');log.flush()
                assert not decision.permit
                if state:assert state['left']==state['right']==0 and state['lock']==1
                time.sleep(.05)
        result.update(observed_s=time.monotonic()-start, sensor_errors=link.sensor_errors,
                      transport_error=link.transport_error, state_reports=link.state_seq,
                      uart_rx_bytes=len(transport.rx))
    finally:
        link.close();client.set_command(forward=False,valid=False)
        client.disable_risk_permit();client.invalidate_qei_scales()
        # Revoke external validity after this bounded diagnostic ends.
        client.commit_external_sensors(None,time.monotonic())
        result['final_scale']=[client.io.read32(reg.QEI0_SCALE),client.io.read32(reg.QEI1_SCALE)]
        result['final_external_status']=client.io.read32(reg.EXT_SENSOR_STATUS)
        result['final_risk_enable']=client.io.read32(reg.RISK_ENABLE)

(OUT/'uart_rx.bin').write_bytes(transport.rx)
(OUT/'uart_tx.bin').write_bytes(b'\n'.join(transport.tx))
result['tx_types']=dict(collections.Counter('Q1' if p.startswith(b'$Q1,') else 'PSTOP' if p==b'$PSTOP#' else 'UNEXPECTED' for p in transport.tx))
assert result['tx_types'].get('UNEXPECTED',0)==0
result['samples']=len(rows)
result['valid_us_pl_samples']=sum(bool(r['registers']['US_META']&0x80000000) for r in rows)
result['valid_ir_pl_samples']=sum(bool(r['registers']['IR_META']&0x80000000) for r in rows)
good=[r for r in rows if r['report'] is not None]
result['first_report']=good[0]['report'] if good else None
result['last_report']=good[-1]['report'] if good else None
result['passed']=bool(result['state_reports']>=150 and result['sensor_errors']==0 and result['transport_error'] is None and result['valid_us_pl_samples']>len(rows)*.9 and result['valid_ir_pl_samples']>len(rows)*.9)
result['bit_sha256']=manifest['artifacts']['bit']['sha256']
result['raw_archive_sha256']=hashlib.sha256((OUT/'samples.jsonl').read_bytes()).hexdigest()
(OUT/'result.json').write_text(json.dumps(result,indent=2))
raw=(OUT/'samples.jsonl').read_bytes()
result['samples_zlib_base64']=base64.b64encode(zlib.compress(raw,9)).decode()
result['rx_zlib_base64']=base64.b64encode(zlib.compress(bytes(transport.rx),9)).decode()
result['tx_zlib_base64']=base64.b64encode(zlib.compress(b'\n'.join(transport.tx),9)).decode()
print(json.dumps(result))
