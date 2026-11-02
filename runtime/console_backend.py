"""Integrated console policy and API. Web handlers never touch MMIO/UART."""
import hashlib
import json
from pathlib import Path
import queue
import threading
import time
from aiohttp import web

from wireless_runtime import WirelessRunner
from wireless_server import WirelessServer
from system_runtime import JointRunner
from trial_control import TrialGate, TrialOwner, DirectManualControl, PWM_LIMIT, MAX_BURST_S, DRIVE_LEASE_MS
import car_regs as reg


class AuditedSerial:
    """Count completed UART writes; requested release is not a sent release."""
    def __init__(self,serial):
        self.serial=serial;self.lock=threading.Lock();self.release_tx=0
    def __getattr__(self,name):return getattr(self.serial,name)
    def write(self,data):
        written=self.serial.write(data)
        if written==len(data) and data.startswith(b'$R1,'):
            with self.lock:self.release_tx+=1
        return written


def verify_console(folder, base_manifest):
    value=json.loads((folder/'console_manifest.json').read_text('utf8'))
    if value.get('schema')!='car-integrated-console/v1' or value.get('classification')!='CONTROLLED_CONSOLE_NOT_RELEASE':
        raise ValueError('integrated console manifest required')
    if value.get('base_manifest_sha256')!=hashlib.sha256(base_manifest.read_bytes()).hexdigest():
        raise ValueError('console/base identity mismatch')
    required={'console_backend.py','console_ui.js','trial_control.py','start_console.sh'}
    if set(value.get('files',{}))!=required:raise ValueError('console inventory mismatch')
    for name,digest in value['files'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('console file identity mismatch: '+name)
    return value


class ConsoleRunner(WirelessRunner):
    allow_unbounded_session=True
    def create_control(self,client,link):
        return DirectManualControl(link,motion_allowed=not self.motor_disconnected)

    def _direct_loop(self):
        try:
            while not self.stop_event.is_set():
                if self._journal is not None:
                    phase=self.control._phase
                    self.drive_owner.step()
                    if phase!='WAIT_UNLOCK' and self.control._phase=='WAIT_UNLOCK':self.release_requests+=1
                self.stop_event.wait(.020)
        except Exception as exc:
            self.drive_owner.fault='直接驾驶线程异常：'+str(exc)
            self.control.stop()
            self.fail(self.drive_owner.fault)
        finally:
            self.control.stop()

    def run(self,duration_s):
        worker=threading.Thread(target=self._direct_loop,name='direct-manual-control',daemon=True)
        worker.start()
        try:return super().run(duration_s)
        finally:
            self.stop_event.set();worker.join(timeout=1)
            self.control.stop()

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.video_required_for_control=False
        self.control.motion_allowed=not self.motor_disconnected
        self.control.LEASE_S=DRIVE_LEASE_MS/1000
        self.link.CMD_MAX_AGE=DRIVE_LEASE_MS/1000
        self.control.yellow_pwm_limit=PWM_LIMIT  # Warning colour must not reduce starting torque.
        self.schedule_jitter_count=0
        self.console_actions=queue.Queue(maxsize=4)
        self.drive_owner=TrialOwner(self.control,self.intent_mailbox)
        self.release_requests=0
        self.calibration_measured=self.identity.get('calibration',{}).get('measured') is True
        self.console_scales=[0,0]
        self.release_ready=False
        self.console_action=None
        self.console_qei_config=None
        self.serial_audit=AuditedSerial(self.link.ser) if hasattr(self.link,'ser') else None
        if self.serial_audit is not None:self.link.ser=self.serial_audit

    def release_was_sent(self):
        return bool(self.serial_audit and self.serial_audit.release_tx)

    def session_motion_capable(self):
        return True

    def enqueue_action(self,kind,payload=None):
        if self.stop_event.is_set() or self._journal is None:raise RuntimeError('session is not running')
        if kind=='calibration':raise ValueError('此演示版不使用双轮标定')
        if kind=='mode':raise ValueError('运行方式已取消，请直接接管控制并安全解锁')
        if kind!='motor-state':return super().enqueue_action(kind,payload)
        if not isinstance(payload,dict):raise ValueError('需要有效的操作参数')
        if kind=='motor-state' and (type(payload.get('disconnected')) is not bool or payload.get('confirmed') is not True):
            raise ValueError('请据实确认电机动力的物理连接状态')
        self.console_actions.put_nowait({'kind':kind,'payload':payload})
        return {'queued':True,'kind':kind}

    def control_tick(self):
        try:action=self.console_actions.get_nowait()
        except queue.Empty:action=None
        if action:
            try:
                last=self.control.last or {}
                car=last.get('car')
                self.control.stop();self.intent_mailbox.stop()
                if not last.get('car_fresh') or not car or car['lock']!=1 or car['left'] or car['right']:
                    raise ValueError('需要 STM32 新鲜的锁车、双轮零输出反馈')
                self.motor_disconnected=action['payload']['disconnected']
                self.control.motion_allowed=not self.motor_disconnected
                self.console_action={**action,'applied':True}
            except (ValueError,PermissionError) as exc:
                self.console_action={**action,'applied':False,'error':str(exc)}
            self.log({'type':'console_action',**self.console_action})
        # This thread owns MMIO/display only. It never schedules driving.
        if self.control.last is None:self.control.tick()
        state=self.control.snapshot()
        fresh=bool(state.get('intent_fresh') and time.monotonic()-state['host_monotonic_s']<.2)
        requested=state.get('requested_pwm',[0,0])
        self.client.set_command(forward=fresh and any(v>0 for v in requested),valid=fresh)
        ticks,shot,_=self.client.sample_and_decide()
        result=(ticks,shot,{**state,'pl_ticks':ticks,'epoch':shot.epoch})
        if self.action_status and self.action_status.get('kind')=='calibration' and self.action_status.get('applied'):
            self.calibration_measured=self.identity.get('calibration',{}).get('measured') is True
        self.release_ready=bool(state.get('release_ready'))
        return result

    def validate_actual_output(self,car):
        if car and any(abs(car[k])>PWM_LIMIT for k in ('left','right')):
            self.control.stop()
            raise RuntimeError('STM32 actual PWM exceeds console limit')
        if self.motor_disconnected:super().validate_actual_output(car)

    def handle_schedule_overrun(self,lag_s):
        # Telemetry/logging delay is not a drive-worker failure. The independent
        # worker, UART intent lease and STM32 timeout still stop stalled control.
        self.schedule_jitter_count+=1
        with self._state_lock:
            self.schedule_overruns+=1
            self.schedule_max_lag_ms=max(self.schedule_max_lag_ms,lag_s*1000)
        self.log({'type':'console_telemetry_jitter','lag_ms':lag_s*1000,'action':'direct_worker_unaffected'})

    def status_snapshot(self):
        result=super().status_snapshot()
        fresh=result['telemetry_fresh'] and result['running']
        control=self.control.snapshot()
        if result.get('latest') is not None:result['latest']['control']=control
        control_age=time.monotonic()-control.get('host_monotonic_s',float('-inf'))
        control_live=result['running'] and 0<=control_age<.200 and control.get('car_fresh',False)
        blockers=[]
        if self.motor_disconnected:blockers.append('电机动力当前记录为已断开')
        if self.drive_owner.fault:blockers.append(self.drive_owner.fault)
        result.update(console={'control_flow':'claim_release','control_mode':'direct_manual','drive_worker_period_ms':20,'telemetry_period_ms':self.interval_s*1000,'control_fresh':bool(control_live),'operation_mode_required':False,'motion_supported':True,
            'schedule_stop_lag_ms':None,'schedule_jitter_events':self.schedule_jitter_count+self.drive_owner.jitter_count,
            'infrared_policy':'warning_only','profile':'plain_motor_demo','mileage':'estimated','speed_display':False,'forward_stop_mm':250,
            'motion_ready':bool(control_live and not self.motor_disconnected and control.get('phase')=='ARMED' and not self.drive_owner.fault),
            'release_ready':bool(control_live and control.get('release_ready')),'pwm_limit':PWM_LIMIT,'max_burst_s':MAX_BURST_S,
            'video_required_for_control':False,'packet_max_age_ms':200,'sync_rtt_ms':200,'intent_lease_ms':DRIVE_LEASE_MS,'default_pwm':1800,
            'obstacle_policy':{'active_fpga_forward_stop_mm':250,'active_stm32_stop_mm':250,'unknown_range':'warning_only','previous_near_obstacle':'retain_until_valid_clear','requested_rule_pending_firmware':False},
            'scales':list(self.console_scales),'calibration_measured':self.calibration_measured,
            'qei_configuration':self.console_qei_config,
            'blockers':blockers,'action':self.console_action,'operator_error':self.drive_owner.error,
            'fault':self.drive_owner.fault,'release_requests':self.release_requests},
            motion_allowed=self.control.motion_allowed,classification='CONTROLLED_CONSOLE_NOT_RELEASE')
        return result


class ConsoleServer(WirelessServer):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.gate=TrialGate(self.mailbox)

    async def console_action(self,request):
        self.check(request,True)
        self.gate.revoke('console_physical_state_change')
        try:return web.json_response(self.runner.enqueue_action(request.match_info['action'],await request.json()),status=202)
        except (ValueError,TypeError,RuntimeError,queue.Full) as exc:raise web.HTTPBadRequest(text=str(exc))

    async def retired_mode(self,request):
        self.check(request,True)
        # An old tab must not switch the fixed workflow or revoke a new owner.
        raise web.HTTPGone(text='运行方式已取消，请刷新页面后直接接管控制并安全解锁')

    async def session(self,request):
        response=await super().session(request)
        response.text=json.dumps({'authenticated':True,'motion_allowed':self.runner.control.motion_allowed,'console':True})
        return response

    def application(self):
        app=super().application()
        app.router.add_post('/api/console/{action:motor-state}',self.console_action)
        app.router.add_post('/api/console/mode',self.retired_mode)
        return app
