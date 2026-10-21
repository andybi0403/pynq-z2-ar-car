"""Open the existing PYNQ browser receiver using its current session token.

This launcher opens a current session or starts the existing video-only runner.
It never unlocks actuators or changes networking. The browser connects directly
to PYNQ, without a PC proxy.
"""
from pathlib import Path
import json
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[2]
SSID = 'GL-SFT1200-0a0-5G'
DEFAULT_HOST = '192.168.8.139'
CONFIG = Path(__file__).with_name('receiver_settings.json')

# Reuse the previously verified board key and the project's existing SSH login.
sys.path.insert(0, str(ROOT / 'tmp'))
import router_session_20261007 as board_session

PROBE = r'''
from pathlib import Path
import json, re
processes=[]
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit(): continue
    try:
        args=(entry/'cmdline').read_bytes().decode().split('\0')
    except (OSError, UnicodeError): continue
    if any(Path(arg).name=='wireless_runtime.py' for arg in args):
        processes.append(args)
logs=[Path('/home/xilinx/stm32_sensors_platform_20261013/receiver.log')]
for args in processes:
    if '--evidence-dir' in args:
        index=args.index('--evidence-dir')+1
        if index<len(args):
            folder=Path(args[index])
            if folder.is_absolute(): logs.extend(folder.glob('*.log'))
for folder in (Path('/home/xilinx/stm32_sensors_platform_20261013'),
               Path('/home/xilinx/stm32_sensors_v010_20261013_r3/evidence')):
    if folder.exists():
        logs.extend(folder.glob('*.log'))
        logs.extend(folder.glob('*/*.log'))
tokens=[]
startup_error=None
try:
    tail=(Path('/home/xilinx/stm32_sensors_platform_20261013')/'receiver.log').read_text(errors='replace')[-6000:]
    errors=[line for line in tail.splitlines() if re.match(r'^(?:\w*Error|\w*Exception):',line)]
    if errors:startup_error=re.sub(r'#token=[A-Za-z0-9_-]+','#token=[redacted]',errors[-1])[:350]
except OSError:pass
if processes:
    for path in logs:
        try:
            with path.open('rb') as stream:
                stream.seek(max(0,path.stat().st_size-65536))
                content=stream.read().decode('utf8','replace')
            tokens.extend(re.findall(r'http://[A-Za-z0-9.-]+:8080/#token=([A-Za-z0-9_-]+)',content))
        except OSError: pass
print(json.dumps({'running':bool(processes),'tokens':list(dict.fromkeys(tokens))[-12:],'startup_error':startup_error}))
'''

START_VIDEO = r'''
from pathlib import Path
import datetime, fcntl, json, os, pwd, subprocess
platform=Path('/home/xilinx/stm32_sensors_platform_20261013')
script=platform/'start_hybrid.sh'
if not script.is_file(): raise RuntimeError('missing verified platform start_hybrid.sh')
guard=(platform/'receiver-launch.lock').open('a')
fcntl.flock(guard,fcntl.LOCK_EX | fcntl.LOCK_NB)
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit(): continue
    try: args=(entry/'cmdline').read_bytes().decode().split('\0')
    except (OSError,UnicodeError): continue
    if any(Path(arg).name=='wireless_runtime.py' for arg in args):
        raise RuntimeError('a wireless session is already running; retry connection')
user=pwd.getpwnam('xilinx')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
folder=platform/'receiver_sessions'/stamp
folder.mkdir(parents=True,exist_ok=False)
log_path=platform/'receiver.log'
with log_path.open('w') as log:
    os.chown(log_path,user.pw_uid,user.pw_gid)
    os.chmod(log_path,0o600)
    command=['/bin/bash',str(script),'--video-only','--duration','3600',
             '--video-mode','auto','--fps','30','--quality','85',
             '--evidence-dir',str(folder/'evidence')]
    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,
                             stderr=subprocess.STDOUT,start_new_session=True)
receipt={'pid':process.pid,'mode':'video_only','duration_s':3600,
         'motor_release_sent':False,'evidence_dir':str(folder)}
(folder/'launcher_receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
'''


