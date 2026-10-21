"""Protocol, native JPEG, DMA ownership and real HTTP/WS regressions."""
import asyncio
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'host'));sys.path.insert(0,str(PROJECT/'preintegration/host'))
from wireless_core import ControlGate,IntentMailbox,VideoHub,EncodedFrame
from wireless_dma import FiniteVDMA
from native_video import NativeLibrary,Codec,Camera,FRAME_BYTES,CameraWarmingUp
from wireless_server import WirelessServer


class GateTests(unittest.TestCase):
    def test_sixty_seconds_50ms_intents_and_sync_do_not_spontaneously_revoke(self):
        for seq in range(1,1201):
            self.now=1+seq*.05
            if seq%20==0:
                c=self.gate.challenge('a')
                self.gate.message('a',dict(type='sync',nonce=c['nonce'],received_ms=self.now*1000,sent_ms=self.now*1000))
            self.gate.message('a',dict(type='intent',seq=seq,left=0,right=0,client_ms=self.now*1000))
            self.gate.maintain();self.assertEqual(self.gate.owner,'a');self.assertEqual(self.mail.consume()[0],'intent')
    def setUp(self):
        self.now=1.;self.mail=IntentMailbox(clock=lambda:self.now)
        self.gate=ControlGate(self.mail,clock=lambda:self.now);self.gate.connect('a')
        c=self.gate.challenge('a')
        self.gate.message('a',dict(type='sync',nonce=c['nonce'],received_ms=1000,sent_ms=1000))
        self.gate.message('a',dict(type='claim',client_ms=1000));self.mail.consume()
    def test_only_valid_new_intents_reach_mailbox(self):
        payload=dict(type='intent',seq=1,left=0,right=0,client_ms=1000)
        self.gate.message('a',payload);self.assertEqual(self.mail.consume(),('intent',(1,0,0)))
        with self.assertRaisesRegex(ValueError,'replayed'):self.gate.message('a',payload)
        self.assertIsNone(self.gate.owner);self.assertEqual(self.mail.consume(),('stop',None))
    def test_stale_future_nonzero_bool_fail_closed(self):
        for change in ({'client_ms':800},{'client_ms':1200},{'left':1},{'seq':True}):
            self.gate.owner='a'
            with self.assertRaises(ValueError):
                self.gate.message('a',dict(type='intent',seq=1,left=0,right=0,client_ms=1000,**{} )|change)
            self.assertIsNone(self.gate.owner)
    def test_stop_disconnect_and_reconnect_never_restore_owner(self):
        self.gate.message('a',{'type':'stop'});self.assertIsNone(self.gate.owner)
        self.gate.disconnect('a');self.gate.connect('a')
        with self.assertRaisesRegex(ValueError,'sync'):self.gate.message('a',dict(type='claim',client_ms=1000))
    def test_exclusive_owner_and_clock_expiration(self):
        self.gate.connect('b');c=self.gate.challenge('b')
        self.gate.message('b',dict(type='sync',nonce=c['nonce'],received_ms=1000,sent_ms=1000))
        with self.assertRaisesRegex(ValueError,'another'):self.gate.message('b',dict(type='claim',client_ms=1000))
        self.assertEqual(self.gate.owner,'a');self.now=4.1
        with self.assertRaisesRegex(ValueError,'expired'):self.gate.message('a',dict(type='intent',seq=2,left=0,right=0,client_ms=4100))
    def test_old_claim_and_uncertain_sync_rejected(self):
        self.gate.message('a',{'type':'stop'})
        with self.assertRaisesRegex(ValueError,'claim'):self.gate.message('a',dict(type='claim',client_ms=700))
        c=self.gate.challenge('a');self.now+=.2
        with self.assertRaisesRegex(ValueError,'uncertainty'):self.gate.message('a',dict(type='sync',nonce=c['nonce'],received_ms=1000,sent_ms=1000))
    def test_mailbox_latest_bounded_and_priority_stop(self):
        for _ in range(1000):self.mail.submit(0,0)
        self.assertEqual(self.mail.consume()[1][0],1000)
        self.mail.submit(0,0);self.now+=.101;self.assertEqual(self.mail.consume(),('stop',None))
        self.mail.submit(0,0);self.mail.stop();self.assertEqual(self.mail.consume(),('stop',None))
    def test_queue_delay_includes_original_packet_age(self):
        self.mail.submit(0,0,age_upper_ms=80);self.now+=.021
        self.assertEqual(self.mail.consume(),('stop',None))
    def test_idle_lease_revokes_control_and_requires_new_claim(self):
        self.now+=.251;self.gate.maintain();self.assertIsNone(self.gate.owner)
        with self.assertRaisesRegex(ValueError,'claim'):
            self.gate.message('a',dict(type='intent',seq=1,left=0,right=0,client_ms=self.now*1000))


