"""Temporary base-overlay GPIO inspection, with restoration of the verified car image."""
from pathlib import Path
import os,json,subprocess,time,signal,hashlib
os.environ.setdefault('XILINX_XRT','/usr')
unit='pynq-car-console.service'
assert subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()=='0'
root=Path('/home/xilinx/v011_uart_recovery_20261026_r17b')
restore=root/'task7_8_LAB_ONLY.bit'
assert hashlib.sha256(restore.read_bytes()).hexdigest()=='1d80069c8254fa9942cde851ee0dfcfbe4d38c22150ec99ed007d5a14df03f6b'
result={'motor_commands_sent':False,'calibration_changed':False,'pmodb_direction':'all inputs','pmoda_only_output_physical_pin':9,'restored':False}
changed=False
def alarm(*args):raise TimeoutError('GPIO probe deadline reached')
signal.signal(signal.SIGALRM,alarm);signal.alarm(35)
try:
 from pynq import Overlay,MMIO
 from pynq.overlays.base import BaseOverlay
 from pynq.lib.pmod import Pmod_DevMode,PMOD_SWCFG_DIOALL,PMOD_DIO_BASEADDR,PMOD_DIO_TRI_OFFSET
 changed=True
 base=BaseOverlay('/home/xilinx/pynq/overlays/base/base.bit')
 base.select_pmoda()
 b=Pmod_DevMode(base.PMODB,PMOD_SWCFG_DIOALL);b.start()
 b.write_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET,0xff)
 a=Pmod_DevMode(base.PMODA,PMOD_SWCFG_DIOALL);a.start()
 a.write_cmd(PMOD_DIO_BASEADDR,1<<6)
 a.write_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET,0xbf)
 def sample():
  values=[]
  for _ in range(25):
   values.append(b.read_cmd(PMOD_DIO_BASEADDR)&255);time.sleep(.01)
  return {'all_input_states':sorted(set(values)),'encoder_nibble_states':sorted({v&15 for v in values}),'samples':len(values)}
 result['oe_disabled']=sample()
 a.write_cmd(PMOD_DIO_BASEADDR,0)
 result['oe_enabled']=sample()
 a.write_cmd(PMOD_DIO_BASEADDR,1<<6)
except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
finally:
 signal.alarm(0)
 if changed:
  try:
   Overlay(str(restore))
   regs=MMIO(0x43c00000,0x1000)
   result['restored_id']=hex(regs.read(0))
   result['scales_after_restore']=[regs.read(0x128),regs.read(0x138)]
   result['restored']=regs.read(0)==0xc425100b and result['scales_after_restore']==[0,0]
  except Exception as exc:result['restore_error']=type(exc).__name__+': '+str(exc)
 (root/'gpio_static_probe_20261027.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result))
if result.get('error') or not result['restored']:raise SystemExit(1)
