"""Wired status/config/log page backed by the existing MMIO-owning session."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import secrets
import threading
from urllib.parse import urlsplit

PAGE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>小车联合运行</title><style>
body{font-family:system-ui,sans-serif;background:#f4f6f8;color:#172332;max-width:980px;margin:32px auto;padding:0 20px}
h1{font-size:26px}section{background:white;border-radius:14px;padding:20px;margin:16px 0;border:1px solid #dce2e8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:18px}
.value{font-size:25px;font-weight:600}.label{font-size:14px;color:#596b7b}button{padding:10px 16px;border:0;border-radius:8px;background:#174d78;color:white;cursor:pointer;margin:6px 8px 6px 0}
button.stop{background:#ad2637}textarea{box-sizing:border-box;width:100%;height:150px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.muted{color:#596b7b}
</style><h1>小车联合运行</h1><p class="muted">无电机台架模式 · 页面与HDMI共用当前运行会话</p>
<section><p id="connection">正在连接…</p><div class="grid" id="cards"></div><p id="risks"></p><p id="faults"></p></section>
<section><h2>标定配置</h2><p>电机保持断开。选择已保存的左右轮标定文件，应用后会清零里程并读回核验。页面不会自动使用名义轮径。</p>
<input id="file" type="file" accept=".json"><textarea id="config" placeholder="选择标定JSON文件后在此预览"></textarea>
<button id="apply">应用标定</button><button id="save">保存当前配置</button><p id="action"></p></section>
<section><h2>运行记录</h2><p id="counts"></p><p id="displaystate"></p><button id="log">下载完整运行日志</button><button id="summary">下载验收摘要</button><button class="stop" id="stop">停止本次运行</button>
<p class="muted">摄像头时间统计指解码帧接收与提交；HDMI帧计数不代表摄像头曝光或屏幕实测延迟。</p><pre id="errors"></pre></section>
<script>
const token=new URLSearchParams(location.hash.slice(1)).get('token')||'';
let snapshot=null; const el=id=>document.getElementById(id);
const names=['禁用','命令无效','命令过期','超声无效','超声过期','红外无效','保留','红外障碍','左轮无效','右轮无效','左轮过期','右轮过期','距离不足','轮速方向异常'];
async function request(path,method='GET',body){let r=await fetch(path,{method,headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!r.ok)throw Error((await r.text())||r.status);return r;}
function number(value,valid,unit){return valid&&Number.isFinite(value)?value.toFixed(2)+' '+unit:'未取得有效数据';}
const displayModes={smoothed:'平滑显示',hold:'短时保持',stationary_assumption:'静止展示',locked_zero_estimate:'锁车零速',measured_model_estimate:'模型显示',unavailable:'显示不可用',telemetry_expired:'更新中断'};
function motionCards(s){const d=s.motion_display;if(!d)return [['轮速',number(s.speed_mm_s,s.speed_valid,'mm/s')],['累计路程',number(s.travelled_mm,s.odometry_valid,'mm')],['有符号位移',number(s.displacement_mm,s.odometry_valid,'mm')]];return [['轮速',number(d.speed_mm_s,d.available,'mm/s')],['累计路程',number(d.travelled_mm,d.available,'mm')],['位移',number(d.displacement_mm,d.available,'mm')],['显示状态',displayModes[d.mode]||'显示不可用']];}
function card(label,value){const d=document.createElement('div');const l=document.createElement('div');l.className='label';l.textContent=label;const v=document.createElement('div');v.className='value';v.textContent=value;d.append(l,v);return d;}
async function poll(){try{snapshot=await (await request('/api/status')).json();const s=snapshot.latest?.status||{};el('connection').textContent=snapshot.running?snapshot.telemetry_fresh?'会话运行中':'控制状态更新中断':snapshot.failures.length?'会话已停止':'等待会话启动';
const cards=[['障碍距离',number(s.distance_mm,s.distance_valid,'mm')],...motionCards(s),['PL停车请求',s.pl_stop==null?'无有效记录':s.pl_stop?'停车':'允许'],['STM32实际锁存',!s.car_valid?'回传缺失或过期':s.car.lock?'已锁存':'已解除']];el('cards').replaceChildren(...cards.map(([a,b])=>card(a,b)));
el('risks').textContent='风险原因：'+(names.filter((name,i)=>(s.risk_reasons||0)&(1<<i)).join('、')||'无');
el('faults').textContent='STM32故障：'+(s.car_valid?'0x'+s.car.fault.toString(16).padStart(4,'0'):'无有效回传');
el('counts').textContent=`控制采样 ${snapshot.samples} 次 · 摄像头提交 ${snapshot.frames} 帧 · HDMI ${s.display?.DISPLAY_FRAMES??'—'} 帧 · 显示格式异常 ${s.display?.OSD_ERRORS??'—'} 次`;
const d=s.display||{},fresh=snapshot.telemetry_fresh&&(d.DISPLAY_FRAME_STATE&3)===3;
const sof=(BigInt(d.DISPLAY_FRAME_SOF_HI||0)<<32n)+BigInt(d.DISPLAY_FRAME_SOF_LO||0),rx=(BigInt(d.DISPLAY_FRAME_TS_HI||0)<<32n)+BigInt(d.DISPLAY_FRAME_TS_LO||0);
el('displaystate').textContent=fresh?`画面编号 ${d.DISPLAY_FRAME_ID} · 对应快照 ${d.DISPLAY_FRAME_STATE>>>16} · 最近一帧进入叠加时的年龄 ${(Number(sof-rx)/100000).toFixed(2)} ms · 重复画面 ${d.DISPLAY_REPEATS} 次 · 标记异常 ${d.DISPLAY_HEADER_ERRORS} 次`:'画面对应状态尚未确认或已过期';
el('errors').textContent=snapshot.failures.join('\n');if(snapshot.action)el('action').textContent=snapshot.action.applied?'标定已应用并核验':snapshot.action.error||'已排队';
}catch(e){el('connection').textContent='连接失败：'+e.message;}setTimeout(poll,1000);}
async function action(kind,payload){try{await request('/api/'+kind,'POST',payload||{});el('action').textContent='请求已排队，等待运行线程处理';}catch(e){el('action').textContent=e.message;}}
el('file').onchange=async()=>{if(el('file').files[0])el('config').value=await el('file').files[0].text();};
el('apply').onclick=()=>{try{action('calibration',JSON.parse(el('config').value));}catch(e){el('action').textContent='文件格式错误：'+e.message;}};
function save(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
el('save').onclick=()=>{const c=snapshot?.identity?.calibration;if(!c?.schema){el('action').textContent='当前未加载可保存的标定文件';return;}save(new Blob([JSON.stringify(c,null,2)],{type:'application/json'}),'calibration.json');};
async function download(name){try{save(await (await request('/api/log/'+name)).blob(),name);}catch(e){el('action').textContent=e.message;}}
el('log').onclick=()=>download('joint.jsonl');el('summary').onclick=()=>download('joint_summary.json');el('stop').onclick=()=>action('stop');poll();
</script></html>'''


class StatusServer:
    def __init__(self, runner, host='127.0.0.1', port=0):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError('web port must be 0..65535')
        self.runner=runner
        self.token=secrets.token_urlsafe(32)
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, status, payload, content_type='application/json'):
                data=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode('utf-8')
                self.send_response(status);self.send_header('Content-Type',content_type)
                self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
            def authorized(self):
                value=self.headers.get('Authorization','')
                return secrets.compare_digest(value,'Bearer '+owner.token)
            def do_GET(self):
                path=urlsplit(self.path).path
                if path=='/':
                    self.reply(200,PAGE.encode('utf-8'),'text/html; charset=utf-8');return
                if not self.authorized():self.reply(401,{'error':'需要页面链接中的会话令牌'});return
                if path=='/api/status':self.reply(200,owner.runner.status_snapshot());return
                if path in ('/api/log/joint.jsonl','/api/log/joint_summary.json'):
                    file=Path(owner.runner.output_dir)/path.rsplit('/',1)[1]
                    try:
                        with file.open('rb') as stream:
                            size=file.stat().st_size
                            self.send_response(200);self.send_header('Content-Type','application/octet-stream')
                            self.send_header('Content-Length',str(size));self.end_headers()
                            remaining=size
                            while remaining:
                                chunk=stream.read(min(65536,remaining))
                                if not chunk:break
                                self.wfile.write(chunk);remaining-=len(chunk)
                    except FileNotFoundError:self.reply(404,{'error':'记录尚未生成'})
                    return
                self.reply(404,{'error':'没有此入口'})
            def do_POST(self):
                if not self.authorized():self.reply(401,{'error':'会话令牌不匹配'});return
                path=urlsplit(self.path).path
                if path not in ('/api/stop','/api/calibration'):
                    self.reply(404,{'error':'没有此操作'});return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0 < size <= 16384:raise ValueError('配置文件大小不合法')
                    payload=json.loads(self.rfile.read(size))
                    if not isinstance(payload,dict):raise ValueError('配置必须为JSON对象')
                    result=owner.runner.enqueue_action(path.rsplit('/',1)[1],payload)
                    self.reply(202,result)
                except (ValueError,TypeError,RuntimeError,queue.Full) as exc:
                    self.reply(400,{'error':str(exc)})
            def setup(self):
                super().setup();self.connection.settimeout(3)
        self.http=ThreadingHTTPServer((host,port),Handler)
        self.http.daemon_threads=True
        self.port=self.http.server_port
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):
        self.http.shutdown();self.http.server_close();self.thread.join(2)