class HubTests(unittest.TestCase):
    def test_per_minute_zero_gaps_and_weighted_cpu_are_recorded(self):
        hub=VideoHub();hub.start_ns=time.monotonic_ns()-61_000_000_000;hub.observe('captured')
        hub.record_cpu({'two_core_percent':50,'system_total_percent':70,'interval_s':1})
        hub.record_cpu({'two_core_percent':20,'system_total_percent':40,'interval_s':2})
        stats=hub.stats();self.assertEqual(stats['full_minute_fps']['0']['captured'],0)
        self.assertEqual(stats['average_process_two_core_percent'],30)
        self.assertEqual(stats['average_system_total_percent'],50)
    def test_snapshot_uses_new_same_frame_and_immutable_history(self):
        hub=VideoHub();history={'epoch':1};hub.publish(EncodedFrame(1,1,b'\xff\xd8a',b'\xff\xd8b',history))
        history['epoch']=999;self.assertEqual(hub.pair.historical['epoch'],1)
        result=[];worker=threading.Thread(target=lambda:result.append(hub.snapshot()))
        worker.start();time.sleep(.03);hub.publish(EncodedFrame(2,2,b'\xff\xd8c',b'\xff\xd8d',{'epoch':2}))
        worker.join(1);self.assertEqual(result[0].frame_id,2);self.assertEqual(result[0].historical['epoch'],2)
    def test_no_duplicate_frames_or_fake_processed_image(self):
        hub=VideoHub();frame=EncodedFrame(1,1,b'\xff\xd8a',None,{})
        hub.publish(frame);self.assertIsNone(hub.next('processed',0,.001))
        self.assertIsNone(hub.next('raw',1,.001))
        with self.assertRaises(ValueError):hub.publish(frame)
        hub.close();self.assertIsNone(hub.next('raw',0))


