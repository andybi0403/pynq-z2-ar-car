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
from trial_control import TrialGate, TrialOwner, PWM_LIMIT
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
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.console_mode='observe'
        self.console_actions=queue.Queue(maxsize=4)
        self.drive_owner=TrialOwner(self.control,self.intent_mailbox)
        self.release_requests=0
        self.calibration_measured=self.identity.get('calibration',{}).get('measured') is True
        self.console_scales=[0,0]
        self.release_ready=False
        self.console_action=None
        self.observation_stop_started=None
        self.console_qei_config=None
        self.serial_audit=AuditedSerial(self.link.ser) if hasattr(self.link,'ser') else None
        if self.serial_audit is not None:self.link.ser=self.serial_audit

    def release_was_sent(self):
        return bool(self.serial_audit and self.serial_audit.release_tx)

    def session_motion_capable(self):
        return True

    def enqueue_action(self,kind,payload=None):
        if self.stop_event.is_set() or self._journal is None:raise RuntimeError('session is not running')
        if kind not in ('mode','motor-state'):
            if kind=='calibration' and self.console_mode!='observe':
                raise ValueError('请先切回仅观察模式并停车')
            if kind=='calibration':
                if not isinstance(payload,dict) or payload.get('measured') is not True:
                    raise ValueError('完整控制台只接受有实物测量来源的标定')
                self.console_action=None
            return super().enqueue_action(kind,payload)
        if not isinstance(payload,dict):raise ValueError('需要有效的操作参数')
        if kind=='mode' and payload.get('mode') not in ('observe','manual'):
            raise ValueError('请选择仅观察或手动驾驶')
        if kind=='mode' and payload.get('mode')=='observe':self.intent_mailbox.stop()
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
                observe=action['kind']=='mode' and action['payload']['mode']=='observe'
                if not observe and (not last.get('car_fresh') or not car or car['lock']!=1 or car['left'] or car['right']):
                    raise ValueError('需要 STM32 新鲜的锁车、双轮零输出反馈')
                if action['kind']=='motor-state':
                    if self.console_mode!='observe':raise ValueError('请先切回仅观察模式')
                    self.motor_disconnected=action['payload']['disconnected']
                else:
                    mode=action['payload']['mode']
                    if mode=='manual':
                        if self.motor_disconnected:raise ValueError('当前记录为动力已断开；接入动力后据实更新连接状态')
                        if not self.calibration_measured or not all(self.console_scales):
                            raise ValueError('需要先完成双轮实测标定并读回验证')
                        if self.drive_owner.fault:raise ValueError(self.drive_owner.fault)
                    self.console_mode=mode
                    self.control.motion_allowed=mode=='manual'
                    if mode=='observe':self.observation_stop_started=time.monotonic()
                self.console_action={**action,'applied':True}
            except (ValueError,PermissionError) as exc:
                self.console_action={**action,'applied':False,'error':str(exc)}
            self.log({'type':'console_action',**self.console_action})
        old_phase=self.control._phase
        # LAB owner semantics remain unchanged in observation mode. Explicit
        # release packets are rejected and can never silently change mode.
        if self.console_mode=='manual':
            result=self.drive_owner.step()
        else:
            kind,value=self.intent_mailbox.consume()
            if kind=='stop':self.control.stop()
            elif kind=='intent':
                try:self.control.submit_intent(*value)
                except (PermissionError,ValueError) as exc:
                    self.control.stop();self.drive_owner.error=str(exc)
            elif kind=='release':
                self.control.stop();self.drive_owner.error='请先切换到手动驾驶模式'
            result=self.control.tick()
        if old_phase!='WAIT_UNLOCK' and self.control._phase=='WAIT_UNLOCK':self.release_requests+=1
        self.console_scales=[self.client.io.read32(reg.QEI0_SCALE),self.client.io.read32(reg.QEI1_SCALE)]
        self.console_qei_config=[{key:self.client.io.read32(getattr(reg,f'QEI{i}_{key.upper()}')) for key in ('dir','filter','zero')} for i in (0,1)]
        if self.action_status and self.action_status.get('kind')=='calibration' and self.action_status.get('applied'):
            self.calibration_measured=self.identity.get('calibration',{}).get('measured') is True
        last=self.control.last or {}
        safe_since=self.control._safe_since
        self.release_ready=bool(self.console_mode=='manual' and last.get('safe_hold') and safe_since is not None and time.monotonic()-safe_since>=self.control.SAFE_HOLD_S and not self.drive_owner.fault)
        return result

    def validate_actual_output(self,car):
        if car and any(abs(car[k])>PWM_LIMIT for k in ('left','right')):
            self.control.stop()
            raise RuntimeError('STM32 actual PWM exceeds console limit')
        if self.console_mode!='manual':
            if self.observation_stop_started is not None and time.monotonic()-self.observation_stop_started<.300:
                if car and (car['left'] or car['right']):self.control.stop()
                return
            super().validate_actual_output(car)

    def handle_schedule_overrun(self,lag_s):
        if self.console_mode!='manual':return super().handle_schedule_overrun(lag_s)
        self.drive_owner.fault='驾驶控制调度超时，已锁停；检查负载后重新启动服务'
        self.drive_owner.stop(self.drive_owner.fault)
        self.release_ready=False
        with self._state_lock:
            self.schedule_overruns+=1
            self.schedule_max_lag_ms=max(self.schedule_max_lag_ms,lag_s*1000)
            if self.drive_owner.fault not in self.failures:self.failures.append(self.drive_owner.fault)
        self.log({'type':'console_timing_fault','lag_ms':lag_s*1000,'action':'latched_stop'})

    def status_snapshot(self):
        result=super().status_snapshot()
        fresh=result['telemetry_fresh'] and result['running']
        control=(result.get('latest') or {}).get('control',{})
        blockers=[]
        if not self.calibration_measured or not all(self.console_scales):blockers.append('双轮尚未完成实测标定')
        if self.motor_disconnected:blockers.append('电机动力当前记录为已断开')
        if self.console_mode!='manual':blockers.append('当前为仅观察模式')
        if self.drive_owner.fault:blockers.append(self.drive_owner.fault)
        result.update(console={'mode':self.console_mode,'motion_supported':True,
            'infrared_policy':'warning_only',
            'motion_ready':bool(fresh and control.get('phase')=='ARMED' and not self.drive_owner.fault),
            'release_ready':bool(fresh and self.release_ready),'pwm_limit':PWM_LIMIT,'max_burst_s':1,
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
        self.gate.revoke('console_mode_or_physical_state_change')
        try:return web.json_response(self.runner.enqueue_action(request.match_info['action'],await request.json()),status=202)
        except (ValueError,TypeError,RuntimeError,queue.Full) as exc:raise web.HTTPBadRequest(text=str(exc))

    async def session(self,request):
        response=await super().session(request)
        response.text=json.dumps({'authenticated':True,'motion_allowed':self.runner.control.motion_allowed,'console':True})
        return response

    def application(self):
        app=super().application()
        app.router.add_post('/api/console/{action:mode|motor-state}',self.console_action)
        return app
