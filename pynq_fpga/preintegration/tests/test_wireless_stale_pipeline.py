"""Production video lifecycle regression; camera/DMA/MMIO fixtures are software only."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'host'));sys.path.insert(0,str(ROOT/'preintegration/host'))
class StalePipelineTests(unittest.TestCase):
    def test_fault_during_old_encoding_requires_fresh_capture(self):
        import io,threading,time
        from types import SimpleNamespace
        from unittest.mock import patch
        import wireless_runtime as runtime
        from wireless_core import VideoHub,IntentMailbox
        jpeg=b'\xff\xd8software-fixture\xff\xd9'
        encoding=threading.Event();finish_old=threading.Event();fault_seen=threading.Event()
        resume_camera=threading.Event();old_attempted=threading.Event();fresh_published=threading.Event()
        class Hub(VideoHub):
         def set_error(self,error):
          super().set_error(error);fault_seen.set()
         def publish(self,frame):
          result=super().publish(frame)
          if frame.frame_id==1:old_attempted.set()
          if frame.frame_id==2:fresh_published.set()
          return result
        class Video:
         def __init__(self):
          self.inputs=[bytearray(128) for _ in range(3)];self.outputs=[bytearray(128) for _ in range(3)]
          self.dma=SimpleNamespace(transfer=lambda *args:None);self.stopped=False
         def start(self):pass
         def stop(self):self.stopped=True
        class Camera:
         dropped=0;generation=0;reads=0
         def __enter__(self):self.generation+=1;return self
         def __exit__(self,*args):pass
         def read(self):
          self.reads+=1
          if self.reads==2:
           assert encoding.wait(3),'old frame never entered encoding'
           raise RuntimeError('injected camera disconnected during old encode')
          if self.reads==3:
           assert resume_camera.wait(3),'fresh-camera release missing'
          elif self.reads>3:
           runner.stop_event.wait(3);raise RuntimeError('fixture stopped')
          fid=1 if self.reads==1 else 2
          return fid,time.monotonic_ns(),jpeg,SimpleNamespace(sequence=fid,width=1280,height=720,fps_num=1,fps_den=30)
        class Codec:
         restart_padding_warnings=0
         def __init__(self,*args,**kwargs):pass
         def __enter__(self):return self
         def __exit__(self,*args):pass
         def decode_into(self,*args):pass
         def encode(self,*args,**kwargs):
          if not encoding.is_set():
           encoding.set();assert finish_old.wait(3),'old encoder release missing'
          return jpeg
        hub=Hub();hub.policy.configure({'mode':'manual','fps':30,'quality':85})
        video=Video();camera=Camera()
        runner=runtime.VideoOnlyRunner(object(),None,video=video,source=camera,output_dir='unused',
         identity={'scope':'software-only cross-thread fault fixture'},hardware=False,
         native=None,hub=hub,intent_mailbox=IntentMailbox())
        runner._journal=io.StringIO()
        runner.associator=SimpleNamespace(associate=lambda fid,stamp:{'valid':True,'frame_id':fid,'epoch':1,'registers':{}})
        runner.association_metrics=SimpleNamespace(observe=lambda *args:None)
        worker=threading.Thread(target=runner._video_loop,daemon=True)
        try:
         with patch.object(runtime,'Codec',Codec),patch.object(runtime,'encode',return_value=[]),patch.object(runtime,'prefix_bgr0',return_value=b'\0'*72):
          worker.start();assert fault_seen.wait(3),'camera fault not observed'
          finish_old.set();assert old_attempted.wait(3),'old encode never attempted publication'
          assert hub.error is not None,'old encoder completion must not clear the camera fault'
          assert hub.next('processed',0,.001) is None,'old encoded image must not be deliverable'
          resume_camera.set();assert fresh_published.wait(3),'new camera generation never published'
          assert hub.error is None
          assert hub.next('processed',0,.001).frame_id==2
          deadline=time.monotonic()+1
          while runner.frames<1 and time.monotonic()<deadline:runner.stop_event.wait(.005)
          assert runner.frames==1,'stale encoded completion must not count as delivered'
          runner.stop_event.set();worker.join(4)
          assert not worker.is_alive();assert video.stopped;assert runner.pipeline_safe
          assert not runner.failures,runner.failures
         print('PIPELINE_FAULT_PASS old encoder/capture race rejected; new capture restores service; cleanup confirmed')
        finally:
         runner.stop_event.set();finish_old.set();resume_camera.set();worker.join(4)
