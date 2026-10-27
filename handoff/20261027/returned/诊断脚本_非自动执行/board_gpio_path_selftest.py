"""Single-channel low/high test after a verified cold-wired JA1 -> J3.LA5 jumper."""
from pathlib import Path
import os,json,time,signal,hashlib,subprocess
os.environ.setdefault('XILINX_XRT','/usr')
root=Path('/home/xilinx/v011_uart_recovery_20261026_r17b')
assert subprocess.check_output(['systemctl','show','pynq-car-console.service','-p','MainPID','--value'],text=True).strip()=='0'
restore=root/'task7_8_LAB_ONLY.bit'
assert hashlib.sha256(restore.read_bytes()).hexdigest()=='1d80069c8254fa9942cde851ee0dfcfbe4d38c22150ec99ed007d5a14df03f6b'
result={'requires_cold_wiring_verified':True,'jumper':'physical JA1 -> J3.LA5; encoder disconnected from J3','only_output_pmoda_pins':[1,9],'pmodb_all_inputs':True,'motor_commands_sent':False,'calibration_changed':False,'restored':False,'trials':[]}
changed=False;a=None
def timeout(*args):raise TimeoutError('Single-channel test deadline reached')
signal.signal(signal.SIGALRM,timeout);signal.alarm(35)
try:
 from pynq import Overlay,MMIO
 from pynq.overlays.base import BaseOverlay
 from pynq.lib.pmod import Pmod_DevMode,PMOD_SWCFG_DIOALL,PMOD_DIO_BASEADDR,PMOD_DIO_TRI_OFFSET
 changed=True;base=BaseOverlay('/home/xilinx/pynq/overlays/base/base.bit');base.select_pmoda()
 b=Pmod_DevMode(base.PMODB,PMOD_SWCFG_DIOALL);b.start();b.write_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET,255)
 a=Pmod_DevMode(base.PMODA,PMOD_SWCFG_DIOALL);a.start()
 a.write_cmd(PMOD_DIO_BASEADDR,64);a.write_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET,0xbe)
 for _ in range(8):
  for level in [0,1]:
   a.write_cmd(PMOD_DIO_BASEADDR,level);time.sleep(.02)
   readings=[b.read_cmd(PMOD_DIO_BASEADDR)&255 for _ in range(4)]
   result['trials'].append({'driven':level,'input_states':readings})
 a.write_cmd(PMOD_DIO_BASEADDR,64)
 result['matching_b_gpio_indexes']=[pin for pin in range(8) if all(((value>>pin)&1)==trial['driven'] for trial in result['trials'] for value in trial['input_states'])]
 result['expected_JB1_tracks']=0 in result['matching_b_gpio_indexes']
except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
finally:
 signal.alarm(0)
 if a:
  try:a.write_cmd(PMOD_DIO_BASEADDR,64)
  except Exception:pass
 if changed:
  try:
   Overlay(str(restore));regs=MMIO(0x43c00000,4096)
   result['restored_id']=hex(regs.read(0));result['scales_after_restore']=[regs.read(0x128),regs.read(0x138)]
   result['restored']=regs.read(0)==0xc425100b and result['scales_after_restore']==[0,0]
  except Exception as exc:result['restore_error']=type(exc).__name__+': '+str(exc)
 (root/'gpio_path_selftest_20261027.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if result.get('error') or not result['restored']:raise SystemExit(1)
