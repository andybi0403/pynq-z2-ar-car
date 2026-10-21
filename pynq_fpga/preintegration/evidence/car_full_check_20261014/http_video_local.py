"""Actual authenticated HTTP views and snapshot on loopback; not a Wi-Fi pass."""
from pathlib import Path
import base64
import json
import re
import time
import urllib.request

text=Path('/home/xilinx/stm32_sensors_platform_20261013/receiver.log').read_text()
token=re.search(r'http://[0-9.]+:8080/#token=([A-Za-z0-9_-]+)',text)[1]
result={'kind':'LOCAL_HTTP_VIDEO_VIEWS','hardware':True,'scope':'board HTTP endpoints, excludes PC wireless and display','views':[]}
def get(path,body=None):
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080'+path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}),timeout=8)
for view in ('raw','processed'):
    entry={'view':view,'frames':0,'read_bytes':0}
    try:
        with get('/api/video?view='+view) as stream:
            began=time.monotonic();buf=b''
            while time.monotonic()-began<6:
                data=stream.read1(4096);entry['read_bytes']+=len(data);buf+=data
                if not data:raise EOFError('stream ended')
                while True:
                    match=re.search(rb'Content-Length: (\d+)\r\n.*?\r\n\r\n',buf,re.S)
                    if match is None:break
                    length=int(match[1]);end=match.end()+length
                    if len(buf)<end:break
                    jpeg=buf[match.end():end]
                    assert jpeg[:2]==b'\xff\xd8' and jpeg[-2:]==b'\xff\xd9'
                    entry['frames']+=1;buf=buf[end:]
            entry['seconds']=time.monotonic()-began
    except Exception as exc:entry['error']=type(exc).__name__+': '+str(exc)
    entry['passed']=entry['frames']>=2 and 'error' not in entry
    result['views'].append(entry)
try:
    with get('/api/snapshot',{}) as response:frozen=json.loads(response.read(5000000))
    raw=base64.b64decode(frozen['raw_jpeg_base64']);processed=base64.b64decode(frozen['processed_jpeg_base64'])
    result['snapshot']={'frame_id':frozen['frame_id'],'raw_bytes':len(raw),'processed_bytes':len(processed),
                        'both_JPEG':raw[:2]==processed[:2]==b'\xff\xd8'}
except Exception as exc:result['snapshot_error']=type(exc).__name__+': '+str(exc)
with get('/api/status') as response:status=json.loads(response.read(800000))
result['final_video']=status.get('video')
result['passed']=all(v['passed'] for v in result['views']) and result.get('snapshot',{}).get('both_JPEG',False)
print(json.dumps(result))
