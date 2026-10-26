"""After confirmed K1 wiring and S5 OFF, verify S1 before restarting UI.

Verified installed arrangement: PMOD B pin 9 -> K1 TX, pin 10 <- K1 RX,
common GND, K1 VCC empty, S5 OFF. Core pins remain seated in the baseboard.
Motors may stay connected for this explicitly locked/zero-output diagnosis.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'work/uart_live_fix_20261014'))
from pynq_console_transport import execute

SOURCE=r'''
from pathlib import Path
import json,secrets,subprocess,sys,time
import serial
package=Path('/home/xilinx/v010_locked_resync_20261026_r12')
sys.path.insert(0,str(package))
from pynq_link import hybrid_frame,parse_sensor_report
from overlay_session import DeviceLease
from pynq import Overlay
result={'hardware':True,'motion_commands_sent':False,'valid_reports':0,'reports':[]}
subprocess.run(['systemctl','stop','pynq-uart-wiring-observer'],timeout=10,check=False)
subprocess.run(['systemctl','stop','pynq-car-console.service'],timeout=15,check=False)
passed=False
try:
    prep=subprocess.run([sys.executable,str(package/'prepare_console.py')],capture_output=True,text=True,timeout=40,cwd=package)
    assert prep.returncode==0,prep.stderr
    with DeviceLease():
        with serial.Serial('/dev/ttyPS1',115200,timeout=.01,write_timeout=.4,exclusive=True) as port:
            session=secrets.randbits(32) or 1;raw=bytearray();received=bytearray();seen=set()
            start=time.monotonic();n=0;next_query=start
            while time.monotonic()-start<6:
                if time.monotonic()>=next_query:
                    n+=1;port.write(hybrid_frame('Q1',session,n)+b'$PSTOP#');next_query+=.05
                chunk=port.read(1024);raw.extend(chunk);received.extend(chunk)
                while b'#' in received:
                    part,_,received=received.partition(b'#')
                    frame=b'$'+part.rsplit(b'$',1)[-1]+b'#'
                    report=parse_sensor_report(frame)
                    if report and report['session']==session and 1<=report['request']<=n:
                        assert report['lock']==1 and report['left']==report['right']==0
                        seen.add(report['request']);result['reports'].append(report)
            port.write(b'$PSTOP#');port.flush()
            result.update(valid_reports=len(seen),rx_bytes=len(raw),rx_prefix_hex=raw[:2048].hex())
    passed=len(seen)>=60
    result['serial_query_reply_passed']=passed
    if passed:
        p=subprocess.run(['systemctl','enable','--now','pynq-car-console.service'],capture_output=True,text=True,timeout=40)
        result['console_start']={'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
        assert p.returncode==0,p.stderr
except BaseException as exc:
    result['error']=repr(exc);passed=False
finally:
    if not passed:
        subprocess.run(['systemctl','stop','pynq-car-console.service'],timeout=15,check=False)
        subprocess.run(['systemctl','disable','pynq-car-console.service'],timeout=10,check=False)
        with DeviceLease():Overlay('/home/xilinx/uart_snoop_20261026/uart_receive_only.bit',download=True)
        result['parked_both_uart_pins_high_impedance']=True
    Path('/home/xilinx/uart_snoop_20261026/post_rewire_verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
if not passed:raise SystemExit(2)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wiring-confirmed',action='store_true',required=True)
    args=parser.parse_args()
    result=execute(SOURCE,seconds=150,root=True,password='xilinx')
    out=ROOT/'work/connection_live_20261026'/('post-rewire-'+datetime.now().strftime('%H%M%S')+'.json')
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print('EVIDENCE',out,'RETURN_CODE',result['returncode'])
    print(result['output'])
    raise SystemExit(result['returncode'])

if __name__=='__main__':main()
