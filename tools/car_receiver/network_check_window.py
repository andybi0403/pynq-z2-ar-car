"""Bounded car-LAN test with two independent Wi-Fi restoration timers."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'pynq_fpga/preintegration/evidence/car_full_check_20261014'
ROUTER='GL-SFT1200-0a0-5G'
INTERFACE='WLAN 2'

def command(args,timeout=8):
    r=subprocess.run(args,capture_output=True,text=True,errors='replace',timeout=timeout)
    return {'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}

def ssid():
    state=command(['netsh','wlan','show','interfaces'])
    found=re.search(r'^\s*SSID\s*:\s*(.+)$',state['stdout'],re.M)
    return found.group(1).strip() if found else None

def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf8')

def restore(profile,deadline,label):
    save(label+'_ready.json',{'timer_armed':True,'pid':os.getpid(),'deadline':deadline,'profile':profile})
    # This process survives the network test, browser, agent, and its parent.
    time.sleep(max(0,deadline-time.time()))
    attempts=[]
    for _ in range(6):
        if ssid()==profile:break
        attempts.append(command(['netsh','wlan','connect','name='+profile,'interface='+INTERFACE]))
        time.sleep(4)
    save(label+'_restored.json',{'profile':profile,'ssid_after':ssid(),'verified':ssid()==profile,
                                 'attempts':attempts,'restored_epoch':time.time()})

def window(config_path,label,native=False,browser_only=False):
    config=json.loads(Path(config_path).read_text('utf8'))
    prior=ssid()
    if not prior or prior==ROUTER:raise RuntimeError('expected an active campus profile before guarded window')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',label):raise ValueError('invalid phase')
    deadline=time.time()+55
    timers=[]
    for suffix,delay in (('primary',0),('backup',4)):
        timer_label=label+'_'+suffix
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'restore',
             '--profile',prior,'--deadline',str(deadline+delay),'--label',timer_label],
             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
             creationflags=subprocess.CREATE_NO_WINDOW)
        timers.append({'pid':child.pid,'label':timer_label})
    ready=time.monotonic()+5
    while time.monotonic()<ready and not all((OUT/(t['label']+'_ready.json')).exists() for t in timers):time.sleep(.05)
    if not all((OUT/(t['label']+'_ready.json')).exists() for t in timers):raise RuntimeError('restoration timers not armed')
    facts={'kind':'GUARDED_WIFI_WINDOW','prior_profile':prior,'deadline':deadline,'timers':timers,
           'PC_network_mutated':True,'started_epoch':time.time(),'stages':[]}
    save(label+'_window.json',facts)
    native_close=lambda:None
    try:
        if native:
            from native_wifi_connect import request
            facts['connection_request'],native_close=request(ROUTER)
        else:
            facts['connection_request']=command(['netsh','wlan','connect','name='+ROUTER,'interface='+INTERFACE])
        save(label+'_window.json',facts)
        wait_until=time.monotonic()+15
        while time.monotonic()<wait_until and ssid()!=ROUTER:time.sleep(.5)
        if ssid()!=ROUTER:raise RuntimeError('router Wi-Fi did not connect')
        # Test authenticated real endpoints, bypassing the desktop proxy/VPN.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(path,body=None,timeout=8):
            headers={'Authorization':'Bearer '+config['token']}
            if body is not None:headers['Content-Type']='application/json'
            request=urllib.request.Request(config['base']+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
            return opener.open(request,timeout=timeout)
        with get('/api/status') as response:
            status=json.loads(response.read(800000))
        facts['status_probe']={'running':status.get('running'),'frames':status.get('frames'),
                                'scope':status.get('session_scope'),'control_available':status.get('control_available')}
        if status.get('running') is not True:raise RuntimeError('board video session is not running')
        if browser_only:
            facts['browser_ready']=True
            save(label+'_window.json',facts)
        for view in (() if browser_only else ('raw','processed')):
            with get('/api/video?view='+view) as response:
                started=time.monotonic();buffer=b'';frames=0;sizes=[]
                while time.monotonic()-started<6:
                    buffer+=response.read1(4096)
                    while True:
                        match=re.search(rb'Content-Length: (\d+)\r\n.*?\r\n\r\n',buffer,re.S)
                        if not match:break
                        size=int(match[1]);end=match.end()+size
                        if len(buffer)<end:break
                        jpeg=buffer[match.end():end]
                        if not jpeg.startswith(b'\xff\xd8'):raise RuntimeError('not a real JPEG')
                        frames+=1;sizes.append(size);buffer=buffer[end:]
                facts['stages'].append({'view':view,'actual_JPEG_frames':frames,'seconds':time.monotonic()-started,
                     'received_fps':frames/(time.monotonic()-started),'passed':frames>=2})
                save(label+'_window.json',facts)
        if not browser_only:
            with get('/api/snapshot',{},timeout=12) as response:
                frozen=json.loads(response.read(12000000))
            facts['snapshot']={'frame_id':frozen['frame_id'],
                               'raw_bytes_base64':len(frozen['raw_jpeg_base64']),
                               'processed_bytes_base64':len(frozen['processed_jpeg_base64'])}
        save(label+'_window.json',facts)
        # Leave the rest of the bounded window for browser UI verification.
        while time.time()<deadline-3:time.sleep(.5)
    except Exception as exc:
        facts['error']=type(exc).__name__+': '+str(exc)
    finally:
        native_close()
        # Timers remain armed if this restore attempt or the parent fails.
        restore(prior,time.time(),label+'_early')
        facts['finished_epoch']=time.time()
        facts['ssid_after']=ssid()
        facts['restoration_verified']=facts['ssid_after']==prior
        save(label+'_window.json',facts)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['window','restore'])
    parser.add_argument('--profile');parser.add_argument('--deadline',type=float)
    parser.add_argument('--config');parser.add_argument('--label',required=True)
    parser.add_argument('--delay-seconds',type=float,default=0)
    parser.add_argument('--native',action='store_true')
    parser.add_argument('--browser-only',action='store_true')
    args=parser.parse_args()
    if args.mode=='restore':restore(args.profile,args.deadline,args.label)
    else:
        if not 0<=args.delay_seconds<=10:raise ValueError('invalid initial delay')
        time.sleep(args.delay_seconds)
        window(args.config,args.label,args.native,args.browser_only)
