import base64
import zlib
from pathlib import Path
source = Path('work/encoder_debug_20261011/monitor.py').read_bytes()
encoded = base64.b64encode(zlib.compress(source, 9)).decode()
bootstrap = '''import base64, json, os, subprocess, zlib
from pathlib import Path
session = Path('/home/xilinx/encoder_debug_20261011/session01')
session.mkdir(parents=True, exist_ok=False)
script = session/'monitor.py'
script.write_bytes(zlib.decompress(base64.b64decode(ENCODED)))
env = os.environ.copy()
env['XILINX_XRT'] = '/usr'
env['PYTHONDONTWRITEBYTECODE'] = '1'
with (session/'monitor.log').open('wb') as log:
    child = subprocess.Popen(['timeout', '-s', 'INT', '-k', '10', '630s', '/usr/local/share/pynq-venv/bin/python3', str(script)], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
print(json.dumps({'monitor_pid': child.pid, 'session': str(session), 'maximum_seconds': 630}))
'''.replace('ENCODED', repr(encoded))
Path('work/encoder_debug_20261011/start_monitor.py').write_text(bootstrap, 'utf8')
