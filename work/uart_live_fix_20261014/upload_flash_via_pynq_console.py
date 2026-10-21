"""Run guarded STM32 flashing through the verified bounded COM14 transport.

The PYNQ console must have a valid sudo timestamp. Credentials are not
embedded here. Compressed transfer avoids cat/EOF and echoed-marker races.
"""
from pathlib import Path
import base64
import hashlib
import json
import argparse
import getpass

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIRMWARE = ROOT / 'stm32_pynq对接版' / 'build_safe' / 'safe_car.bin'
from pynq_console_transport import execute

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--authenticate', action='store_true',
                    help='read the PYNQ sudo password locally without echo or storage')
args = parser.parse_args()
password = getpass.getpass('PYNQ sudo password (not stored): ') if args.authenticate else None

firmware = FIRMWARE.read_bytes()
firmware_sha = hashlib.sha256(firmware).hexdigest()
if firmware_sha != '8b043a342c839414f021bbd68700ddfac48113509577872ace9074bb806f4f2d':
    raise RuntimeError('firmware differs from tested role-fix build')
template = (OUT / 'flash_stm32_board.py').read_text(encoding='utf-8')
if template.count('FIRMWARE_B64_PLACEHOLDER') != 1:
    raise RuntimeError('expected exactly one firmware placeholder')
source = template.replace('FIRMWARE_B64_PLACEHOLDER',
                          repr(base64.b64encode(firmware).decode('ascii')))
compile(source, '<guarded-stm32-flash>', 'exec')
print('Starting current-flash check, guarded write, full readback and S1 check', flush=True)
result = execute(source, seconds=180, root=True, password=password)
result.update(kind='PYNQ_USB_CONSOLE_FLASH_TRANSPORT', hardware=True,
              firmware_sha256=firmware_sha)
(OUT / 'flash_transport.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(result['output'], flush=True)
rows = []
for line in result['output'].splitlines():
    try:
        row = json.loads(line)
    except (ValueError, TypeError):
        continue
    if isinstance(row, dict) and row.get('kind') == 'STM32_UART_ROLE_FIX_FLASH_AND_LIVE_CHECK':
        rows.append(row)
if result['returncode'] != 0 or len(rows) != 1:
    raise SystemExit(result['returncode'] or 1)
(OUT / 'flash_result.json').write_text(json.dumps(rows[0], indent=2), encoding='utf-8')
print('FLASH_AND_INITIAL_COMMUNICATION_VERIFIED', flush=True)