class DMATests(unittest.TestCase):
    class MMIO:
        def __init__(self,err=0):self.writes=[];self.err=err
        def write(self,a,v):self.writes.append((a,v))
        def read(self,a):return 0 if a in (0,.0+0x30) else 0x1001|self.err
    class Buffer(bytearray):
        physical_address=0x1000
        def flush(self):self.flushed=True
        def invalidate(self):self.invalidated=True
    def buffers(self):
        buffers=[self.Buffer(FRAME_BYTES) for _ in range(3)]
        for i,buffer in enumerate(buffers):buffer.physical_address=0x1000+i*FRAME_BYTES
        return buffers
    def test_single_frame_write_first_and_completed_ownership(self):
        io=self.MMIO();src,dst,scratch=self.buffers();dma=FiniteVDMA(io,scratch=scratch)
        dma.transfer(1,src,dst)
        self.assertTrue(src.flushed);self.assertTrue(dst.invalidated)
        self.assertLess(io.writes.index((0xa0,720)),io.writes.index((0x50,720)))
        self.assertIn((0xa4,5120),io.writes);self.assertIn((0x30,0x15003),io.writes)
        self.assertIn((0,0x25011),io.writes)
        self.assertIn((0xac,dst.physical_address),io.writes)
        self.assertIn((0xb0,scratch.physical_address),io.writes)
        with self.assertRaises(ValueError):dma.transfer(1,src,dst)
    def test_dma_error_never_exposes_output(self):
        io=self.MMIO(0x20);src,dst,scratch=self.buffers();dma=FiniteVDMA(io,scratch=scratch)
        with self.assertRaises(RuntimeError):dma.transfer(1,src,dst)
        self.assertFalse(hasattr(dst,'invalidated'));self.assertTrue(dma.failed)
    def test_timeout_stops_both_channels(self):
        io=self.MMIO();io.read=lambda a:0;src,dst,scratch=self.buffers();dma=FiniteVDMA(io,scratch=scratch,timeout_s=.001)
        with self.assertRaises(TimeoutError):dma.transfer(1,src,dst)
        self.assertEqual(io.writes[-2:],[(0,0),(0x30,0)])
    def test_rx_irq_without_initial_rx_halt_completes_then_drains(self):
        io=self.MMIO();src,dst,scratch=self.buffers()
        def read(a):
            if a in (0,0x30):return 0
            if a==4:return 0x11001
            return 0x11001 if (0x30,0) in io.writes else 0x11000
        io.read=read;dma=FiniteVDMA(io,scratch=scratch)
        dma.transfer(1,src,dst)
        self.assertTrue(dst.invalidated)
        self.assertEqual(io.writes[-2:],[(0,0),(0x30,0)])
    def test_rx_cannot_halt_never_exposes_destination(self):
        io=self.MMIO();src,dst,scratch=self.buffers()
        io.read=lambda a:0 if a in (0,0x30) else 0x11001 if a==4 else 0x11000
        dma=FiniteVDMA(io,scratch=scratch,timeout_s=.001)
        with self.assertRaises(TimeoutError):dma.transfer(1,src,dst)
        self.assertFalse(hasattr(dst,'invalidated'))
    def test_overlapping_scratch_is_rejected_before_dma_writes(self):
        io=self.MMIO();src,dst,scratch=self.buffers();scratch.physical_address=dst.physical_address+8
        dma=FiniteVDMA(io,scratch=scratch)
        with self.assertRaisesRegex(ValueError,'overlap'):dma.transfer(1,src,dst)
        self.assertEqual(io.writes,[])


