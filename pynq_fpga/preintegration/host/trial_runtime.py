"""Limited ground-trial entry point; starts locked, without video workload."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
if not (HERE/'perception_client.py').exists():
    sys.path.insert(0, str(HERE.parents[1]/'host'))
    sys.path.insert(0, str(HERE.parents[2]/'stm32预备程序/pc'))

from overlay_session import DeviceLease, open_verified_overlay
from board_runtime import validate_ip_dict
from lab_acceptance import verify_package, CONTROL_BASE, CONTROL_LENGTH
from perception_client import PerceptionClient, PynqMMIO
from control_supervisor import ControlSupervisor
from pynq_link import HybridCarLink
from wireless_runtime import verify_wireless
from wireless_core import VideoHub
from wireless_server import WirelessServer
from trial_control import TrialMailbox, TrialGate, TrialOwner, PWM_LIMIT, MAX_BURST_S
import car_regs as reg


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_trial(folder):
    manifest = json.loads((folder/'trial_manifest.json').read_text('utf8'))
    if manifest.get('schema') != 'car-ground-trial/v1' or manifest.get('limits') != {
            'pwm':400, 'burst_s':1.0, 'intent_lease_ms':250, 'scheduling_fault_ms':100}:
        raise ValueError('trial schema or safety limits mismatch')
    if manifest.get('classification') != 'CONTROLLED_TRIAL_CANDIDATE_NOT_RELEASE':
        raise ValueError('explicit trial candidate required')
    if manifest.get('base_manifest_sha256') != digest(folder/'lab_manifest.json'):
        raise ValueError('trial base identity mismatch')
    if set(manifest.get('files', {})) != {'trial_control.py', 'trial_runtime.py', 'trial_page.html', 'start_trial_console.sh'}:
        raise ValueError('trial source inventory mismatch')
    for name, value in manifest['files'].items():
        if digest(folder/name) != value or digest(HERE/name) != value:
            raise ValueError('trial source mismatch: '+name)
    verify_package(folder/'task7_8_LAB_ONLY.bit', folder/'task7_8_LAB_ONLY.hwh', folder/'lab_manifest.json')
    verify_wireless(folder/'lab_manifest.json', folder/'task7_8_LAB_ONLY.hwh')
    return manifest


class TrialRunner:
    control_available = True

    def __init__(self, client, link, mailbox, output):
        self.client, self.link, self.output_dir = client, link, output
        self.control = ControlSupervisor(client, link, motion_allowed=True, yellow_pwm_limit=PWM_LIMIT)
        self.owner = TrialOwner(self.control, mailbox)
        self.lock = threading.Lock()
        self.latest = None
        self.updated = None
        self.running = True
        self.samples = 0

    def enqueue_action(self, kind, value=None):
        raise ValueError('试跑中不能修改标定；停车按钮通过控制邮箱执行')

    def step(self, lag_s):
        ticks, shot, decision = self.owner.step(lag_s)
        scales = [self.client.io.read32(reg.QEI0_SCALE), self.client.io.read32(reg.QEI1_SCALE)]
        blockers = list(decision['decision_reasons'])
        if not all(scales):
            blockers.append('双轮编码器尚未实测标定（SCALE=0）')
        if not decision['car_fresh']:
            blockers.append('STM32 回包缺失或过期')
        car = decision['car']
        if car and car.get('ir', 3):
            blockers.append('STM32 红外仍报告障碍：IR='+str(car['ir']))
        if car and car.get('mm', 0) < 250:
            blockers.append('距离不足 250mm')
        if self.owner.fault:
            blockers.append(self.owner.fault)
        state = {'control': decision, 'scales': scales, 'blockers': blockers,
                 'encoder_counts': [shot.qei0_position, shot.qei1_position],
                 'raw_velocity_q16': [shot.qei0_velocity_q16, shot.qei1_velocity_q16],
                 'stm32_link': self.link.diagnostics(), 'operator_error': self.owner.error,
                 'epoch': shot.epoch, 'host_monotonic_s': time.monotonic()}
        with self.lock:
            self.latest, self.updated = state, time.monotonic()
            self.samples += 1
        return state

    def status_snapshot(self):
        with self.lock:
            fresh = self.updated is not None and time.monotonic()-self.updated < .200
            state = self.latest
            c = state['control'] if state else {}
            return {'mode': 'controlled-trial', 'running': self.running, 'hardware': True,
                    'trial_requested': True, 'motion_ready': bool(self.running and fresh and not self.owner.fault and c.get('phase') == 'ARMED'),
                    'release_ready': bool(self.running and fresh and not self.owner.fault and c.get('safe_hold')),
                    'telemetry_fresh': fresh, 'latest': state, 'samples': self.samples,
                    'pwm_limit': PWM_LIMIT, 'max_burst_s': MAX_BURST_S,
                    'video_enabled': False, 'control_available': True}


class TrialServer(WirelessServer):
    def __init__(self, runner, mailbox, port):
        super().__init__(runner, VideoHub(), mailbox, port=port)
        self.gate = TrialGate(mailbox)
        self.page_text = (HERE/'trial_page.html').read_text('utf8')

    async def session(self, request):
        response = await super().session(request)
        # Base authentication stays intact; capability differs from readiness.
        response.text = json.dumps({'authenticated': True, 'mode': 'controlled-trial', 'motion_ready': False})
        return response


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ground-trial', action='store_true')
    p.add_argument('--duration', type=float, default=1800)
    p.add_argument('--web-port', type=int, default=8080)
    args = p.parse_args(argv)
    if not args.ground_trial:
        p.error('explicit --ground-trial required')
    if not 0 < args.duration <= 1800:
        p.error('duration must be 0..1800 seconds')
    identity = verify_trial(HERE)
    output = HERE/'evidence'/time.strftime('ground_trial_%Y%m%dT%H%M%S')
    output.mkdir(parents=True, exist_ok=False)
    done = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: done.set())
    with DeviceLease():
        overlay = open_verified_overlay(HERE/'task7_8_LAB_ONLY.bit', HERE/'task7_8_LAB_ONLY.hwh')
        validate_ip_dict(overlay.ip_dict)
        client = PerceptionClient(PynqMMIO(CONTROL_BASE, CONTROL_LENGTH))
        client.verify_contract()
        link = HybridCarLink('/dev/ttyPS1', locked_diagnostic=False)
        # The base link reads up to 256 bytes with a 50ms timeout. S1 is
        # shorter, so every read waits out that timeout and adds avoidable age.
        # A bounded 5ms read preserves framing and the original 100ms IR guard.
        link.ser.timeout = .005
        runner = None
        try:
            client.attach_sensor_link(link)
            link.start()
            mailbox = TrialMailbox()
            runner = TrialRunner(client, link, mailbox, output)
            runner.control.stop()
            (output/'identity.json').write_text(json.dumps(identity, indent=2), 'utf8')
            with TrialServer(runner, mailbox, args.web_port) as server, (output/'joint.jsonl').open('x') as journal:
                print('浏览器入口：http://192.168.8.139:'+str(server.port)+'/#token='+server.token, flush=True)
                print('受限地面试跑；启动锁车；PWM≤400；单次≤1秒；视频暂停', flush=True)
                started = time.monotonic()
                due = started
                previous = None
                while not done.is_set() and time.monotonic()-started < args.duration:
                    now = time.monotonic()
                    lag = max(0, now-due, 0 if previous is None else now-previous-.050)
                    previous = now
                    state = runner.step(lag)
                    journal.write(json.dumps(state, ensure_ascii=False)+'\n')
                    if runner.samples % 20 == 0:
                        journal.flush()
                    due += .050
                    now = time.monotonic()
                    if now > due:
                        due = now
                    done.wait(max(0, due-time.monotonic()))
        finally:
            if runner is not None:
                runner.running = False
                runner.control.stop()
            else:
                link.stop_request()
            link.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
