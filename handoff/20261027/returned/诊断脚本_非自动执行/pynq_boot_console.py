"""Bounded U-Boot inspection, or resume its existing default boot without saving configuration."""
from pathlib import Path
import argparse,json,sys,time,re
sys.path.insert(0,str(Path(__file__).resolve().parent/'deps'))
import serial
from serial.tools import list_ports
from pynq_check import clean,read_for
from datetime import datetime,timezone,timedelta
parser=argparse.ArgumentParser();parser.add_argument('--boot',action='store_true');args=parser.parse_args()
assert any(p.device=='COM10' and (p.vid,p.pid)==(0x0403,0x6010) for p in list_ports.comports())
port=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=2)
port.port='COM10';port.dtr=False;port.rts=False
result={'time':datetime.now(timezone(timedelta(hours=8))).isoformat(),'port':'COM10','configuration_saved':False,'motion_commands_sent':False,'steps':[]}
try:
 port.open();port.write(b'\r');port.flush();start=read_for(port,1)
 assert re.search(rb'Zynq>\s*$',start),'Expected an idle U-Boot prompt; no command sent'
 commands=['boot'] if args.boot else ['version','printenv bootcmd boot_targets modeboot','mmc list']
 for command in commands:
  port.write((command+'\n').encode());port.flush()
  output=read_for(port,12 if args.boot else 1)
  result['steps'].append({'command':command,'output':clean(output.decode('utf8','replace'))})
  if not args.boot:assert re.search(rb'Zynq>\s*$',output),'Unexpected prompt after read-only bootloader inspection'
except Exception as exc:result['error']=str(exc)
finally:port.close()
out=Path(__file__).resolve().parent/('boot-'+('resume-' if args.boot else 'inspect-')+datetime.now().strftime('%H%M%S')+'.json')
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=True,indent=2))
raise SystemExit(1 if result.get('error') else 0)
