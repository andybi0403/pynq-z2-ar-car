"""Bounded raw input capture. Restore the car FPGA image on completion/error."""
from pathlib import Path
import os,sys,time,json,signal,hashlib
os.environ.setdefault('XILINX_XRT','/usr')
run=Path(sys.argv[1]);root=run.parent.parent
restore=root/'task7_8_LAB_ONLY.bit'
assert hashlib.sha256(restore.read_bytes()).hexdigest()=='1d80069c8254fa9942cde851ee0dfcfbe4d38c22150ec99ed007d5a14df03f6b'
s={'phase':'loading','pid':os.getpid(),'motor_commands_sent':False,'calibration_changed':False,'sample_count':0,'encoder_states':{},'pin_transitions':[0,0,0,0],'events':[],'restored':False}
def save():
 p=run/'state.tmp';p.write_text(json.dumps(s,indent=2));p.replace(run/'state.json')
def alarm(*args):raise TimeoutError('Raw capture total deadline reached')
signal.signal(signal.SIGALRM,alarm);signal.signal(signal.SIGTERM,alarm);signal.alarm(225)
save();changed=False;a=None
try:
 from pynq import Overlay,MMIO
 from pynq.overlays.base import BaseOverlay
 from pynq.lib.pmod import Pmod_DevMode,PMOD_SWCFG_DIOALL,PMOD_DIO_BASEADDR,PMOD_DIO_TRI_OFFSET
 changed=True;base=BaseOverlay('/home/xilinx/pynq/overlays/base/base.bit');base.select_pmoda()
 b=Pmod_DevMode(base.PMODB,PMOD_SWCFG_DIOALL);b.start();b.write_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET,0xff)
 a=Pmod_DevMode(base.PMODA,PMOD_SWCFG_DIOALL);a.start()
 a.write_cmd(PMOD_DIO_BASEADDR,64);a.write_cmd(PMOD_DIO_BASEADDR+PMOD_DIO_TRI_OFFSET,0xbf)
 a.write_cmd(PMOD_DIO_BASEADDR,0)
 start=time.monotonic();end=start+180;last_save=0;previous=None
 s.update(phase='ready',capture_seconds=180,started_monotonic=start,scope='level transitions only; not calibrated counts or voltage measurement')
 save()
 while time.monotonic()<end and not (run/'stop').exists():
  now=time.monotonic();value=b.read_cmd(PMOD_DIO_BASEADDR)&15
  s['sample_count']+=1;s['encoder_states'][str(value)]=s['encoder_states'].get(str(value),0)+1
  if previous is not None and value!=previous:
   for i in range(4):s['pin_transitions'][i]+=bool((value^previous)&(1<<i))
   if len(s['events'])<80:s['events'].append({'t':round(now-start,3),'from':previous,'to':value})
  previous=value;s['last_value']=value;s['elapsed_s']=round(now-start,3)
  if now-last_save>=1:save();last_save=now
  time.sleep(.003)
except Exception as exc:s['error']=type(exc).__name__+': '+str(exc)
finally:
 signal.alarm(0);s['phase']='restoring';save()
 if changed:
  try:
   if a:a.write_cmd(PMOD_DIO_BASEADDR,64)
  except Exception:pass
  try:
   Overlay(str(restore));regs=MMIO(0x43c00000,4096)
   s['restored_id']=hex(regs.read(0));s['scales_after_restore']=[regs.read(0x128),regs.read(0x138)]
   s['restored']=regs.read(0)==0xc425100b and s['scales_after_restore']==[0,0]
  except Exception as exc:s['restore_error']=type(exc).__name__+': '+str(exc)
 s['phase']='complete' if s['restored'] and not s.get('error') else 'failed';save()
