"""Temporary converter enable control: J1.LA3->JB1 restored, LA5 grounded, OEN wire disconnected from JA9 before grounding; encoders isolated."""
from pathlib import Path
import os,json,time,signal,hashlib,subprocess
os.environ.setdefault('XILINX_XRT','/usr')
root=Path('/home/xilinx/v011_uart_recovery_20261026_r17b')
assert subprocess.check_output(['systemctl','show','pynq-car-console.service','-p','MainPID','--value'],text=True).strip()=='0'
restore=root/'task7_8_LAB_ONLY.bit'
assert hashlib.sha256(restore.read_bytes()).hexdigest()=='1d80069c8254fa9942cde851ee0dfcfbe4d38c22150ec99ed007d5a14df03f6b'
result={'wiring_required':'normal J1.LA3 -> JB1 restored; spare JA5 GND -> J3.LA5; original J2.OEN wire unplugged from JA9 before moving PYNQ end to a verified spare GND on Arduino POWER; JA9 left empty; J3/J4 encoder inputs isolated; J2.3V3/GND and J5 unchanged; temporary bench control only, restore OEN->JA9 after test','pmodb_all_inputs':True,'no_pmod_outputs_configured':True,'motor_commands_sent':False,'calibration_changed':False,'restored':False}
changed=False
def timeout(*args):raise TimeoutError('Ground control deadline reached')
signal.signal(signal.SIGALRM,timeout);signal.alarm(35)
try:
 from pynq import Overlay,MMIO
 from pynq.overlays.base import BaseOverlay
 from pynq.lib.pmod import Pmod_DevMode,PMOD_SWCFG_DIOALL,PMOD_DIO_BASEADDR,PMOD_DIO_TRI_OFFSET
 changed=True;base=BaseOverlay('/home/xilinx/pynq/overlays/base/base.bit')
 b=Pmod_DevMode(base.PMODB,PMOD_SWCFG_DIOALL);b.start()
 b.write_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET,255)
 result['B_direction_readback']=b.read_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET)
 assert result['B_direction_readback']==255
 result['B_input_states']=[]
 for _ in range(32):
  result['B_input_states'].append(b.read_cmd(PMOD_DIO_BASEADDR)&255);time.sleep(.01)
 result['JB1_values']=sorted({v&1 for v in result['B_input_states']})
 result['expected_JB1_low']=result['JB1_values']==[0]
except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
finally:
 signal.alarm(0)
 if changed:
  try:
   Overlay(str(restore));regs=MMIO(0x43c00000,4096)
   result['restored_id']=hex(regs.read(0));result['scales_after_restore']=[regs.read(0x128),regs.read(0x138)]
   result['restored']=regs.read(0)==0xc425100b and result['scales_after_restore']==[0,0]
  except Exception as exc:result['restore_error']=type(exc).__name__+': '+str(exc)
 (root/'gpio_converter_oe_ground_control_20261027.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if result.get('error') or not result['restored']:raise SystemExit(1)
