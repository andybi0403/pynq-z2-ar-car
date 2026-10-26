"""Deploy/start the verified zero-output console without Internet; restore PC network."""
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import urllib.request
import zipfile
from car_network_probe import connect_board,cmd,wifi,OUT,ROOT,clean,join_car

NAME='v010_locked_resync_20261026_r12'
REMOTE='/home/xilinx/'+NAME
PYTHON='/usr/local/share/pynq-venv/bin/python3'
FACTS={'started_local':datetime.now().isoformat(),'host':'192.168.8.139','name':NAME,
       'motor_disconnected':False,'motion_allowed':False,'firmware_reflashed':False}

def save():
    (OUT/'deploy-result.json').write_text(json.dumps(FACTS,ensure_ascii=False,indent=2),'utf8')

def run(client,command,*,root=False,timeout=20):
    stdin,out,err=client.exec_command(('sudo -S -p "" -- ' if root else '')+command,timeout=timeout)
    if root:stdin.write('xilinx\n');stdin.flush()
    stdin.channel.shutdown_write();channel=out.channel;end=time.monotonic()+timeout;a=bytearray();b=bytearray()
    while True:
        while channel.recv_ready():a.extend(channel.recv(65536))
        while channel.recv_stderr_ready():b.extend(channel.recv_stderr(65536))
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():break
        if time.monotonic()>end:channel.close();raise TimeoutError('bounded remote command timed out')
        time.sleep(.02)
    result={'code':channel.recv_exit_status(),'stdout':a.decode('utf8','replace'),'stderr':b.decode('utf8','replace')}
    return result

def py(client,source,**kwargs):
    return run(client,shlex.quote(PYTHON)+' -c '+shlex.quote(source),**kwargs)

def require(result,label):
    FACTS[label]={k:clean(v) if isinstance(v,str) else v for k,v in result.items()};save()
    if result['code']!=0:raise RuntimeError(label+': '+clean(result['stderr']+result['stdout'])[-3000:])
    return result

def main():
    original=re.search(r'^\s*Profile\s*:\s*(.+)$',wifi(),re.M).group(1).strip()
    client=None
    try:
        FACTS['wifi_profile']=join_car()
        time.sleep(1);client=connect_board(FACTS['host'])
        FACTS['verified_host_key']=True
        artifact=ROOT/'pynq_fpga/release'/ (NAME+'.zip')
        data=artifact.read_bytes();digest=hashlib.sha256(data).hexdigest();FACTS['zip_sha256']=digest
        sftp=client.open_sftp()
        try:
            try:sftp.mkdir('/home/xilinx/.console-deploy')
            except OSError:pass
            target='/home/xilinx/.console-deploy/'+NAME+'.zip'
            with sftp.open(target,'wb') as stream:stream.write(data)
        finally:sftp.close()
        source=f'''from pathlib import Path
import hashlib,zipfile,json,shutil
archive=Path({target!r});assert hashlib.sha256(archive.read_bytes()).hexdigest()=={digest!r}
out=Path({REMOTE!r})
if not out.exists():
 with zipfile.ZipFile(archive) as z:
  assert all(not n.startswith('/') and '..' not in Path(n).parts and '\\\\' not in n for n in z.namelist())
  z.extractall(out)
manifest=json.loads((out/'lab_manifest.json').read_text())
for n,h in {{**manifest['runtime_files'],**manifest['wireless_files']}}.items():assert hashlib.sha256((out/n).read_bytes()).hexdigest()==h,n
base=Path('/home/xilinx/edge_console_v010_uart_role_fix_20261014_r3')
assert hashlib.sha256((base/'native/car_video.c').read_bytes()).hexdigest()==manifest['wireless_files']['native/car_video.c']
(out/'native-build').mkdir(exist_ok=True)
shutil.copy2(base/'native-build/libcar_video.so',out/'native-build/libcar_video.so')
print(json.dumps({{'files_verified':len(manifest['runtime_files'])+len(manifest['wireless_files']),'native_sha256':hashlib.sha256((out/'native-build/libcar_video.so').read_bytes()).hexdigest()}}))
'''
        require(py(client,source,timeout=25),'deployment')
        unit=f'''[Unit]
Description=PYNQ car locked connection and sensor console
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=3
[Service]
Type=simple
User=root
WorkingDirectory={REMOTE}
Environment=XILINX_XRT=/usr
Environment=SENSOR_CONSOLE_MOTOR_MODE=connected-zero-output
Environment=SENSOR_CONSOLE_DURATION=1800
ExecStart=/bin/sh {REMOTE}/start_sensor_console.sh
Restart=on-failure
RestartPreventExitStatus=1
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=8
[Install]
WantedBy=multi-user.target
'''
        setup=f'''from pathlib import Path
import subprocess
p=Path('/etc/systemd/system/pynq-car-console.service')
if p.exists() and not Path(str(p)+'.before-r9').exists():Path(str(p)+'.before-r9').write_bytes(p.read_bytes())
p.write_text({unit!r})
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','pynq-car-console.service'],check=True)
subprocess.run(['systemctl','restart','pynq-car-console.service'],check=True)
print('SERVICE_ENABLED_AND_STARTED')
'''
        require(py(client,setup,root=True),'service_install')
        token=None
        for _ in range(25):
            time.sleep(1)
            invocation=run(client,'systemctl show pynq-car-console.service -p InvocationID --value')['stdout'].strip()
            if not re.fullmatch('[0-9a-f]{32}',invocation):continue
            result=run(client,'journalctl _SYSTEMD_INVOCATION_ID='+invocation+' -n 80 --no-pager -o cat',root=True)
            tokens=re.findall(r'http://[^\s]+/#token=([\w-]+)',result['stdout'])
            if tokens:token=tokens[-1];break
        FACTS['service_status']=run(client,'systemctl is-active pynq-car-console.service; systemctl is-enabled pynq-car-console.service')
        FACTS['service_log_redacted']={k:clean(v) if isinstance(v,str) else v for k,v in result.items()};save()
        if token is None:raise RuntimeError('service did not publish a browser session; inspect redacted service log')
        url='http://'+FACTS['host']+':8080/'
        (OUT/'active-session.json').write_text(json.dumps({'url':url+'#token='+token}),'utf8')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(5):
            request=urllib.request.Request(url+'api/status',headers={'Authorization':'Bearer '+token})
            with opener.open(request,timeout=5) as response:state=json.load(response)
            if state.get('frames',0)>0:break
            time.sleep(1)
        FACTS['actual_status']=state;save()
        expected=json.loads((ROOT/'pynq_fpga/release'/NAME/'lab_manifest.json').read_text('utf8'))
        if state.get('identity',{}).get('runtime_sources')!=expected['runtime_files']:
            raise RuntimeError('running runtime identity differs from deployed package')
        result=subprocess.run(['node',str(ROOT/'tools/verify_live_car_console.js')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=50)
        FACTS['browser_verification']={'code':result.returncode,'stdout':clean(result.stdout),'stderr':clean(result.stderr)}
        if result.returncode:raise RuntimeError('live browser verification failed')
        FACTS['connected_verified']=True
    except Exception as e:FACTS['error']=clean(str(e))
    finally:
        if client:client.close()
        FACTS['restore']=cmd(['netsh','wlan','connect','name='+original,'interface=WLAN 2'])
        time.sleep(4);FACTS['restored_wifi']=wifi();save()
        print(json.dumps({k:FACTS.get(k) for k in ('connected_verified','error','deployment','service_status','browser_verification')},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
