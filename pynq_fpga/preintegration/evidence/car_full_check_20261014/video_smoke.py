"""Thirty-second actual C270 -> PL -> JPEG run; no actuator UART opened."""
from pathlib import Path
import json
import os
import subprocess

package=Path('/home/xilinx/stm32_sensors_v010_20261013_r3')
folder=Path('/home/xilinx/stm32_sensors_platform_20261013/full_check_20261014/video_smoke_r2')
folder.mkdir(parents=True,exist_ok=False)
environment={**os.environ,'XILINX_XRT':'/usr','PYTHONDONTWRITEBYTECODE':'1'}
command=['/usr/local/share/pynq-venv/bin/python3',str(package/'wireless_runtime.py'),
         '--video-only','--headless','--duration','30','--evidence-dir',str(folder/'evidence')]
with (folder/'startup.log').open('w') as log:
    process=subprocess.run(command,cwd=package,env=environment,stdout=log,
                           stderr=subprocess.STDOUT,timeout=55)
result={'kind':'ACTUAL_VIDEO_SMOKE','hardware':True,'returncode':process.returncode,
        'mode':'video_only','uart_opened':False,'requested_s':30}
for name in ('video_summary.json','wireless_summary.json','startup_readiness.json'):
    path=folder/'evidence'/name
    if path.exists():result[name]=json.loads(path.read_text())
result['log_tail']=(folder/'startup.log').read_text(errors='replace')[-5000:]
print(json.dumps(result))
