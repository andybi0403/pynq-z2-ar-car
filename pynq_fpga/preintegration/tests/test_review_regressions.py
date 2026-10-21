"""Review counterexamples executed against production runtime and page code."""
import concurrent.futures
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'host'))
sys.path.insert(0, str(ROOT/'preintegration/host'))
import system_runtime
import wireless_runtime
from system_runtime import EvidenceSession, JointRunner
from test_joint_runtime import Client, Link
from status_server import PAGE
from wireless_core import VideoHub, EncodedFrame


class EvidenceTests(unittest.TestCase):
    def test_existing_session_artifacts_are_preserved_before_runner_start(self):
        for name in ('joint.jsonl','joint_summary.json','video.jsonl','video_summary.json',
                     'startup_readiness.json','wireless_summary.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/name;path.write_bytes(b'original hardware evidence\n')
                link=Link();runner=JointRunner(Client(link),link,output_dir=folder,identity={})
                with self.assertRaises(FileExistsError):runner.run(.01)
                self.assertEqual(path.read_bytes(),b'original hardware evidence\n')
                self.assertEqual(link.stops,0)
                self.assertEqual(len(list(Path(folder).iterdir())),1)

    def test_cli_rejects_existing_evidence_before_overlay_or_uart(self):
        for runtime,args in ((system_runtime,['--motor-disconnected']),
                             (wireless_runtime,['--video-only','--headless'])):
            with self.subTest(runtime=runtime.__name__), tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'startup_readiness.json';path.write_bytes(b'old evidence')
                with patch.object(runtime,'verify_package'),patch.object(runtime,'open_verified_overlay') as overlay, \
                     patch.object(wireless_runtime,'verify_wireless',return_value={}):
                    if runtime is system_runtime:
                        self.assertEqual(runtime.main(args+['--evidence-dir',folder]),1)
                    else:
                        with self.assertRaises(FileExistsError):runtime.main(args+['--evidence-dir',folder])
                    overlay.assert_not_called()
                self.assertEqual(path.read_bytes(),b'old evidence')

    def test_simultaneous_reservation_has_one_winner(self):
        with tempfile.TemporaryDirectory() as folder:
            def reserve(_):
                try:return EvidenceSession(folder)
                except FileExistsError:return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                winners=[s for s in pool.map(reserve,range(8)) if s is not None]
            self.assertEqual(len(winners),1)

    def test_completed_runner_cannot_overwrite_its_own_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            link=Link();runner=JointRunner(Client(link),link,output_dir=folder,identity={})
            self.assertTrue(runner.run(.01)['passed'])
            before={p.name:p.read_bytes() for p in Path(folder).iterdir()}
            with self.assertRaisesRegex(RuntimeError,'already started'):runner.run(.01)
            self.assertEqual(before,{p.name:p.read_bytes() for p in Path(folder).iterdir()})


class HubLifecycleTests(unittest.TestCase):
    def test_stop_during_native_encode_does_not_publish_or_count_completed_frame(self):
        import io
        import threading
        import time
        from types import SimpleNamespace
        from wireless_core import IntentMailbox
        encoding=threading.Event();release=threading.Event()
        jpeg=b'\xff\xd8fixture\xff\xd9'
        class Video:
            def __init__(self):
                self.inputs=[bytearray(128) for _ in range(3)]
                self.outputs=[bytearray(128) for _ in range(3)]
                self.dma=SimpleNamespace(transfer=lambda *args:None)
                self.stopped=False
            def start(self):pass
            def stop(self):self.stopped=True
        class Camera:
            dropped=0;generation=1;reads=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):
                self.reads+=1
                if self.reads>1:
                    runner.stop_event.wait(3)
                    raise RuntimeError('fixture stopped')
                return 1,time.monotonic_ns(),jpeg,SimpleNamespace(sequence=1,width=1280,height=720,fps_num=1,fps_den=30)
        class Codec:
            restart_padding_warnings=0
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def decode_into(self,*args):pass
            def encode(self,*args,**kwargs):
                encoding.set()
                if not release.wait(3):raise RuntimeError('test encoder barrier timed out')
                return jpeg
        hub=VideoHub();video=Video()
        runner=wireless_runtime.VideoOnlyRunner(object(),None,video=video,source=Camera(),
            output_dir='unused',identity={},hardware=False,native=None,hub=hub,intent_mailbox=IntentMailbox())
        runner._journal=io.StringIO()
        runner.associator=SimpleNamespace(associate=lambda fid,stamp:{'valid':True,'frame_id':fid,'epoch':1,'registers':{}})
        runner.association_metrics=SimpleNamespace(observe=lambda *args:None)
        worker=threading.Thread(target=runner._video_loop,daemon=True)
        with patch.object(wireless_runtime,'Codec',Codec),patch.object(wireless_runtime,'encode',return_value=[]), \
             patch.object(wireless_runtime,'prefix_bgr0',return_value=b'\0'*72):
            try:
                worker.start();self.assertTrue(encoding.wait(3))
                runner.stop_event.set();release.set();worker.join(4)
                self.assertFalse(worker.is_alive());self.assertTrue(video.stopped)
                self.assertEqual(runner.failures,[])
                self.assertEqual(runner.frames,0);self.assertIsNone(hub.latest)
                self.assertNotIn('wireless_frame',runner._journal.getvalue())
            finally:
                runner.stop_event.set();release.set();worker.join(4)

    def test_closed_hub_rejects_late_codec_completion_without_erasing_error(self):
        hub=VideoHub()
        self.assertTrue(hub.publish(EncodedFrame(1,1,b'\xff\xd8a',b'\xff\xd8b',{'epoch':1})))
        hub.close('capture stopped')
        self.assertFalse(hub.publish(EncodedFrame(2,2,b'\xff\xd8c',b'\xff\xd8d',{'epoch':2})))
        hub.set_error('late callback');hub.close()
        self.assertEqual(hub.error,'capture stopped')
        self.assertEqual(hub.latest.frame_id,1)
        self.assertEqual(hub.pair.frame_id,1)
        self.assertIsNone(hub.next('raw',0,.001))


