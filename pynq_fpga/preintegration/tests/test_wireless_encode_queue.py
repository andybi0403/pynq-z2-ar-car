"""Production video lifecycle regression; camera/DMA/MMIO fixtures are software only."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'host'));sys.path.insert(0,str(ROOT/'preintegration/host'))
class EncoderQueueTests(unittest.TestCase):
    def test_busy_encoder_defers_decode_and_exact_DMA_buffer_return(self):
        import io,threading,time
        from types import SimpleNamespace
        from unittest.mock import patch
        import wireless_runtime as runtime
        from wireless_core import VideoHub,IntentMailbox
        encoding=threading.Event();release_old=threading.Event();queued3=threading.Event();finished3=threading.Event()
        decoded2=threading.Event();encoded=[];decoded=[];queues=[];jpeg=b'\xff\xd8fixture\xff\xd9'
        OriginalQueue=runtime.queue.Queue
        class Queue(OriginalQueue):
         def __init__(self,*args,**kwargs):self.free_indices=set();super().__init__(*args,**kwargs);queues.append(self)
         def _put(self,item):
          if type(item) is int:
           assert item not in self.free_indices,'DMA output buffer returned twice';self.free_indices.add(item)
          super()._put(item)
          if isinstance(item,tuple) and len(item)==4 and item[0]==3:queued3.set()
         def _get(self):
          item=super()._get()
          if type(item) is int:self.free_indices.remove(item)
          return item
        class Video:
         def __init__(self):
          self.inputs=[bytearray(128) for _ in range(3)];self.outputs=[bytearray(128) for _ in range(3)]
          self.dma=SimpleNamespace(transfer=self.transfer);self.stopped=False
         def transfer(self,fid,src,dst):
          decoded.append(fid)
          dst[0]=fid
          if fid==2:decoded2.set()
         def start(self):pass
         def stop(self):self.stopped=True
        class Camera:
         dropped=0;generation=1;reads=0
         def __enter__(self):return self
         def __exit__(self,*args):pass
         def read(self):
          self.reads+=1
          if self.reads==2:assert encoding.wait(3)
          if self.reads==3:assert decoded2.wait(3)
          if self.reads>3:
           runner.stop_event.wait(3);raise RuntimeError('fixture stopped')
          fid=self.reads
          return fid,time.monotonic_ns(),jpeg,SimpleNamespace(sequence=fid,width=1280,height=720,fps_num=1,fps_den=30)
        class Codec:
         restart_padding_warnings=0
         def __init__(self,*args,**kwargs):pass
         def __enter__(self):return self
         def __exit__(self,*args):pass
         def decode_into(self,*args):pass
         def encode(self,buffer,**kwargs):
          fid=buffer[0];encoded.append(fid)
          if fid==1:encoding.set();assert release_old.wait(3)
          if fid==3:finished3.set()
          return jpeg
        hub=VideoHub();hub.policy.configure({'mode':'manual','fps':30,'quality':85})
        # No cadence limiter in this pressure fixture; the real bounded queues and
        # output-buffer pool are the behavior under test.
        hub.policy.admit=lambda **kwargs:True
        video=Video();runner=runtime.VideoOnlyRunner(object(),None,video=video,source=Camera(),native=None,hub=hub,
         intent_mailbox=IntentMailbox(),output_dir='unused',identity={},hardware=False)
        runner._journal=io.StringIO();runner.associator=SimpleNamespace(associate=lambda fid,stamp:{'valid':True,'frame_id':fid,'epoch':1,'registers':{}})
        runner.association_metrics=SimpleNamespace(observe=lambda *args:None)
        worker=threading.Thread(target=runner._video_loop,daemon=True)
        try:
         with patch.object(runtime,'Codec',Codec),patch.object(runtime,'encode',return_value=[]),patch.object(runtime,'prefix_bgr0',return_value=b'\0'*72),patch.object(runtime.queue,'Queue',Queue):
          worker.start();assert queued3.wait(3),'third camera frame never reached capture slot'
          time.sleep(.02)
          assert decoded==[1,2],f'busy encoder allowed unnecessary PL work: {decoded}'
          release_old.set();assert finished3.wait(3)
          deadline=time.monotonic()+1
          while runner.frames<3 and time.monotonic()<deadline:time.sleep(.002)
          runner.stop_event.set();worker.join(4)
          assert not worker.is_alive();assert not runner.failures,runner.failures
          assert encoded==[1,2,3],f'expected admitted jobs to finish without replacement, got {encoded}'
          assert hub.counts.get('encode_queue_replaced',0)==0
          assert len(hub.times['encode_wait'])==3,'all admitted jobs need measured encoder-wait intervals'
          assert all(value>=0 for value in hub.times['encode_wait'])
          pools=[q for q in queues if q.free_indices]
          assert len(pools)==1 and pools[0].free_indices=={0,1,2},'all DMA outputs must return exactly once'
          assert video.stopped
         print('ENCODE_QUEUE_PASS busy encoder defers PL work; all three DMA buffers returned exactly once')
        finally:
         runner.stop_event.set();release_old.set();worker.join(4)
