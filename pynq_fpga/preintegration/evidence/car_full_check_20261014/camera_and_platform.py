"""Real camera capture plus verified overlay/UART preparation; no motor frames."""
from pathlib import Path
import json
import os
import subprocess
import sys

package=Path('/home/xilinx/stm32_sensors_v010_20261013_r3')
platform=Path('/home/xilinx/stm32_sensors_platform_20261013')
sys.path.insert(0,str(package))
os.chdir(package)
from wireless_benchmark import capture_benchmark
from native_video import NativeLibrary
result={'kind':'CAMERA_CAPTURE_AND_PLATFORM_CHECK','hardware':True,'motor_command_sent':False}
try:
    result['capture']=capture_benchmark(NativeLibrary(package/'native-build/libcar_video.so'),'/dev/video0',10)
    result['capture_passed']=result['capture']['unique_frames']>=2
except Exception as exc:
    result['capture_passed']=False
    result['capture_error']=repr(exc)
command=['/usr/local/share/pynq-venv/bin/python3',str(platform/'prepare_hybrid.py')]
process=subprocess.run(command,capture_output=True,text=True,timeout=35)
result['prepare_returncode']=process.returncode
result['prepare_stderr']=process.stderr[-5000:]
result['prepare_stdout']=process.stdout[-12000:]
receipt=platform/'load_receipt.json'
if process.returncode==0 and receipt.exists():result['prepare']=json.loads(receipt.read_text())
out=platform/'full_check_20261014'
out.mkdir(exist_ok=True)
(out/'camera_platform.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