NATIVE=PROJECT/'fpga/build/wireless_native_host_v2/Release/car_video.dll'
@unittest.skipUnless(NATIVE.is_file(),'host native build required')
class CodecTests(unittest.TestCase):
    def test_reused_decoder_recovers_after_damage_and_matches_baseline(self):
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(1280,720),(61,143,202)).save(stream,format='JPEG')
        jpeg=stream.getvalue();baseline=bytearray(FRAME_BYTES);actual=bytearray(FRAME_BYTES)
        with Codec(NativeLibrary(NATIVE)) as codec:codec.decode_into(jpeg,baseline)
        for dct in ('islow','ifast'):
            with Codec(NativeLibrary(NATIVE),decode_dct=dct,reuse_decoder=True) as codec:
                for _ in range(2):codec.decode_into(jpeg,actual)
                if dct=='islow':self.assertEqual(actual,baseline)
                with self.assertRaises(RuntimeError):codec.decode_into(b'badJPEG',actual)
                codec.decode_into(jpeg,actual)
                if dct=='islow':self.assertEqual(actual,baseline)
    def test_explicit_profiles_keep_quality_independent_of_sampling(self):
        from PIL import Image
        buffer=bytearray((bytes((20,120,210,0))*1280)*720)
        with Codec(NativeLibrary(NATIVE)) as codec:
            for q in (75,85,95):
                for profile,expected in (('balanced',(2,2)),('balanced_fast',(2,2)),('detail',(1,1))):
                    image=Image.open(io.BytesIO(codec.encode(buffer,q,profile=profile)))
                    image.load()
                    self.assertEqual(image.size,(1280,720))
                    self.assertEqual(image.layer[0][1:3],expected)
                    pixel=image.getpixel((640,360))
                    self.assertTrue(all(abs(a-b)<5 for a,b in zip(pixel,(210,120,20))))
            with self.assertRaisesRegex(ValueError,'profile'):codec.encode(buffer,85,profile='invalid')
    def test_high_quality_preserves_thin_colored_edges_and_baseline_sampling(self):
        from PIL import Image
        import numpy as np
        a=np.zeros((720,1280,4),dtype=np.uint8)
        a[:,:,0:3]=30
        a[:,600:604,0:3]=(0,208,0)
        buffer=bytearray(a.tobytes())
        with Codec(NativeLibrary(NATIVE)) as codec:
            images=[Image.open(io.BytesIO(codec.encode(buffer,q))) for q in (75,85)]
        self.assertEqual(images[0].layer[0][1:3],(2,2))
        self.assertEqual(images[1].layer[0][1:3],(1,1))
        target=a[:,596:608,:3][:,:,::-1].astype(float)
        errors=[np.mean(np.abs(np.asarray(im)[:,596:608].astype(float)-target)) for im in images]
        self.assertLess(errors[1],errors[0]*.6)
    def test_restart_padding_is_pixel_identical_and_other_damage_is_rejected(self):
        from PIL import Image
        image=Image.new('RGB',(1280,720),(90,120,160));stream=io.BytesIO()
        image.save(stream,format='JPEG',restart_marker_blocks=8)
        original=stream.getvalue()
        markers=[i for i in range(len(original)-1) if original[i]==255 and 0xd0<=original[i+1]<=0xd7]
        self.assertTrue(markers,'Fixture must contain real restart intervals')
        point=markers[len(markers)//2]
        baseline=bytearray(FRAME_BYTES);decoded=bytearray(FRAME_BYTES)
        with Codec(NativeLibrary(NATIVE)) as codec:
            codec.decode_into(original,baseline)
            for count in (1,3,4,9,32):
                codec.decode_into(original[:point]+b'\x00'*count+original[point:],decoded)
                self.assertEqual(decoded,baseline)
                self.assertEqual(codec.restart_padding_warnings,1)
            for bad in (original[:-50]+b'\xff\xd9',
                        original[:-2]+b'\x00\x00'+original[-2:]):
                with self.assertRaises(RuntimeError):codec.decode_into(bad,decoded)
            codec.decode_into(original,decoded)
            self.assertEqual(codec.restart_padding_warnings,0)

    def test_closed_handle_and_invalid_quality_are_safe(self):
        codec=Codec(NativeLibrary(NATIVE));codec.close()
        with self.assertRaisesRegex(RuntimeError,'closed'):codec.encode(bytearray(FRAME_BYTES))
        with Codec(NativeLibrary(NATIVE)) as codec:
            with self.assertRaises(ValueError):codec.encode(bytearray(FRAME_BYTES),0)
    def test_real_jpeg_roundtrip_dimensions_color_and_invalid_inputs(self):
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(1280,720),(210,50,20)).save(stream,format='JPEG',quality=90)
        buffer=bytearray(FRAME_BYTES)
        with Codec(NativeLibrary(NATIVE)) as codec:
            codec.decode_into(stream.getvalue(),buffer)
            self.assertLess(abs(buffer[0]-20),4);self.assertLess(abs(buffer[2]-210),4)
            jpeg=codec.encode(buffer);image=Image.open(io.BytesIO(jpeg))
            self.assertEqual(image.size,(1280,720));self.assertEqual(image.layer[1][1:3],(1,1))
            with self.assertRaises(RuntimeError):codec.decode_into(b'badJPEG',buffer)
            wrong=io.BytesIO();Image.new('RGB',(640,480)).save(wrong,format='JPEG')
            with self.assertRaisesRegex(RuntimeError,'1280x720'):codec.decode_into(wrong.getvalue(),buffer)
            with self.assertRaises(ValueError):codec.encode(buffer[:-1])
    def test_host_capture_explicitly_unavailable(self):
        with self.assertRaisesRegex(RuntimeError,'Linux'):Camera(NativeLibrary(NATIVE)).__enter__()