def checked_url(value):
    parts = urllib.parse.urlsplit(value.strip())
    if parts.scheme != 'http' or not parts.hostname or parts.port != 8080:
        raise ValueError('请输入 PYNQ 的完整 http://地址:8080/#token=… 会话链接。')
    if parts.username or parts.password or parts.path not in ('', '/') or parts.query:
        raise ValueError('会话链接格式不正确。')
    token = urllib.parse.parse_qs(parts.fragment).get('token', [''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,120}', token):
        raise ValueError('链接缺少本次运行的会话令牌。')
    return parts, token


def verify_current(url):
    parts, token = checked_url(url)
    request = urllib.request.Request(
        f'{parts.scheme}://{parts.netloc}/api/status',
        headers={'Authorization': 'Bearer ' + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=4) as response:
        status = json.loads(response.read(262144))
    if not status.get('running'):
        raise RuntimeError('板端会话已经停止，请先启动板端接收服务。')
    return url


def open_edge(url):
    # Open the actual browser control interface, regardless of default browser.
    candidates=(Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
                Path('C:/Program Files/Microsoft/Edge/Application/msedge.exe'))
    edge=next((path for path in candidates if path.is_file()),None)
    if edge is None:
        raise RuntimeError('未找到 Microsoft Edge，请安装或修复 Edge。')
    subprocess.Popen([str(edge),'--app='+url],stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def start_video(client):
    # Password travels through SSH stdin, never through command-line arguments.
    stream, out, err = client.exec_command(
        "sudo -S -p '' python3 -c " + shlex.quote(START_VIDEO), timeout=15)
    stream.write('xilinx\n')
    stream.flush()
    stream.channel.shutdown_write()
    output = out.read().decode('utf8', 'replace')
    error = err.read().decode('utf8', 'replace')
    code = out.channel.recv_exit_status()
    if code:
        raise RuntimeError('板端视频启动失败。请检查已有运行会话、摄像头及板端启动入口。')
    return json.loads(output)


def discover_current(host):
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', host):
        raise ValueError('板卡地址只能填写 IP 或主机名。')
    board_session.HOST = host
    client = board_session.connect_board()
    try:
        result = board_session.remote(client, 'python3 -c ' + shlex.quote(PROBE), timeout=10)
        if result['exit_code']:
            raise RuntimeError('未能读取板端会话状态。')
        facts = json.loads(result['output'])
        if not facts['running']:
            start_video(client)
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                result = board_session.remote(client, 'python3 -c ' + shlex.quote(PROBE), timeout=8)
                if not result['exit_code']:
                    facts = json.loads(result['output'])
                    if facts['running'] and facts['tokens']:
                        break
                    if not facts['running'] and facts.get('startup_error'):
                        raise RuntimeError('板端程序启动失败：'+facts['startup_error'])
                time.sleep(1)
    finally:
        client.close()
    if result['exit_code']:
        raise RuntimeError('未能读取板端会话状态。')
    facts = json.loads(result['output'])
    if not facts['running']:
        raise RuntimeError('PYNQ 已连接，但视频程序没有持续运行。请检查板端启动日志；此结果尚不能判断摄像头是否连接。')
    for token in reversed(facts['tokens']):
        try:
            return verify_current(f'http://{host}:8080/#token={token}')
        except (OSError, ValueError, RuntimeError):
            pass
    raise RuntimeError('板端程序正在运行，但未找到有效会话链接。可在下方粘贴当前启动日志中的完整链接。')


def main():
    window = tk.Tk()
    window.title('PYNQ 小车控制台 · 连接')
    window.geometry('610x365')
    window.resizable(False, False)
    style = ttk.Style(window)
    style.configure('TLabel', font=('Microsoft YaHei', 10))
    style.configure('TButton', font=('Microsoft YaHei', 10))
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='PYNQ 小车 Edge 控制台', font=('Microsoft YaHei', 17, 'bold')).pack(anchor='w')
    ttk.Label(frame, text=f'电脑连接 Wi-Fi：{SSID}\n小车由充电宝供电；无需 USB 连接电脑。').pack(anchor='w', pady=(10, 14))
    ttk.Label(frame, text='默认启动现有视频测试（最长 1 小时），电机保持锁定。').pack(anchor='w', pady=(0, 10))
    saved = {}
    try:
        saved = json.loads(CONFIG.read_text('utf8'))
    except (OSError, ValueError):
        pass
    host = tk.StringVar(value=saved.get('host', DEFAULT_HOST))
    row = ttk.Frame(frame)
    row.pack(fill='x')
    ttk.Label(row, text='PYNQ 地址').pack(side='left', padx=(0, 12))
    ttk.Entry(row, textvariable=host, width=28).pack(side='left')
    status = tk.StringVar(value='正在检查当前板端会话……')
    ttk.Label(frame, textvariable=status, wraplength=565).pack(anchor='w', pady=12)
    ttk.Label(frame, text='也可粘贴本次运行的完整会话链接：').pack(anchor='w')
    manual = tk.StringVar()
    ttk.Entry(frame, textvariable=manual).pack(fill='x', pady=6)
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x', pady=6)

    def finish(url=None, error=None):
        button.configure(state='normal')
        if error:
            status.set(error)
        else:
            CONFIG.write_text(json.dumps({'host': host.get().strip()}, indent=2), 'utf8')
            status.set('已打开浏览器接收界面，可关闭此窗口。')
            open_edge(url)

    def connect():
        address = host.get().strip()
        supplied = manual.get().strip()
        button.configure(state='disabled')
        status.set('正在连接 PYNQ 并核对当前会话……')

        def work():
            try:
                url = verify_current(supplied) if supplied else discover_current(address)
            except Exception as exc:
                if isinstance(exc, OSError):
                    detail = '请确认电脑已连接小车 Wi-Fi、PYNQ 与路由器之间网线已接好。'
                else:
                    detail = str(exc)
                # Do not display URLs/tokens or credentials from transport errors.
                if type(exc).__name__ in ('SSHException', 'NoValidConnectionsError', 'TimeoutError'):
                    detail = '网络尚未连通。请连接小车 Wi-Fi，确认小车和路由器已上电，再点重试。'
                window.after(0, lambda: finish(error=detail))
            else:
                window.after(0, lambda: finish(url=url))
        threading.Thread(target=work, daemon=True).start()

    button = ttk.Button(buttons, text='连接 / 启动视频', command=connect)
    button.pack(side='left')
    ttk.Button(buttons, text='关闭', command=window.destroy).pack(side='right')
    window.after(150, connect)
    window.mainloop()


if __name__ == '__main__':
    main()
