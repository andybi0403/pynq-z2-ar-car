from pathlib import Path
import sys,json,tempfile,subprocess,re
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[2]
for path in ('pynq_fpga/host','pynq_fpga/host/tests','pynq_fpga/preintegration/host','pynq_fpga/preintegration/tests'):
 sys.path.insert(0,str(ROOT/path))
from test_motion_display import data
from motion_display import MotionDisplayEstimator
from wireless_core import VideoHub,EncodedFrame
from test_joint_runtime import Client,Link
from system_runtime import JointRunner
from status_server import PAGE
results={}
s,v=data(good=False)
results['locked_feedback_250ms']=MotionDisplayEstimator().update(s,v,10_000_000,car={'left':0,'right':0,'lock':1},car_age_s=.25)
s,v=data(400)
results['turning_clean_wheels']=MotionDisplayEstimator().update(s,(v[0],replace(v[1],value_q16=100*65536)),10_000_000,car={'left':1000,'right':250,'lock':0},car_age_s=.05)
hub=VideoHub();hub.close('session ended')
results['closed_hub_accepts_frame']=hub.publish(EncodedFrame(1,1,b'\xff\xd8data',None,{}))
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp)/'joint.jsonl';path.write_text('original hardware evidence\n','utf8');link=Link()
 runner=JointRunner(Client(link),link,output_dir=tmp,identity={},hardware=False)
 runner.run(.01)
 results['existing_evidence_overwritten']=path.read_text('utf8')!='original hardware evidence\n'
script=re.search(r'<script>(.*?)</script>',PAGE,re.S).group(1).replace("el('stop').onclick=()=>action('stop');poll();","el('stop').onclick=()=>action('stop');")
stub="const elements={};const elDummy=()=>({textContent:'',children:[],append(...v){this.children.push(...v)},replaceChildren(...v){this.children=v}});const document={getElementById(id){return elements[id]??=elDummy()},createElement:elDummy};const location={hash:'#token=test'};let calls=0;const fetch=async()=>{if(calls++)throw Error('offline');return {ok:true,json:async()=>({running:true,telemetry_fresh:true,failures:[],latest:{status:{motion_display:{available:true,speed_mm_s:123,travelled_mm:20,displacement_mm:20,mode:'smoothed'}}}})}};const setTimeout=()=>{};"
js=stub+script+";(async()=>{await poll();const before=JSON.stringify(elements.cards);await poll();console.log(JSON.stringify({cards_retained_after_disconnect:JSON.stringify(elements.cards)===before,connection:elements.connection.textContent}))})()"
r=subprocess.run(['node','-e',js],capture_output=True,text=True,encoding='utf8',timeout=10);assert r.returncode==0,r.stderr
results['wired_disconnect']=json.loads(r.stdout)
out=Path(__file__).with_name('python_repro.json');out.write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(results,ensure_ascii=False))
