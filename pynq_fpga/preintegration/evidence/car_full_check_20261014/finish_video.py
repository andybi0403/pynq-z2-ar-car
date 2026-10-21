from pathlib import Path
import base64,hashlib,json,os,signal,time
platform=Path('/home/xilinx/stm32_sensors_platform_20261013')
receipt=json.loads((platform/'edge_console_deployment_20261014.json').read_text())
pid=receipt['launch']['pid'];proc=Path('/proc')/str(pid)
result={'kind':'OWN_VIDEO_SESSION_CLEANUP','pid':pid,'signal_sent':False}
if proc.exists():
    args=(proc/'cmdline').read_bytes().decode().split('\0')
    assert any(a=='/home/xilinx/edge_console_v010_20261014_r2/wireless_runtime.py' for a in args),args
    os.kill(pid,signal.SIGINT);result['signal_sent']=True
    end=time.monotonic()+12
    while time.monotonic()<end and proc.exists():time.sleep(.2)
result['process_closed']=not proc.exists()
assert result['process_closed'],'own video runtime did not exit cleanly'
folder=Path(receipt['launch']['evidence_dir'])/'evidence'
result['evidence_dir']=str(folder);result['files']=[]
for path in sorted(folder.iterdir()):
    if not path.is_file():continue
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
    result['files'].append({'name':path.name,'bytes':path.stat().st_size,'sha256':digest.hexdigest()})
    if path.name=='video_summary.json':result['video_summary']=json.loads(path.read_text())
result['log_tail']=(platform/'receiver.log').read_text(errors='replace')[-4000:]
print(json.dumps(result))
