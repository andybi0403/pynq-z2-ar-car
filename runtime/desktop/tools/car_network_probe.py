"""Bounded offline LAN diagnosis; always restore the original Wi-Fi profile."""
import concurrent.futures
from datetime import datetime
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.request
from car_connection_control import check_cancel, pause, hidden_process_options

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/connection_live_20261025'
OUT.mkdir(exist_ok=True)
STAMP=datetime.now().strftime('%H%M%S')
FACTS={'started_local':datetime.now().isoformat(),'hardware_writes':False}

def clean(value):
    return re.sub(r'(?i)(#token=|Bearer )[A-Za-z0-9_\-]+',r'\1<redacted>',value)

def cmd(args,timeout=8):
    p=subprocess.run(args,capture_output=True,timeout=timeout,**hidden_process_options())
    def decode(data):
        try:return data.decode('utf8')
        except UnicodeDecodeError:return data.decode('mbcs' if os.name=='nt' else 'utf8','replace')
    return {'code':p.returncode,'stdout':clean(decode(p.stdout)),
            'stderr':clean(decode(p.stderr))}

def save():
    (OUT/('probe_'+STAMP+'.json')).write_text(json.dumps(FACTS,ensure_ascii=False,indent=2),'utf8')

def normalize_wifi_output(text):
    """netsh changes language between a terminal and a pythonw desktop launch."""
    keys={'名称':'Name','状态':'State','配置文件':'Profile'}
    states={'已连接':'connected','已断开连接':'disconnected','已断开':'disconnected',
            '正在连接':'connecting','正在断开连接':'disconnecting'}
    lines=[]
    for line in text.splitlines():
        match=re.match(r'^(\s*)(名称|状态|配置文件|Name|State|Profile)\s*[:：]\s*(.*?)\s*$',line)
        if match:
            indent,key,value=match.groups();key=keys.get(key,key)
            if key=='State':value=states.get(value,value).lower()
            line=indent+key+' : '+value
        lines.append(line)
    return '\n'.join(lines)


def wifi():
    return normalize_wifi_output(cmd(['netsh','wlan','show','interfaces'])['stdout'])

def join_car(timeout=22, *, cancel_event=None, progress=None):
    """Retry association: Windows can initially return to its Internet profile."""
    check_cancel(cancel_event)
    if 'GL-SFT1200-0a0' not in wifi():
        if progress:progress('正在刷新无线网络列表…')
        cmd(['netsh','wlan','disconnect','interface=WLAN 2'])
        import ctypes,uuid
        handle=ctypes.c_void_p()
        version=ctypes.c_ulong()
        wlan=ctypes.WinDLL('wlanapi')
        wlan.WlanOpenHandle.argtypes=[ctypes.c_ulong,ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_void_p)]
        wlan.WlanScan.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
        wlan.WlanCloseHandle.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        if wlan.WlanOpenHandle(2,None,ctypes.byref(version),ctypes.byref(handle))==0:
            try:
                guid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID('d9371623-0cd9-40f1-990a-ee99d29a8960').bytes_le)
                wlan.WlanScan(handle,ctypes.byref(guid),None,None,None)
            finally:wlan.WlanCloseHandle(handle,None)
        pause(4,cancel_event)
    attempts=[]
    for profile in ('GL-SFT1200-0a0-5G','GL-SFT1200-0a0'):
        check_cancel(cancel_event)
        if progress:progress('正在关联 '+profile+'，等待电脑获取小车网段地址…')
        deadline=time.monotonic()+timeout
        requested=0
        while time.monotonic()<deadline:
            check_cancel(cancel_event)
            state=wifi()
            current=re.search(r'^\s*SSID\s*:\s*(GL-SFT1200-0a0(?:-5G)?)\s*$',state,re.M)
            if current and re.search(r'^\s*State\s*:\s*connected\s*$',state,re.M):
                for _ in range(18):
                    check_cancel(cancel_event)
                    addresses=cmd(['netsh','interface','ipv4','show','addresses','name=WLAN 2'])['stdout']
                    if re.search(r'192\.168\.8\.(?:[2-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-4])\b',addresses):
                        return current.group(1)
                    pause(1,cancel_event)
                break
            if time.monotonic()-requested>5:
                attempt=cmd(['netsh','wlan','connect','name='+profile,'interface=WLAN 2'])
                attempts.append(attempt)
                if attempt['code']!=0:break
                requested=time.monotonic()
            pause(1,cancel_event)
    raise RuntimeError('未能连上小车 Wi-Fi。请确认 GL-SFT1200-0a0-5G 已开启且在附近。')

