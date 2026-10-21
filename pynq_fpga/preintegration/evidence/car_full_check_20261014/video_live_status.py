from pathlib import Path
import json
import re
import urllib.request

platform=Path('/home/xilinx/stm32_sensors_platform_20261013')
text=(platform/'receiver.log').read_text(errors='replace')
match=re.search(r'http://[0-9.]+:8080/#token=([A-Za-z0-9_-]+)',text)
result={'kind':'LIVE_VIDEO_DIAGNOSTIC','hardware':True}
try:
    request=urllib.request.Request('http://127.0.0.1:8080/api/status',headers={'Authorization':'Bearer '+match[1]})
    with urllib.request.urlopen(request,timeout=5) as response:
        result['status']=json.loads(response.read(800000))
except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
lines=text.splitlines()
result['log_errors']=[line for line in lines if 'Error' in line or 'Exception' in line][-12:]
print(json.dumps(result))
