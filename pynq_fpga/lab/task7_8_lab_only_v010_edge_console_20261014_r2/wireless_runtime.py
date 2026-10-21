"""Headless 720p capture -> PL -> JPEG, with independent control ownership."""
from contextlib import ExitStack
import argparse
import hashlib
import json
import math
from contextlib import nullcontext
from pathlib import Path
import queue
import threading
import time
from collections import deque
from system_runtime import (JointRunner,DeviceLease,open_verified_overlay,validate_ip_dict,
    PerceptionClient,PynqMMIO,CONTROL_BASE,CONTROL_LENGTH,wait_for_acquisition,session_identity,
    EvidenceSession,write_new_json)
from lab_acceptance import verify_package
from native_video import NativeLibrary,Camera,Codec,CameraWarmingUp,CameraFrameRejected
from wireless_core import VideoHub,IntentMailbox,EncodedFrame
from wireless_dma import WirelessBoardVideo,audit_wireless_hwh
from wireless_server import WirelessServer
from frame_metadata import encode,prefix_bgr0
from calibration_config import CalibrationConfig
from qei_quality import BENCH_FILTER_TICKS
from motion_display import MeasuredDriveModel
import car_regs as reg
from perception_replay import snapshot_registers

HERE=Path(__file__).resolve().parent
WIRELESS_FILES=('wireless_runtime.py','wireless_core.py','wireless_dma.py','wireless_server.py',
                'wireless_policy.py','wireless_player.js',
                'native_video.py','wireless_page.html','wireless_benchmark.py','wireless_requirements.txt',
                'native/CMakeLists.txt','native/car_video.c','WIRELESS_SETUP.md')


def verify_wireless(manifest,hwh):
    package=json.loads(Path(manifest).read_text(encoding='utf-8-sig'))
    if package.get('video_profile')!='wireless720':raise ValueError('a wireless720 candidate is required')
    hashes=package.get('wireless_files',{})
    if set(hashes)!=set(WIRELESS_FILES):raise ValueError('wireless source inventory mismatch')
    for name,expected in hashes.items():
        path=Path(manifest).parent/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('wireless package hash mismatch: '+name)
        # Runtime must load the verified packaged implementation, not a sibling checkout.
        if (HERE/name).is_file() and hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('loaded wireless code differs: '+name)
    audit_wireless_hwh(hwh)
    return hashes


