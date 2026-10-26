"""Switch the shared service to the limited trial candidate, initially locked."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import urllib.request

from car_network_probe import ROOT, connect_board, wifi, join_car, cmd, clean
from car_deploy_console import run, py
from package_trial_console import NAME, BASE

OUT = ROOT/'work/ground_trial_20261026'
REMOTE = '/home/xilinx/'+NAME
FACTS = {'started_local':datetime.now().isoformat(), 'mode':'controlled-trial',
         'operator_confirmed':'ground trial; surrounding area cleared',
         'release_commands_sent_by_deployer':False, 'nonzero_commands_sent_by_deployer':False}


def require(result):
    if result['code']:
        raise RuntimeError(clean(result['stderr']+result['stdout'])[-2500:])
    return result['stdout']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = wifi()
    original = re.search(r'^\s*Profile\s*:\s*(.+)$', before, re.M).group(1).strip()
    FACTS['original_profile'] = original
    client = None
    changed = False
    try:
        join_car(progress=lambda value:print(value, flush=True))
        client = connect_board('192.168.8.139')
        FACTS['verified_host_key'] = True
        data = (ROOT/'pynq_fpga/release'/NAME).with_suffix('.zip').read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        target = '/home/xilinx/.console-deploy/'+NAME+'.zip'
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(20)
        try:
            with sftp.open(target, 'wb') as stream:
                stream.write(data)
        finally:
            sftp.close()
        source = f'''from pathlib import Path
import hashlib,zipfile
archive=Path({target!r});assert hashlib.sha256(archive.read_bytes()).hexdigest()=={digest!r}
folder=Path({REMOTE!r});assert not folder.exists(), 'immutable candidate already deployed'
with zipfile.ZipFile(archive) as z:
 assert all(not n.startswith('/') and '..' not in Path(n).parts and '\\\\' not in n for n in z.namelist())
 z.extractall(folder)
print('TRIAL_FILES_STAGED')
'''
        print(require(py(client, source, timeout=30)).strip(), flush=True)
        FACTS['package_sha256'] = digest
        require(run(client, 'cd '+shlex.quote(REMOTE)+' && XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 -c '+shlex.quote('from pathlib import Path;from trial_runtime import verify_trial;verify_trial(Path.cwd());print("TRIAL_IDENTITY_VERIFIED")'), timeout=30))
        unit = f'''[Unit]
Description=PYNQ car limited ground trial (manual release, PWM400, 1s)
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory={REMOTE}
Environment=XILINX_XRT=/usr
Environment=SENSOR_CONSOLE_DURATION=1800
ExecStart=/bin/sh {REMOTE}/start_trial_console.sh
Restart=no
KillSignal=SIGINT
TimeoutStopSec=8
[Install]
WantedBy=multi-user.target
'''
        changed = True
        setup = f'''from pathlib import Path
import subprocess
p=Path('/etc/systemd/system/pynq-car-console.service')
backup=Path(str(p)+'.before-ground-trial-r13')
if not backup.exists():backup.write_bytes(p.read_bytes())
subprocess.run(['systemctl','stop','pynq-car-console.service'],check=True)
p.write_text({unit!r})
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','start','pynq-car-console.service'],check=True)
print('TRIAL_SERVICE_STARTED_LOCKED')
'''
        print(require(py(client, setup, root=True, timeout=30)).strip(), flush=True)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic()+60
        state = None
        token = None
        while time.monotonic() < deadline:
            invocation = require(run(client, 'systemctl show pynq-car-console.service -p InvocationID --value')).strip()
            log = require(run(client, 'journalctl _SYSTEMD_INVOCATION_ID='+invocation+' -n 50 --no-pager -o cat', root=True))
            matches = re.findall(r'http://[^\s]+/#token=([\w-]+)', log)
            if matches:
                token = matches[-1]
                request = urllib.request.Request('http://192.168.8.139:8080/api/status', headers={'Authorization':'Bearer '+token})
                try:
                    with opener.open(request, timeout=3) as response:
                        state = json.load(response)
                    if state.get('telemetry_fresh') and state.get('latest', {}).get('stm32_link', {}).get('link_fresh'):
                        break
                except OSError:
                    pass
            active = require(run(client, 'systemctl is-active pynq-car-console.service || true')).strip()
            if active in ('inactive', 'failed'):
                raise RuntimeError('trial service exited: '+clean(log)[-2500:])
            time.sleep(.5)
        if not state or not state.get('telemetry_fresh') or not state.get('latest', {}).get('stm32_link', {}).get('link_fresh'):
            raise RuntimeError('no fresh trial telemetry or STM32 reply before deadline')
        car = state['latest']['control']['car']
        if not car or car['lock'] != 1 or car['left'] or car['right']:
            raise RuntimeError('initial actual locked-zero confirmation failed')
        FACTS['initial_status'] = state
        (OUT/'active-session.json').write_text(json.dumps({'url':'http://192.168.8.139:8080/#token='+token}), 'utf8')
        # Read-only browser verification: no claim, release or motion is sent.
        tested = subprocess.run(['node', str(ROOT/'tools/verify_trial_live.js')], cwd=ROOT, capture_output=True, text=True, encoding='utf8', timeout=40)
        FACTS['browser_check'] = {'code':tested.returncode, 'stdout':clean(tested.stdout), 'stderr':clean(tested.stderr)}
        if tested.returncode:
            raise RuntimeError('trial browser check failed: '+clean(tested.stderr)[-1200:])
        observed = []
        for _ in range(80):
            with opener.open(request, timeout=3) as response:
                current = json.load(response)
            actual = current.get('latest', {}).get('control', {}).get('car')
            if not current.get('telemetry_fresh') or not actual or actual['lock'] != 1 or actual['left'] or actual['right']:
                raise RuntimeError('locked-zero trial observation failed')
            observed.append(current)
            time.sleep(.1)
        FACTS['read_only_observation'] = {
            'samples':len(observed),
            'ir_invalid_samples':sum(not s['latest']['stm32_link'].get('sensor', {}).get('ir_valid', False) for s in observed),
            'max_ir_age_ms':max(s['latest']['stm32_link']['sensor']['ir_age_ms'] for s in observed),
            'max_reply_latency_ms':max(s['latest']['stm32_link']['last_reply_latency_ms'] for s in observed),
            'operator_faults':[s['latest']['operator_error'] for s in observed if s['latest']['operator_error']],
            'actual_locked_zero_all':True}
        state = observed[-1]
        FACTS['final_status'] = state
        FACTS['switched'] = True
        print(json.dumps({'switched':True, 'mode':state['mode'], 'actual_lock':car['lock'], 'actual_pwm':[car['left'],car['right']], 'scales':state['latest']['scales'], 'ir':car['ir'], 'blockers':state['latest']['blockers']}, ensure_ascii=False), flush=True)
    except Exception as exc:
        FACTS['error'] = clean(str(exc))
        if changed and client:
            rollback = '''from pathlib import Path
import subprocess
p=Path('/etc/systemd/system/pynq-car-console.service');b=Path(str(p)+'.before-ground-trial-r13')
subprocess.run(['systemctl','stop','pynq-car-console.service'])
if b.exists():
 p.write_bytes(b.read_bytes())
 subprocess.run(['systemctl','daemon-reload'],check=True)
 subprocess.run(['systemctl','start','pynq-car-console.service'],check=True)
print('RESTORED_PREVIOUS_ZERO_OUTPUT_SERVICE')
'''
            FACTS['rollback'] = py(client, rollback, root=True, timeout=30)
        raise
    finally:
        if client:
            client.close()
        FACTS['wifi_restore'] = cmd(['netsh','wlan','connect','name='+original,'interface=WLAN 2'])
        (OUT/'deployment.json').write_text(json.dumps(FACTS, ensure_ascii=False, indent=2), 'utf8')


if __name__ == '__main__':
    main()
