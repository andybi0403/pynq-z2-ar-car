"""Bounded independent UART query/STOP probe. No release/drive/calibration commands."""
from datetime import datetime
import json
import re
import shlex
import time

from car_network_probe import ROOT,OUT,wifi,cmd,join_car,connect_board,clean
from car_deploy_console import run,PYTHON,REMOTE


def main():
    original=re.search(r'^\s*Profile\s*:\s*(.+)$',wifi(),re.M).group(1).strip()
    facts={'time':datetime.now().isoformat(),'motion_commands_sent':False,'commands':['Q1','PSTOP']}
    client=None
    try:
        facts['profile']=join_car()
        client=connect_board('192.168.8.139')
        stopped=run(client,'systemctl stop pynq-car-console.service',root=True,timeout=20)
        if stopped['code']:raise RuntimeError(stopped['stderr'])
        source=f'''import sys,time,json,serial
sys.path.insert(0,{REMOTE!r})
from pynq_link import hybrid_frame,parse_sensor_report
from pathlib import Path
before=Path('/proc/tty/driver/xuartps').read_text()
rx=bytearray();tx=0
with serial.Serial('/dev/ttyPS1',115200,timeout=.02,write_timeout=.2,exclusive=True) as s:
 try:
  for n in range(1,81):
   packet=hybrid_frame('Q1',0x25102501,n)+b'$PSTOP#'
   tx+=s.write(packet)
   until=time.monotonic()+.05
   while time.monotonic()<until:rx.extend(s.read(256))
 finally:s.write(b'$PSTOP#');s.flush()
after=Path('/proc/tty/driver/xuartps').read_text()
print(json.dumps({{'device':'/dev/ttyPS1','baud':115200,'query_count':80,'bytes_sent':tx+7,'bytes_received':len(rx),'rx_hex':bytes(rx[:512]).hex(),'driver_before':before,'driver_after':after,'motion_commands_sent':False}}))
'''
        facts['raw_probe']=run(client,shlex.quote(PYTHON)+' -c '+shlex.quote(source),root=True,timeout=15)
    except Exception as exc:facts['error']=clean(str(exc))
    finally:
        if client:
            try:
                facts['restart']=run(client,'systemctl start pynq-car-console.service',root=True,timeout=35)
                time.sleep(9)
                facts['active']=run(client,'systemctl is-active pynq-car-console.service')
            except Exception as exc:facts['restart_error']=clean(str(exc))
            client.close()
        facts['restore']=cmd(['netsh','wlan','connect','name='+original,'interface=WLAN 2'])
        time.sleep(4)
        facts['restored_wifi']=wifi()
        (OUT/'independent-uart-probe.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),'utf8')
        print(json.dumps({k:v for k,v in facts.items() if k not in ('restored_wifi','restore')},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