@unittest.skipUnless(shutil.which('node'),'Node is unavailable')
class PageFailureTests(unittest.TestCase):
    def test_disconnect_and_stalled_response_body_clear_wired_numbers(self):
        script=re.search(r'<script>(.*?)</script>',PAGE,re.S).group(1)
        script=script.replace("el('stop').onclick=()=>action('stop');poll();","el('stop').onclick=()=>action('stop');")
        self.check_page(script, 'JSON.stringify(elements.cards)', '123.00')

    def test_disconnect_and_stalled_response_body_clear_wireless_numbers(self):
        page=(ROOT/'preintegration/host/wireless_page.html').read_text('utf8')
        lines=[line for line in page.splitlines() if line.startswith((
            'const displayModes=','function renderMotion(','function renderHealth(','async function api(',
            'async function readStatus(','async function poll('))]
        script="const el=id=>document.getElementById(id);const frozen=true;const player={rates:()=>({received_fps:0,drawn_fps:0})};\n"+'\n'.join(lines)
        self.check_page(script, 'elements.motionNumbers.textContent', '123.00')

    def check_page(self, script, rendered, number):
        stub=r'''
const assert=require('node:assert/strict');
const elements={};const element=()=>({textContent:'',children:[],append(...v){this.children.push(...v)},replaceChildren(...v){this.children=v}});
const document={getElementById(id){return elements[id]??=element()},createElement:element};
const location={hash:'#token=test'};let mode='ok';let timers=new Map(),nextTimer=0;
const setTimeout=(fn,ms)=>{timers.set(++nextTimer,{fn,ms});return nextTimer};
const clearTimeout=id=>timers.delete(id);
const payload={running:true,telemetry_fresh:true,failures:[],latest:{status:{motion_display:{available:true,speed_mm_s:123,travelled_mm:20,displacement_mm:20,mode:'smoothed'}}}};
const waitAbort=signal=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('timeout')),{once:true}));
const fetch=async(path,options)=>{
 if(mode==='offline')throw Error('offline');
 if(mode==='hang_headers')return waitAbort(options.signal);
 return {ok:true,json:()=>mode==='hang_body'?waitAbort(options.signal):Promise.resolve(payload)};
};
'''
        assertions=r'''
(async()=>{
 for(const failure of ['offline','hang_headers','hang_body']){
  mode='ok';await poll();assert.ok(RENDERED.includes(NUMBER));
  mode=failure;const pending=poll();
  // Let fetch headers settle; the body can independently stop responding.
  for(let i=0;i<8;i++)await Promise.resolve();
  if(failure.startsWith('hang')){
   const deadlines=[...timers.values()].filter(t=>t.ms===2000);
   assert.equal(deadlines.length,1);deadlines[0].fn();
  }
  await pending;assert.ok(!RENDERED.includes(NUMBER),failure+' retained old speed');
  assert.equal([...timers.values()].filter(t=>t.ms===2000).length,0);
 }
 console.log('PAGE_FAILURE_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('RENDERED',rendered).replace('NUMBER',json.dumps(number))
        result=subprocess.run(['node','-e',stub+script+assertions],capture_output=True,
                              text=True,encoding='utf8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PAGE_FAILURE_PASS',result.stdout)


if __name__=='__main__':unittest.main()