class WirelessRunner(JointRunner):
    def __init__(self,*args,native,hub,jpeg_profile='balanced',decode_dct='islow',reuse_decoder=False,**kwargs):
        super().__init__(*args,**kwargs);self.native=native;self.hub=hub
        self.children=[];self.pipeline_safe=True;self.video_shutdown_confirmed=True
        self.jpeg_profile=jpeg_profile
        self.decode_dct=decode_dct;self.reuse_decoder=reuse_decoder
        self.cpu_wall=time.monotonic();self.cpu_time=time.process_time()
        self.system_cpu_previous=None
        self.video_faults=deque(maxlen=32)

    def status_snapshot(self):
        result=super().status_snapshot()
        with self._state_lock:result['video_faults']=list(self.video_faults)
        return result

    def step(self):
        super().step()
        self.record_performance()

    def record_performance(self):
        now=time.monotonic()
        if now-self.cpu_wall>=1:
            cpu=time.process_time();elapsed=now-self.cpu_wall
            system_percent=None
            try:
                values=[int(n) for n in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
                current=(sum(values),values[3]+values[4])
                if self.system_cpu_previous and current[0]>self.system_cpu_previous[0]:
                    system_percent=100*(1-(current[1]-self.system_cpu_previous[1])/(current[0]-self.system_cpu_previous[0]))
                self.system_cpu_previous=current
            except (OSError,ValueError,IndexError):pass
            memory={}
            for file,keys in (('/proc/self/status',('VmRSS','VmHWM')),('/proc/meminfo',('MemAvailable','MemTotal'))):
                try:
                    for line in Path(file).read_text().splitlines():
                        key,_,value=line.partition(':')
                        if key in keys:memory[key+'_KiB']=int(value.strip().split()[0])
                except (OSError,ValueError,IndexError):pass
            process_percent=(cpu-self.cpu_time)/elapsed*50
            self.hub.record_cpu({'two_core_percent':process_percent,
                                  'system_total_percent':system_percent,
                                  'memory':memory,'dma_reserved_bytes':7*1280*720*4,
                                  'interval_s':elapsed,'scope':'process + Linux aggregate /proc/stat'})
            self.hub.policy.observe(backlogged=process_percent>80 or (system_percent is not None and system_percent>80),source='cpu')
            self.cpu_wall=now;self.cpu_time=cpu
            self.log({'type':'wireless_performance','host_monotonic_ns':time.monotonic_ns(),**self.hub.stats()})

    def _video_loop(self):
        captured=queue.Queue(maxsize=1);jobs=queue.Queue(maxsize=3);free=queue.Queue(maxsize=3)
        def put_until_stop(target,item):
            while not self.stop_event.is_set():
                try:target.put(item,timeout=.05);return True
                except queue.Full:pass
            return False
        def capture():
            previous_dropped=0;backoff=.25
            while not self.stop_event.is_set():
                try:
                    with self.source:
                        while not self.stop_event.is_set():
                            try:item=self.source.read()
                            except CameraWarmingUp:
                                self.hub.observe('camera_startup_waits');continue
                            except CameraFrameRejected as exc:
                                self.hub.observe('camera_frame_rejected')
                                self.hub.set_error('capture frame: '+exc.reason)
                                self.intent_mailbox.stop()
                                self.log_frame_fault(exc.reason,exc.frame_id,exc.jpeg,exc.diagnostics)
                                continue
                            self.hub.observe('captured');backoff=.25
                            self.hub.observe('camera_dropped',amount=self.source.dropped-previous_dropped)
                            previous_dropped=self.source.dropped
                            try:captured.put_nowait(item)
                            except queue.Full:
                                try:captured.get_nowait();self.hub.observe('decode_dropped');self.hub.observe('capture_queue_replaced')
                                except queue.Empty:pass
                                captured.put_nowait(item)
                except Exception as exc:
                    if self.stop_event.is_set():return
                    self.hub.set_error('capture: '+str(exc));self.intent_mailbox.stop()
                    fault={'type':'wireless_video_fault','host_monotonic_ns':time.monotonic_ns(),
                           'reason':str(exc),'action':'revoke_remote_intent_and_retry_camera'}
                    with self._state_lock:self.video_faults.append(fault)
                    self.log(fault);self.hub.observe('camera_reconnects')
                    self.stop_event.wait(backoff);backoff=min(2,backoff*2)
        def encoder():
            try:
                with Codec(self.native) as codec:
                    while not self.stop_event.is_set():
                        try:
                            job=jobs.get(timeout=.05)
                            while True:
                                try:newer=jobs.get_nowait()
                                except queue.Empty:break
                                if job[-1] is not None:free.put_nowait(job[-1])
                                self.hub.observe('encode_queue_replaced')
                                job=newer
                        except queue.Empty:continue
                        frame_id,stamp,jpeg,historical,index=job
                        processed=None
                        if index is not None:
                            try:
                                started=time.monotonic_ns()
                                historical['encode_started_host_ns']=started
                                historical['PL_done_to_encode_start_ms']=(started-historical['pl_completed_host_ns'])/1e6
                                self.hub.observe('encode_wait',historical['PL_done_to_encode_start_ms'],amount=0)
                                processed=codec.encode(self.video.outputs[index],quality=historical['jpeg_quality'],profile=self.jpeg_profile)
                                cost=(time.monotonic_ns()-started)/1e6
                                historical['encode_ms']=cost
                                self.hub.observe('encoded',cost);self.hub.policy.observe(cost_ms=cost,source='encode')
                            finally:free.put_nowait(index)
                        historical['encoded_host_ns']=time.monotonic_ns()
                        historical['capture_to_encoded_ms']=(historical['encoded_host_ns']-stamp)/1e6
                        if self.stop_event.is_set():
                            break
                        if not self.hub.publish(EncodedFrame(frame_id,stamp,jpeg,processed,historical)):
                            self.hub.observe('stale_completed_frame')
                            continue
                        self.frames+=1;self.hub.observe('published');self.metrics.observe(stamp)
                        self.log({'type':'wireless_frame',**historical})
            except Exception as exc:
                if not self.stop_event.is_set():self.fail('encoder: '+str(exc));self.hub.close(str(exc))
        try:
            self.video_shutdown_confirmed=False
            self.video.start()
            for index in range(3):free.put_nowait(index)
            self.children=[threading.Thread(target=capture,name='uvc-capture',daemon=True),
                           threading.Thread(target=encoder,name='jpeg-encode',daemon=True)]
            for child in self.children:child.start()
            with Codec(self.native,decode_dct=self.decode_dct,reuse_decoder=self.reuse_decoder) as decoder:
                input_index=0
                while not self.stop_event.is_set():
                    try:frame_id,stamp,jpeg,info=captured.get(timeout=.05)
                    except queue.Empty:continue
                    if time.monotonic_ns()-stamp>100_000_000:
                        self.hub.observe('decode_dropped');self.hub.observe('capture_age_rejected');continue
                    if not self.hub.policy.admit(force=self.hub.snapshot_requested):
                        self.hub.observe('rate_limited');continue
                    historical=self.associator.associate(frame_id,stamp)
                    settings=self.hub.policy.settings()
                    historical.update(captured_monotonic_ns=stamp,
                        jpeg_quality=settings['jpeg_quality'],
                        jpeg_profile=self.jpeg_profile,
                        jpeg_subsampling='4:2:0' if self.jpeg_profile in ('balanced','balanced_fast') or (self.jpeg_profile=='legacy' and settings['jpeg_quality']<85) else '4:4:4',
                        output_fps=settings['output_fps'],
                        timestamp_scope='V4L2_monotonic_capture_timestamp_not_measured_exposure',
                        capture_sequence=info.sequence,negotiated_width=info.width,negotiated_height=info.height,
                        capture_generation=getattr(self.source,'generation',0),
                        negotiated_fps=info.fps_den/info.fps_num,processing_state='raw_passthrough')
                    if not historical['valid']:
                        # The camera may return a pre-session queued frame; do not attach future sensors.
                        self.hub.observe('decode_dropped');self.hub.observe('association_rejected');continue
                    index=None
                    if self.hub.needs_encode():
                        try:index=free.get(timeout=.05)
                        except queue.Empty:
                            self.hub.observe('encode_dropped');self.hub.policy.observe(backlogged=True,source='pipeline');continue
                        source=self.video.inputs[input_index];input_index=(input_index+1)%3
                        try:
                            started=time.monotonic_ns()
                            try:decoder.decode_into(jpeg,source)
                            except RuntimeError as exc:
                                free.put_nowait(index);self.hub.observe('corrupt_jpeg')
                                self.hub.set_error('decode: '+str(exc));self.intent_mailbox.stop()
                                self.log_frame_fault(str(exc),frame_id,jpeg,{'capture_sequence':info.sequence,'v4l2_flags':info.flags})
                                continue
                            historical['decode_ms']=(time.monotonic_ns()-started)/1e6
                            self.hub.observe('decoded',historical['decode_ms'])
                            self.hub.observe('jpeg_restart_padding_warnings',amount=decoder.restart_padding_warnings)
                            words=encode(historical);prefix=prefix_bgr0(words)
                            memoryview(source).cast('B')[:len(prefix)]=prefix
                            started=time.monotonic_ns()
                            historical['submitted_host_ns']=started
                            historical['receive_to_submit_ms']=(started-stamp)/1e6
                            self.video.dma.transfer(frame_id,source,self.video.outputs[index])
                            historical['pl_process_ms']=(time.monotonic_ns()-started)/1e6
                            self.hub.observe('processed',historical['pl_process_ms'])
                            historical.update(processing_state='real_PL_S2MM',pl_completed_host_ns=time.monotonic_ns(),
                                              display_metadata_words=words,dma_timing_ms=getattr(self.video.dma,'last_timings',{}))
                            self.association_metrics.observe(historical)
                        except Exception:
                            free.put_nowait(index);raise
                    if not put_until_stop(jobs,(frame_id,stamp,jpeg,historical,index)):
                        if index is not None:free.put_nowait(index)
        except Exception as exc:
            if not self.stop_event.is_set():self.fail('wireless video: '+str(exc));self.hub.close(str(exc))
        finally:
            self.stop_event.set()
            self.hub.close(self.failures[-1] if self.failures else None)
            for child in self.children:child.join(timeout=2)
            self.pipeline_safe=all(not c.is_alive() for c in self.children)
            if self.pipeline_safe:
                try:
                    self.video.stop()
                    self.video_shutdown_confirmed=True
                except Exception as exc:self.fail('wireless DMA halt: '+str(exc))
            else:
                self.fail('codec/capture worker did not terminate; DMA buffers retained')
                # Prevent JointRunner from freeing memory still used by a native call.
                self.video=None
            self.hub.close(self.failures[-1] if self.failures else None)

    def log_frame_fault(self,reason,frame_id,jpeg=None,diagnostics=None):
        """Bounded bad-frame evidence; never retain a normal video backlog."""
        count=getattr(self,'_saved_bad_frames',0)
        event={'type':'wireless_video_fault','reason':reason,'frame_id':frame_id,
               'host_monotonic_ns':time.monotonic_ns(),'action':'discard_corrupt_frame',
               'diagnostics':diagnostics or {}}
        if jpeg and count<8:
            directory=self.output_dir/'bad_frames';directory.mkdir(exist_ok=True)
            name=f'frame_{count:02d}.jpg';(directory/name).write_bytes(jpeg)
            event.update(sample_file='bad_frames/'+name,sha256=hashlib.sha256(jpeg).hexdigest())
            self._saved_bad_frames=count+1
        self.log(event)


class VideoOnlyRunner(WirelessRunner):
    """Actual production video pipeline with no UART or actuator operations.

    A single owner samples actual PL snapshots for historical display. Missing
    sensor calibration remains missing; this session cannot pass joint/control
    acceptance or fabricate STM32 feedback.
    """
    control_available = False

    def step(self):
        _, shot, _ = self.client.sample_and_decide()
        before = time.monotonic_ns()
        ticks = self.client.read_pl_ticks64()
        after = time.monotonic_ns()
        registers = snapshot_registers(shot)
        anchor = self.associator.publish(host_before_ns=before, host_after_ns=after,
            pl_ticks64=ticks, registers=registers, epoch=shot.epoch)
        clean_speeds = self.speed_display.update(shot,ticks&0xffffffff)
        presentation = self.motion_display.update(shot,clean_speeds,ticks)
        presentation['expires_monotonic_ns'] = after+int(presentation['valid_for_s']*1e9)
        event = {'type':'video_display_sample','host_monotonic_ns':after,
                 'epoch':shot.epoch,'registers':registers,'clock_anchor':anchor,
                 'status':{'published_monotonic_ns':after,'car_valid':False,
                           'distance_valid':False,'speed_valid':False,
                           'odometry_valid':False,'pl_stop':None,'motion_display':presentation},
                 'control':'unavailable_in_video_only_session'}
        with self._state_lock:
            self.latest = event
            self.samples += 1
        self.log(event)
        self.record_performance()

    def status_snapshot(self):
        result = super().status_snapshot()
        result.update(control_available=False,session_scope='video_only',
                      joint_acceptance_validated=False)
        return result

    def enqueue_action(self, kind, payload=None):
        raise RuntimeError('video-only session cannot control or calibrate hardware')

    def run(self, duration_s):
        if not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError('positive finite duration required')
        if self.evidence_session is None:
            self.evidence_session = EvidenceSession(self.output_dir)
        started = time.monotonic()
        self._journal = self.evidence_session.open_journal('video.jsonl')
        self.log({'type':'header','schema':'car-video-only-session/v1',
                  'identity':self.identity,'hardware':self.hardware,
                  'motion_display_configuration':self.motion_display.configuration(),
                  'uart_opened':False,'control_available':False,
                  'motion_allowed':False,'duration_requested_s':duration_s})
        try:
            self.client.verify_contract()
            self.step()
            self._worker=threading.Thread(target=self._video_loop,name='video-pipeline',daemon=True)
            self._worker.start()
            while time.monotonic()-started<duration_s and not self.stop_event.wait(self.interval_s):
                self.step()
        except KeyboardInterrupt:
            self.fail('operator interrupted video session')
        except Exception as exc:
            self.fail('video-only snapshot owner: '+str(exc))
        finally:
            self.stop_event.set()
            if self._worker is not None:
                self._worker.join(timeout=4)
                if self._worker.is_alive():self.fail('video worker shutdown unconfirmed')
            self.log({'type':'end','frames':self.frames,'failures':self.failures,
                      'ended_host_ns':time.monotonic_ns()})
            self._journal.close()
            self._journal=None
        result={'schema':'car-video-only-summary/v1','identity':self.identity,
                'hardware':self.hardware,'uart_opened':False,'control_available':False,
                'joint_acceptance_validated':False,'motion_allowed':False,
                'duration_requested_s':duration_s,'duration_observed_s':time.monotonic()-started,
                'frames':self.frames,'video':self.hub.stats(),'failures':list(self.failures),
                'resources_closed':self.pipeline_safe and self.video_shutdown_confirmed and (self._worker is None or not self._worker.is_alive()),
                'passed':not self.failures and self.frames>0}
        write_new_json(self.output_dir/'video_summary.json', result)
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit',type=Path,default=HERE/'task7_8_LAB_ONLY.bit')
    parser.add_argument('--hwh',type=Path,default=HERE/'task7_8_LAB_ONLY.hwh')
    parser.add_argument('--manifest',type=Path,default=HERE/'lab_manifest.json')
    parser.add_argument('--native',type=Path,default=HERE/'native-build/libcar_video.so')
    parser.add_argument('--camera-device',default='/dev/video0');parser.add_argument('--port',default='/dev/ttyPS1')
    parser.add_argument('--bind',default='0.0.0.0');parser.add_argument('--web-port',type=int,default=8080)
    parser.add_argument('--duration',type=float,default=1800)
    parser.add_argument('--video-mode',choices=['auto','manual','fixed'],default='auto')
    parser.add_argument('--fps',type=int,default=30)
    parser.add_argument('--quality',type=int,default=85)
    parser.add_argument('--jpeg-profile',choices=['balanced','balanced_fast','detail','legacy'],default='balanced')
    parser.add_argument('--decode-dct',choices=['islow','ifast'],default='islow')
    parser.add_argument('--reuse-decoder',action='store_true')
    parser.add_argument('--calibration',type=Path,help='existing versioned wheel calibration JSON')
    parser.add_argument('--display-model',type=Path,help='measured PWM/speed model for display estimates only')
    parser.add_argument('--display-stationary',action='store_true',help='explicit stationary display assumption; requires disconnected motors')
    parser.add_argument('--motor-disconnected',action='store_true')
    parser.add_argument('--video-only',action='store_true',help='video and PL display only; no UART, control, or calibration')
    parser.add_argument('--headless',action='store_true',help='run without browser server or network address discovery')
    parser.add_argument('--evidence-dir',type=Path,default=HERE/'evidence/wireless')
    args=parser.parse_args(argv)
    if not args.video_only and not args.motor_disconnected:parser.error('first candidate requires --motor-disconnected')
    if args.video_only and args.calibration:parser.error('video-only sessions cannot apply calibration')
    if args.display_stationary and not args.motor_disconnected:parser.error('stationary display requires --motor-disconnected')
    if not math.isfinite(args.duration) or args.duration<=0:parser.error('positive finite duration required')
    if not 0<=args.web_port<=65535:parser.error('web port must be 0..65535')
    hub=VideoHub()
    try:hub.policy.configure({'mode':args.video_mode,'fps':args.fps,'quality':args.quality})
    except ValueError as exc:parser.error(str(exc))
    calibration=CalibrationConfig.load(args.calibration) if args.calibration else None
    display_model=MeasuredDriveModel.load(args.display_model) if args.display_model else None
    verify_package(args.bit,args.hwh,args.manifest);hashes=verify_wireless(args.manifest,args.hwh)
    evidence_session=EvidenceSession(args.evidence_dir)
    native=NativeLibrary(args.native)
    with DeviceLease(), ExitStack() as cleanup:
        overlay=open_verified_overlay(args.bit,args.hwh);validate_ip_dict(overlay.ip_dict)
        client=PerceptionClient(PynqMMIO(CONTROL_BASE,CONTROL_LENGTH));client.verify_contract()
        if calibration:calibration.apply(client,motor_disconnected=True)
        elif args.motor_disconnected and not (client.io.read32(reg.QEI0_SCALE) or client.io.read32(reg.QEI1_SCALE)):
            client.configure_qei_filters(BENCH_FILTER_TICKS,BENCH_FILTER_TICKS,motor_disconnected=True)
        link=None
        if not args.video_only:
            from pynq_link import HybridCarLink
            link=HybridCarLink(args.port)
            cleanup.callback(link.close)
            try:
                client.attach_sensor_link(link)
                link.start()
                startup=wait_for_acquisition(client)
            except Exception:
                link.close()
                raise
        else:
            client.io.write32(reg.EXT_SENSOR_MODE,1)
            startup={'scope':'video_only','control_readiness_tested':False}
        identity=session_identity(args.bit,args.hwh,args.manifest,calibration.payload() if calibration else {'source':'live registers; physical calibration pending'})
        identity.update(wireless_sources=hashes,native_binary_sha256=hashlib.sha256(args.native.read_bytes()).hexdigest(),
                        native_version=native.lib.wv_version().decode(),video_profile='wireless720')
        identity['sensor_source']='stm32_uart_v3'
        mailbox=IntentMailbox()
        runner_class=VideoOnlyRunner if args.video_only else WirelessRunner
        runner=runner_class(client,link,video=WirelessBoardVideo(overlay),source=Camera(native,args.camera_device),
              native=native,hub=hub,jpeg_profile=args.jpeg_profile,decode_dct=args.decode_dct,reuse_decoder=args.reuse_decoder,
              intent_mailbox=mailbox,output_dir=args.evidence_dir,identity=identity,hardware=True,
              display_model=display_model,display_stationary=args.display_stationary,evidence_session=evidence_session)
        write_new_json(args.evidence_dir/'startup_readiness.json', startup)
        invoked=False
        try:
            with nullcontext(None) if args.headless else WirelessServer(runner,hub,mailbox,args.bind,args.web_port) as server:
                if server is not None:
                    import socket
                    try:
                        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
                            probe.connect(('192.168.8.1',9));address=probe.getsockname()[0]
                    except OSError as exc:
                        print(f'网络地址暂不可用：{exc}；视频继续运行，浏览器服务端口 {server.port}',flush=True)
                    else:
                        print(f'浏览器入口：http://{address}:{server.port}/#token={server.token}',flush=True)
                invoked=True;summary=runner.run(args.duration)
        finally:
            if not invoked and link is not None:link.close()
        summary['wireless_video']=hub.stats()
        summary['hardware_performance_validated']=False
        write_new_json(args.evidence_dir/'wireless_summary.json', summary)
        return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
