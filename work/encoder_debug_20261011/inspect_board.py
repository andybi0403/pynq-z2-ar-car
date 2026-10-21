import glob
import hashlib
import json
import os
import subprocess
from pathlib import Path

def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None

facts = {'scope': 'read-only inspection; no FPGA reload, no motor commands'}
facts['hostname'] = read('/etc/hostname')
facts['uptime'] = read('/proc/uptime')
facts['loadavg'] = read('/proc/loadavg')
facts['network'] = subprocess.run(['ip', '-j', 'address'], capture_output=True, text=True).stdout
facts['routes'] = subprocess.run(['ip', '-j', 'route'], capture_output=True, text=True).stdout
facts['eth0_carrier'] = read('/sys/class/net/eth0/carrier')
facts['thermal'] = [{ 'path': p, 'type': read(p+'/type'), 'temp': read(p+'/temp') }
                    for p in glob.glob('/sys/class/thermal/thermal_zone*')]
facts['iio'] = [{ 'path': p, 'name': read(p+'/name'),
    'temp_raw': read(p+'/in_temp0_raw'), 'temp_offset': read(p+'/in_temp0_offset'),
    'temp_scale': read(p+'/in_temp0_scale') }
    for p in glob.glob('/sys/bus/iio/devices/iio:device*')]
facts['packages'] = []
for p in glob.glob('/home/xilinx/task7_8_lab_only*'):
    candidate = Path(p)
    manifest = candidate/'lab_manifest.json'
    row = {'path': p, 'manifest_exists': manifest.exists()}
    if manifest.exists():
        row['manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    for name in ('task7_8_LAB_ONLY.bit', 'task7_8_LAB_ONLY.hwh', 'lab_acceptance.py', 'overlay_session.py'):
        file = candidate/name
        if file.exists():
            row[name+'_sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
    facts['packages'].append(row)
facts['runtime_processes'] = []
for p in glob.glob('/proc/[0-9]*/cmdline'):
    try:
        args = Path(p).read_bytes().decode(errors='replace').split('\0')
        scripts = [a for a in args if a.endswith('.py') and ('runtime' in a or 'acceptance' in a or 'video' in a)]
        if scripts:
            facts['runtime_processes'].append({'pid': p.split('/')[2], 'scripts': scripts,
                'cwd': os.readlink(str(Path(p).parent/'cwd'))})
    except OSError:
        pass
print(json.dumps(facts, ensure_ascii=True))
