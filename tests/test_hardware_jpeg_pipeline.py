"""Pressure the real pipeline ownership while a slow PL transaction holds input."""
import io,sys,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pynq_fpga/preintegration/host'))
import wireless_runtime as runtime
from wireless_core import VideoHub,IntentMailbox


class HardwarePipelineTests(unittest.TestCase):
    def test_decode_never_overwrites_a_source_held_by_PL(self):
        self.exercise_pipeline(False)
    def test_late_decode_cannot_publish_an_older_frame(self):
        self.exercise_pipeline(True)
    def exercise_pipeline(self,reorder):
        jpeg=b'\xff\xd8fixture\xff\xd9';seen=[];decoded=[]
        lanes=set()
        class Video:
            hardware_jpeg=True
            def __init__(self):
                self.inputs=[bytearray(128) for _ in range(3)];self.outputs=[bytearray(128) for _ in range(3)]
                self.dma=SimpleNamespace(transfer=self.transfer,last_timings={});self.stopped=False
            def start(self):pass
            def stop(self):self.stopped=True
            def transfer(self,fid,source,dest,quality):
                self_check=source[80];assert self_check==fid%256
                time.sleep(.015)
                assert source[80]==self_check,'CPU decode overwrote an in-flight PL source'
                seen.append(fid)
                if len(seen)>=16:runner.stop_event.set()
                return jpeg
        class Camera:
            generation=1;dropped=0;sequence=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):
                time.sleep(.001);self.sequence+=1;fid=self.sequence
                return fid,time.monotonic_ns(),jpeg+bytes([fid%256]),SimpleNamespace(sequence=fid,width=1280,height=720,fps_num=1,fps_den=30)
        class Decoder:
            restart_padding_warnings=0
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def decode_into(self,data,buffer):
                lanes.add(threading.get_ident())
                if reorder:time.sleep(.03 if data[-1]%2 else .001)
                buffer[80]=data[-1];decoded.append(data[-1])
        video=Video();hub=VideoHub();hub.policy.admit=lambda **kwargs:True
        runner=runtime.VideoOnlyRunner(object(),None,video=video,source=Camera(),native=None,hub=hub,
            intent_mailbox=IntentMailbox(),output_dir='unused',identity={},hardware=False)
        runner._journal=io.StringIO();runner.associator=SimpleNamespace(associate=lambda fid,stamp:{'valid':True,'frame_id':fid,'epoch':1,'registers':{}})
        runner.association_metrics=SimpleNamespace(observe=lambda *args:None)
        with patch.object(runtime,'Codec',Decoder),patch.object(runtime,'encode',return_value=[]),patch.object(runtime,'prefix_bgr0',return_value=b'\x00'*72):
            worker=threading.Thread(target=runner._video_loop,daemon=True);worker.start();worker.join(4)
            runner.stop_event.set();worker.join(3)
        self.assertFalse(worker.is_alive());self.assertFalse(runner.failures,runner.failures)
        self.assertGreaterEqual(len(seen),16);self.assertEqual(seen,sorted(set(seen)))
        self.assertTrue(video.stopped);self.assertEqual(hub.latest.historical['processing_state'],'real_PL_JPEG_DMA')
        self.assertGreater(runner.frames,0)
        if reorder:
            self.assertEqual(len(lanes),2)
            self.assertGreater(hub.counts.get('decode_completion_superseded',0),0)

if __name__=='__main__':unittest.main()