def probe(host,port):
    try:
        with socket.create_connection((host,port),timeout=.6):return True
    except OSError:return False

def ssh_banner(host):
    """A VPN may accept TCP for unreachable IPs; require a real SSH greeting."""
    try:
        with socket.create_connection((host,22),timeout=.8) as sock:
            sock.settimeout(.8)
            return sock.recv(256).startswith(b'SSH-2.0-')
    except OSError:return False

def connect_board(host):
    import paramiko
    client=paramiko.SSHClient()
    known=ROOT/'tools/car_board_known_hosts'
    client.load_host_keys(str(known))
    for kind,key in client.get_host_keys()['192.168.2.99'].items():client.get_host_keys().add(host,kind,key)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(host,username='xilinx',password='xilinx',look_for_keys=False,allow_agent=False,
                       timeout=4,banner_timeout=4,auth_timeout=4)
        return client
    except BaseException:
        client.close()
        raise

def remote(host):
    client=connect_board(host)
    try:
        source="hostname; uptime; ip -br -4 address; ss -ltn; ps -eo pid,args | grep -E 'wireless_runtime|status_server|jupyter' | grep -v grep; find /home/xilinx -maxdepth 2 -name '*console*' -type d; ls -l /dev/video* /dev/ttyPS*"
        _,out,err=client.exec_command(source,timeout=8)
        return {'verified_host_key':True,'code':out.channel.recv_exit_status(),
                'stdout':clean(out.read().decode('utf8','replace')),'stderr':clean(err.read().decode('utf8','replace'))}
    finally:client.close()

def main():
    before=wifi();FACTS['before']=before
    match=re.search(r'^\s*Profile\s*:\s*(.+)$',before,re.M)
    original=match.group(1).strip() if match else 'SEU-WLAN'
    try:
        FACTS['attempts']=[]
        for profile in ('GL-SFT1200-0a0-5G','GL-SFT1200-0a0'):
            attempt={'profile':profile,'request':cmd(['netsh','wlan','connect','name='+profile,'interface=WLAN 2'])}
            FACTS['attempts'].append(attempt);save()
            for _ in range(7):
                time.sleep(1.5);state=wifi()
                if re.search(r'^\s*SSID\s*:\s*'+re.escape(profile)+r'\s*$',state,re.M):
                    attempt['connected']=True;break
            attempt['state']=state;save()
            if attempt.get('connected'):break
        else:raise RuntimeError('saved car profiles did not associate with the AP')
        time.sleep(2)
        FACTS['ipconfig']=cmd(['ipconfig'])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open('http://192.168.8.1/',timeout=2) as r:
                FACTS['router_http']={'status':r.status,'bytes':len(r.read(20000))}
        except Exception as e:FACTS['router_http']={'error':str(e)}
        hosts=['192.168.8.10','192.168.8.139']
        FACTS['ports']={h:{str(p):probe(h,p) for p in (22,80,8080,9090)} for h in hosts}
        found=[h for h in hosts if FACTS['ports'][h]['22']]
        if not found:
            with concurrent.futures.ThreadPoolExecutor(max_workers=40) as pool:
                addresses=['192.168.8.'+str(i) for i in range(2,255)]
                found=[h for h,opened in zip(addresses,pool.map(lambda h:probe(h,22),addresses)) if opened]
        FACTS['ssh_hosts']=found;save()
        FACTS['boards']={}
        for host in found[:3]:
            try:FACTS['boards'][host]=remote(host)
            except Exception as e:FACTS['boards'][host]={'error':str(e)}
        FACTS['arp']=cmd(['arp','-a'])
    except Exception as e:FACTS['error']=str(e)
    finally:
        FACTS['restore_request']=cmd(['netsh','wlan','connect','name='+original,'interface=WLAN 2'])
        time.sleep(4);FACTS['restored']=wifi();save()
        print(json.dumps({'file':str(OUT/('probe_'+STAMP+'.json')),
                          'error':FACTS.get('error'),'ssh_hosts':FACTS.get('ssh_hosts'),
                          'ports':FACTS.get('ports'),'boards':FACTS.get('boards')},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