class CameraStartupTests(unittest.TestCase):
    def test_bad_v4l2_frame_is_discarded_without_closing_camera(self):
        from types import SimpleNamespace
        from native_video import CameraFrameRejected
        closed=[]
        lib=SimpleNamespace(wv_camera_open=lambda *args:42,wv_camera_close=lambda h:closed.append(h),
                            wv_camera_read=lambda *args:-2)
        camera=Camera(SimpleNamespace(lib=lib));camera.__enter__()
        with self.assertRaises(CameraFrameRejected) as error:camera.read()
        self.assertEqual(error.exception.reason,'v4l2_bad_frame')
        self.assertEqual(camera.handle,42);self.assertEqual(closed,[])
        camera.close();self.assertEqual(closed,[42])
    def test_stale_startup_frame_is_discarded_and_future_or_steady_stale_frames_fail(self):
        import ctypes
        from types import SimpleNamespace
        from native_video import FrameInfo
        stamp=[1_000_000_000]
        def read(handle,storage,size,info,timeout):
            ctypes.cast(info,ctypes.POINTER(FrameInfo)).contents.captured_ns=stamp[0]
            return 4
        lib=SimpleNamespace(wv_camera_open=lambda *args:42,
            wv_camera_close=lambda *args:None,wv_camera_read=read)
        camera=Camera(SimpleNamespace(lib=lib))
        with patch('native_video.time.monotonic',return_value=0):camera.__enter__()
        try:
            with patch('native_video.time.monotonic',return_value=3),patch('native_video.time.monotonic_ns',return_value=3_000_000_000):
                with self.assertRaises(CameraWarmingUp):camera.read()
                self.assertIsNone(camera.last_sequence)
                stamp[0]=4_000_000_000
                with self.assertRaises(RuntimeError):camera.read()
                stamp[0]=1_000_000_000;camera.last_sequence=1
                with self.assertRaises(RuntimeError):camera.read()
        finally:camera.close()

    def test_first_frame_wait_is_bounded_and_steady_timeout_stays_strict(self):
        from types import SimpleNamespace
        lib=SimpleNamespace(wv_camera_open=lambda *args:42,
            wv_camera_close=lambda *args:None,wv_camera_read=lambda *args:0)
        camera=Camera(SimpleNamespace(lib=lib))
        with patch('native_video.time.monotonic',return_value=100):camera.__enter__()
        try:
            with patch('native_video.time.monotonic',return_value=104.9):
                with self.assertRaises(CameraWarmingUp):camera.read()
            with patch('native_video.time.monotonic',return_value=105):
                with self.assertRaises(TimeoutError) as result:camera.read()
                self.assertNotIsInstance(result.exception,CameraWarmingUp)
            camera.last_sequence=1
            with patch('native_video.time.monotonic',return_value=101):
                with self.assertRaises(TimeoutError) as result:camera.read()
                self.assertNotIsInstance(result.exception,CameraWarmingUp)
        finally:camera.close()


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_video_only_websocket_cannot_claim_or_deliver_intent(self):
        self.runner.control_available=False
        async with self.client.ws_connect(self.base+'/api/control',headers=self.auth) as ws:
            await ws.receive_json()
            for payload in ({'type':'claim','client_ms':0},{'type':'intent','seq':1,'left':0,'right':0}):
                await ws.send_json(payload)
                reply=await ws.receive_json()
                self.assertEqual(reply['type'],'error')
                self.assertFalse(self.server.gate.status()['owned'])
                self.assertEqual(self.mail.consume(),('stop',None))
    async def asyncSetUp(self):
        # IsolatedAsyncioTestCase enables asyncio debug instrumentation. On this
        # Windows host that adds ~50 ms to loopback sync RTT, versus <1 ms with
        # the production loop configuration. Exercise real timestamps with the
        # production configuration; GateTests still cover the strict deadlines.
        asyncio.get_running_loop().set_debug(False)
        from types import SimpleNamespace
        self.tmp=tempfile.TemporaryDirectory();self.hub=VideoHub();self.mail=IntentMailbox()
        self.runner=SimpleNamespace(output_dir=Path(self.tmp.name),status_snapshot=lambda:{'running':True,'motion_allowed':False})
        self.server=WirelessServer(self.runner,self.hub,self.mail,'127.0.0.1',0)
        await self.server.start_async();self.base=f'http://127.0.0.1:{self.server.port}'
        from aiohttp import ClientSession,CookieJar
        self.client=ClientSession(cookie_jar=CookieJar(unsafe=True))
        self.auth={'Authorization':'Bearer '+self.server.token,'Origin':self.base}
    async def asyncTearDown(self):
        self.hub.close();await self.client.close();await self.server.stop_async();self.tmp.cleanup()
    async def test_auth_cookie_origin_and_restart_token(self):
        async with self.client.get(self.base+'/api/status') as r:self.assertEqual(r.status,401)
    async def test_video_policy_auth_settings_and_active_feedback(self):
        async with self.client.post(self.base+'/api/video/settings',json={'mode':'manual'}) as r:self.assertEqual(r.status,401)
        async with self.client.post(self.base+'/api/video/settings',headers=self.auth,json={'mode':'manual','fps':24,'quality':65}) as r:
            p=await r.json();self.assertEqual((p['output_fps'],p['jpeg_quality']),(24,65))
        async with self.client.post(self.base+'/api/video/settings',headers=self.auth,json={'mode':'auto','fps':True}) as r:self.assertEqual(r.status,400)
        async with self.client.post(self.base+'/api/video/feedback',headers=self.auth,json={'visible':True,'received_fps':1,'drawn_fps':1}) as r:self.assertEqual(r.status,400)
        jpeg=b'\xff\xd8abc\xff\xd9';self.hub.publish(EncodedFrame(1,time.monotonic_ns(),jpeg,jpeg,{}))
        async with self.client.get(self.base+'/api/video',headers=self.auth) as stream:
            session=stream.headers['X-Video-Session'];await stream.content.read(1024)
            async with self.client.post(self.base+'/api/video/feedback',headers=self.auth,json={'video_session':session,'visible':True,'received_fps':24,'drawn_fps':24}) as r:self.assertEqual(r.status,200)
            self.assertEqual(self.mail.consume(),(None,None))
    async def test_network_write_timeout_is_congestion_not_whole_session_failure(self):
        from types import SimpleNamespace
        from wireless_policy import VideoPolicy
        now=[0.];self.hub.policy=VideoPolicy(clock=lambda:now[0]);self.hub.policy.configure({'mode':'auto'})
        jpeg=b'\xff\xd8abc\xff\xd9'
        class Response:
            def __init__(self,**kwargs):pass
            async def prepare(self,request):pass
            async def write(self,chunk):raise asyncio.TimeoutError('injected slow client')
        request=SimpleNamespace(query={'view':'processed'})
        with patch.object(self.server,'check'),patch('wireless_server.web.StreamResponse',Response):
            for n in range(3):
                now[0]=n*1.1;self.hub.publish(EncodedFrame(n,time.monotonic_ns(),jpeg,jpeg,{}))
                await self.server.video(request)
        self.assertEqual(self.hub.policy.settings()['level'],1)
        self.assertFalse(self.hub.closed);self.assertIsNone(self.hub.error)
        self.assertEqual(self.mail.consume(),(None,None))
        async with self.client.post(self.base+'/api/session',headers=self.auth) as r:self.assertEqual(r.status,200)
        async with self.client.get(self.base+'/api/status') as r:self.assertEqual(r.status,200)
        async with self.client.post(self.base+'/api/stop') as r:self.assertEqual(r.status,403)
        async with self.client.post(self.base+'/api/stop',headers={'Origin':'http://evil'}) as r:self.assertEqual(r.status,403)
        self.server.cookie='different-run'
        async with self.client.get(self.base+'/api/status') as r:self.assertEqual(r.status,401)
    async def claim_after_precise_sync(self,ws):
        # A legal <=50 ms sync can still be too uncertain for the stricter
        # future-intent bound. Retry actual challenges; never widen the gate
        # or fabricate a backdated client timestamp to make this test pass.
        deadline=time.monotonic()+5;last=None
        while time.monotonic()<deadline:
            challenge=await ws.receive_json(timeout=2)
            if challenge.get('type')!='sync':continue
            received=time.monotonic()*1000
            await ws.send_json(dict(type='sync',nonce=challenge['nonce'],
                received_ms=received,sent_ms=time.monotonic()*1000))
            reply=await ws.receive_json(timeout=2);last=reply
            if reply.get('type')!='synced' or reply['uncertainty_ms']>2.5:continue
            await ws.send_json(dict(type='claim',client_ms=time.monotonic()*1000))
            reply=await ws.receive_json(timeout=2);last=reply
            if reply.get('type')=='claimed':return
        self.fail('no precise real-loopback sync/claim within 5 seconds: '+repr(last))

    async def test_actual_websocket_sync_intent_replay_stop_disconnect(self):
        async with self.client.ws_connect(self.base+'/api/control',headers=self.auth) as ws:
            await self.claim_after_precise_sync(ws);self.mail.consume()
            payload=dict(type='intent',seq=1,left=0,right=0,client_ms=time.monotonic()*1000)
            await ws.send_json(payload);self.assertEqual((await ws.receive_json())['seq'],1)
            self.assertEqual(self.mail.consume()[0],'intent')
            await ws.send_json(payload);self.assertEqual((await ws.receive_json())['type'],'error')
            self.assertIsNone(self.server.gate.owner);self.assertEqual(self.mail.consume()[0],'stop')
    async def test_stop_revokes_owner_and_timing_report_does_not_submit_intent(self):
        async with self.client.ws_connect(self.base+'/api/control',headers=self.auth) as ws:
            await self.claim_after_precise_sync(ws)
            self.assertIsNotNone(self.server.gate.owner)
            self.mail.consume();await ws.send_json({'type':'ack_timing','rtt_ms':10});await asyncio.sleep(.02)
            self.assertEqual(self.mail.consume(),(None,None))
            async with self.client.post(self.base+'/api/stop',headers=self.auth) as r:self.assertEqual(r.status,200)
            self.assertIsNone(self.server.gate.owner);self.assertEqual(self.mail.consume(),('stop',None))


    async def test_mjpeg_header_identity_and_same_frame_snapshot(self):
        jpeg=b'\xff\xd8abc\xff\xd9';self.hub.publish(EncodedFrame(1,time.monotonic_ns(),jpeg,jpeg,{'epoch':1}))
        async with self.client.get(self.base+'/api/video?view=processed',headers=self.auth) as r:
            self.assertEqual(r.status,200);data=await r.content.read(1024);self.assertIn(b'X-Frame-Id: 1',data)
        request=asyncio.create_task(self.client.post(self.base+'/api/snapshot',headers=self.auth,json={}))
        for _ in range(100):
            if self.hub.snapshot_requested:break
            await asyncio.sleep(.01)
        self.assertTrue(self.hub.snapshot_requested)
        self.hub.publish(EncodedFrame(2,time.monotonic_ns(),jpeg,jpeg,{'epoch':2}))
        async with await request as r:
            frozen=await r.json();self.assertEqual(frozen['frame_id'],2);self.assertEqual(frozen['historical_snapshot']['epoch'],2)


