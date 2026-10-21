"""Read-only board, USB, video and serial inventory; no motor commands."""
from pathlib import Path
import json
import os
import subprocess
import time

def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8)
        return {'argv': args, 'exit_code': result.returncode,
                'stdout': result.stdout[-18000:], 'stderr': result.stderr[-3000:]}
    except Exception as exc:
        return {'argv': args, 'error': repr(exc)}

usb = []
for path in Path('/sys/bus/usb/devices').glob('*'):
    if not (path/'idVendor').exists():
        continue
    entry = {'sysfs': str(path)}
    for name in ('idVendor', 'idProduct', 'manufacturer', 'product', 'serial', 'speed'):
        if (path/name).exists():
            entry[name] = (path/name).read_text().strip()
    usb.append(entry)
video = []
for path in Path('/sys/class/video4linux').glob('*'):
    entry = {'node': '/dev/'+path.name, 'sysfs': str(path.resolve())}
    if (path/'name').exists(): entry['name'] = (path/'name').read_text().strip()
    video.append(entry)
platform = Path('/home/xilinx/stm32_sensors_platform_20261013')
files = {}
for name in ('receiver.log', 'start_hybrid.sh', 'prepare_hybrid.py'):
    path = platform/name
    if path.exists():
        files[name] = path.read_text(errors='replace')[-16000:]
result = {'kind': 'READ_ONLY_BOARD_PREFLIGHT', 'hardware': True, 'time_epoch': time.time(),
          'euid': os.geteuid(), 'usb': usb, 'video_nodes': video,
          'uart_devices': [str(p) for p in Path('/dev').glob('ttyPS*')],
          'platform_files': files,
          'commands': [command(args) for args in (
              ['uname', '-a'], ['ip', '-br', 'address'], ['lsusb'],
              ['v4l2-ctl', '--list-devices'], ['lsmod'],
              ['fuser', '/dev/video0', '/dev/ttyPS1'], ['ss', '-ltnp'],
              ['ps', '-eo', 'pid,args'], ['dmesg', '--ctime'])]}
print(json.dumps(result))
