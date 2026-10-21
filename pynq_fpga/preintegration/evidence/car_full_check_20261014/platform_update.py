
from pathlib import Path
import hashlib,json,os,re,subprocess,time
platform=Path('/home/xilinx/stm32_sensors_platform_20261013')
old='/home/xilinx/stm32_sensors_v010_20261013_r3'
new='/home/xilinx/edge_console_v010_20261014_r2'
changed={}
for name in ('prepare_hybrid.py','start_hybrid.sh'):
    path=platform/name
    previous=path.read_text()
    assert old in previous, 'unexpected platform version; do not replace blindly'
    backup=platform/(name+'.before_edge_console_20261014')
    if backup.exists():assert backup.read_text()==previous
    else:backup.write_text(previous)
    content=previous.replace(old,new)
    path.write_text(content)
    changed[name]=hashlib.sha256(path.read_bytes()).hexdigest()
process=subprocess.run(['/usr/local/share/pynq-venv/bin/python3',str(platform/'prepare_hybrid.py')],
       capture_output=True,text=True,timeout=35)
assert process.returncode==0,process.stderr
ready=json.loads((platform/'load_receipt.json').read_text())
assert ready['package']==new and ready['contract']=='0xc425100a'
assert ready['qei_scale']==[0,0] and ready['risk_enable']==0
scope={}
exec(compile("\nfrom pathlib import Path\nimport datetime, fcntl, json, os, pwd, subprocess\nplatform=Path('/home/xilinx/stm32_sensors_platform_20261013')\nscript=platform/'start_hybrid.sh'\nif not script.is_file(): raise RuntimeError('missing verified platform start_hybrid.sh')\nguard=(platform/'receiver-launch.lock').open('a')\nfcntl.flock(guard,fcntl.LOCK_EX | fcntl.LOCK_NB)\nfor entry in Path('/proc').iterdir():\n    if not entry.name.isdigit(): continue\n    try: args=(entry/'cmdline').read_bytes().decode().split('\\0')\n    except (OSError,UnicodeError): continue\n    if any(Path(arg).name=='wireless_runtime.py' for arg in args):\n        raise RuntimeError('a wireless session is already running; retry connection')\nuser=pwd.getpwnam('xilinx')\nstamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S_%f')\nfolder=platform/'receiver_sessions'/stamp\nfolder.mkdir(parents=True,exist_ok=False)\nlog_path=platform/'receiver.log'\nwith log_path.open('w') as log:\n    os.chown(log_path,user.pw_uid,user.pw_gid)\n    os.chmod(log_path,0o600)\n    command=['/bin/bash',str(script),'--video-only','--duration','3600',\n             '--video-mode','auto','--fps','30','--quality','85',\n             '--evidence-dir',str(folder/'evidence')]\n    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,\n                             stderr=subprocess.STDOUT,start_new_session=True)\nreceipt={'pid':process.pid,'mode':'video_only','duration_s':3600,\n         'motor_release_sent':False,'evidence_dir':str(folder)}\n(folder/'launcher_receipt.json').write_text(json.dumps(receipt,indent=2))\nprint(json.dumps(receipt))\n",'<corrected-video-starter>','exec'),scope)
receipt=scope['receipt']
log_path=platform/'receiver.log'
deadline=time.monotonic()+30
session=None
while time.monotonic()<deadline:
    text=log_path.read_text(errors='replace')
    match=re.search(r'http://([0-9.]+):8080/#token=([A-Za-z0-9_-]+)',text)
    if match:
        session={'base':'http://'+match[1]+':8080','token':match[2]}
        break
    if scope['process'].poll() is not None:raise RuntimeError(text[-4000:])
    time.sleep(.2)
assert session is not None,'no current browser session URL'
result={'kind':'EDGE_CONSOLE_PLATFORM_READY','hardware':True,'platform_sha256':changed,
        'overlay':ready,'launch':receipt,'session':session,'motor_release_sent':False}
(platform/'edge_console_deployment_20261014.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