class PipelineTests(unittest.TestCase):
    def run_pipeline(self,view,fail_once=False,warmup=False):
        from types import SimpleNamespace
        from test_joint_runtime import Link,Client
        from wireless_runtime import WirelessRunner
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(1280,720),(200,80,30)).save(stream,format='JPEG')
        jpeg=stream.getvalue();native=NativeLibrary(NATIVE)
        class Source:
            dropped=0;closed=False;number=0;failed=False;opens=0;startup_waits=0
            def __enter__(self):self.opens+=1;return self
            def read(self):
                if warmup and self.startup_waits<2:
                    self.startup_waits+=1;time.sleep(.015)
                    raise CameraWarmingUp('injected first-frame startup wait')
                if fail_once and not self.failed:
                    self.failed=True;raise RuntimeError('injected camera disconnect')
                time.sleep(.015);self.number+=1
                return self.number,time.monotonic_ns(),jpeg,SimpleNamespace(sequence=self.number,width=1280,height=720,fps_num=1,fps_den=30)
            def close(self):self.closed=True
            def __exit__(self,*args):self.close()
        class Video:
            worker_owned_shutdown=True;stopped=False
            def start(self):
                self.calls=[]
                self.inputs=[bytearray(FRAME_BYTES) for _ in range(3)]
                self.outputs=[bytearray(FRAME_BYTES) for _ in range(3)]
                self.dma=SimpleNamespace(transfer=self.transfer)
            def transfer(self,identity,src,dst):
                self.calls.append(identity);dst[:]=src # Explicit OFFLINE DMA fixture, never PL proof.
            def stop(self):self.stopped=True
        hub=VideoHub();hub.set_view(view);mail=IntentMailbox();video=Video();source=Source();link=Link()
        with tempfile.TemporaryDirectory() as tmp:
            runner=WirelessRunner(Client(link),link,video=video,source=source,native=native,hub=hub,
                    intent_mailbox=mail,output_dir=tmp,identity={'offline_fixture':True},hardware=False)
            result=runner.run(.7 if fail_once else .4)
            self.assertTrue(result['passed'],result['failures']);self.assertGreater(result['frames'],0)
            self.assertFalse(any(t.is_alive() for t in runner.children));self.assertTrue(video.stopped and source.closed)
            self.assertEqual(runner.client.command,0) # No network intent: status never renews lease.
            if fail_once:
                self.assertGreaterEqual(result['samples'],10);self.assertTrue(runner.video_faults)
                self.assertGreater(hub.counts['camera_reconnects'],0)
            if warmup:
                self.assertEqual(source.opens,1)
                self.assertEqual(hub.counts['camera_startup_waits'],2)
                self.assertEqual(hub.counts.get('camera_reconnects',0),0)
            return video.calls,hub
    @unittest.skipUnless(NATIVE.is_file(),'host native build required')
    def test_processed_workers_complete_distinct_frames_and_join_before_free(self):
        calls,hub=self.run_pipeline('processed');self.assertTrue(calls)
        self.assertEqual(calls,sorted(set(calls)));self.assertIsNotNone(hub.pair.processed)
        self.assertFalse(hub.stats()['hardware_performance_validated'])
    @unittest.skipUnless(NATIVE.is_file(),'host native build required')
    def test_raw_mode_skips_full_decode_dma_and_reencoding(self):
        calls,hub=self.run_pipeline('raw');self.assertEqual(calls,[]);self.assertIsNone(hub.latest.processed)
    @unittest.skipUnless(NATIVE.is_file(),'host native build required')
    def test_camera_fault_recovers_without_ending_local_control(self):
        calls,hub=self.run_pipeline('processed',True);self.assertTrue(calls);self.assertIsNone(hub.error)

    @unittest.skipUnless(NATIVE.is_file(),'host native build required')
    def test_first_frame_warmup_keeps_stream_open_and_workers_close(self):
        calls,hub=self.run_pipeline('processed',warmup=True)
        self.assertTrue(calls);self.assertIsNone(hub.error)


if __name__=='__main__':unittest.main()
