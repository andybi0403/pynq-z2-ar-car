"""A short real-board observation, without drive or release commands."""
import argparse
import json
import re
import shlex
import subprocess
import time
import urllib.request
from car_network_probe import ROOT,OUT,wifi,cmd,connect_board,clean
from connect_car_console import connect
from car_deploy_console import run,PYTHON

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duration',type=float,default=180)
    args=parser.parse_args()
    original=re.search(r'^\s*Profile\s*:\s*(.+)$',wifi(),re.M).group(1).strip()
    facts={'hardware':True,'motion_commands_sent':False,'observations':[],'duration_target_s':args.duration}
    client=None
    try:
        initial=connect(lambda s:print(s,flush=True),verify_only=True)
        host=initial['host']
        client=connect_board(host)
        source="from pathlib import Path;from pynq import MMIO;import json;u=MMIO(0xe0001000,4096);print(json.dumps({'uart_regs':{hex(o):hex(u.read(o)) for o in (0,4,0x18,0x2c,0x34)},'clocks':Path('/sys/kernel/debug/clk/clk_summary').read_text() if Path('/sys/kernel/debug/clk/clk_summary').exists() else 'unavailable'}))"
        facts['uart_controller']=run(client,'env XILINX_XRT=/usr '+shlex.quote(PYTHON)+' -c '+shlex.quote(source),root=True)
        facts['service_unit']=run(client,'systemctl cat pynq-car-console.service')
        url=json.loads((OUT/'active-session.json').read_text())['url']
        token=url.split('#token=')[1]
        base=url.split('#')[0]
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        started=time.monotonic()
        while time.monotonic()-started<args.duration:
            request=urllib.request.Request(base+'api/status',headers={'Authorization':'Bearer '+token})
            try:
                with opener.open(request,timeout=3) as response:s=json.load(response)
                l=s.get('latest') or {};status=l.get('status') or {};link=status.get('stm32_link') or {}
                facts['observations'].append({'elapsed_s':round(time.monotonic()-started,2),'running':s['running'],'samples':s['samples'],'frames':s['frames'],'telemetry_fresh':s['telemetry_fresh'],'motion_allowed':s['motion_allowed'],'queries':link.get('query_tx_count'),'replies':link.get('report_rx_count'),'encoder':status.get('encoder'),'car_valid':status.get('car_valid'),'video_faults':s.get('video_faults'),'control_timing':s.get('control_timing')})
                facts['final_status']=s
            except Exception as exc:
                facts['observations'].append({'elapsed_s':round(time.monotonic()-started,2),'error':clean(str(exc))})
            time.sleep(1)
        checked=subprocess.run(['node',str(ROOT/'tools/verify_live_car_console.js')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=50)
        facts['browser_check']={'code':checked.returncode,'stdout':clean(checked.stdout),'stderr':clean(checked.stderr)}
        good=[o for o in facts['observations'] if 'error' not in o]
        facts['connection_observation_passed']=len(good)>=args.duration*.7 and len(good)==len(facts['observations']) and all(o['running'] for o in good) and good[-1]['frames']>good[0]['frames'] and checked.returncode==0
        facts['sampling_fresh_all_observed']=bool(good) and all(o['telemetry_fresh'] for o in good)
        facts['sensor_joint_acceptance']=False
    except Exception as exc:facts['error']=clean(str(exc))
    finally:
        if client:client.close()
        facts['restore']=cmd(['netsh','wlan','connect','name='+original,'interface=WLAN 2'])
        time.sleep(4)
        facts['restored_wifi']=wifi()
        (OUT/'connection-observation.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),'utf8')
        print(json.dumps({k:facts.get(k) for k in ('connection_observation_passed','sensor_joint_acceptance','error','browser_check')},ensure_ascii=True))

if __name__=='__main__':main()
