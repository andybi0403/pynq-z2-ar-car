"""Read-only local UI preview of an actual stationary capture, not live hardware."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pynq_fpga/host'))
sys.path.insert(0,str(ROOT/'pynq_fpga/preintegration/host'))
import status_server
OUT=ROOT/'pynq_fpga/preintegration/evidence/qei_display_20261013'
rows=[json.loads(l) for l in (OUT/'round2_display_replay.jsonl').read_text('utf8').splitlines()]
status_server.PAGE=status_server.PAGE.replace('<h1>小车联合运行</h1>','<h1>运动显示回放预览</h1><p>真实静止采集日志回放 · 非实时上板 · 显示值标记为估计</p>')
class Preview:
    output_dir=OUT
    def status_snapshot(self):
        row=rows[min(int(time.monotonic()*20)%len(rows),len(rows)-1)]
        return {'running':True,'hardware':False,'telemetry_fresh':True,'failures':[],
                'samples':8948,'frames':0,'identity':{},'action':None,
                'latest':{'status':{'distance_valid':False,'speed_valid':row['measured_speed_valid'],
                 'speed_mm_s':None,'raw_speed_mm_s':(row['raw_left_mm_s']+row['raw_right_mm_s'])/2,
                 'odometry_valid':False,'car_valid':False,'pl_stop':True,'risk_reasons':1,
                 'motion_display':row['motion_display'],'display':{}}}}
    def enqueue_action(self,*args):raise RuntimeError('只读回放预览，不执行硬件操作')
with status_server.StatusServer(Preview(),port=0) as server:
    url=f'http://127.0.0.1:{server.port}/#token={server.token}'
    (OUT/'preview_url.json').write_text(json.dumps({'url':url,'scope':'offline readonly UI preview'}),'utf8')
    print(url,flush=True)
    time.sleep(1800)
