"""Receive-only application startup check; never transmits or arms motors."""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import time
import serial

HERE = Path(__file__).resolve().parent
pattern = re.compile(rb'\$SAFE,MS(\d+),IR(\d+),MM(\d+),VALID([01]),LOCK([01]),FAULT(\d+),CMD(\d+),PWM(\d+),USB([01])#')
port = serial.Serial()
port.port = 'COM5'
port.baudrate = 115200
port.timeout = .2
port.dtr = False
port.rts = False
port.open()
buf = b''
raw = bytearray()
observations = []
deadline = time.monotonic() + 60
try:
    while time.monotonic() < deadline:
        chunk = port.read(256)
        raw.extend(chunk)
        buf = (buf + chunk)[-2048:]
        while b'\n' in buf:
            line, buf = buf.split(b'\n', 1)
            match = pattern.fullmatch(line.strip())
            if not match:
                continue
            values = dict(zip(('MS','IR','MM','VALID','LOCK','FAULT','CMD','PWM','USB'), map(int, match.groups())))
            if values['LOCK'] != 1 or values['CMD'] != 0:
                raise RuntimeError('Unexpected unlocked/driving startup state')
            if observations and values['MS'] <= observations[-1]['MS']:
                observations = []  # Re-establish stable startup after any reset.
            observations.append(values)
            if len(observations) >= 12 and observations[-1]['MS'] - observations[0]['MS'] >= 2500:
                break
        if len(observations) >= 12:
            break
finally:
    port.close()
    (HERE / 'application_uart_raw.bin').write_bytes(raw)

if len(observations) < 12:
    raise SystemExit('BOOT_RESET_PENDING: no stable application heartbeat yet')
record = json.loads((HERE / 'flash_record.json').read_text(encoding='utf-8'))
record.update(status='FLASH_AND_STARTUP_VERIFIED', application_startup_verified=True,
              application_verified_at_utc=datetime.now(timezone.utc).isoformat(),
              application_diagnostics=observations, application_uart_baud=115200,
              application_lock_observed=True, application_command_observed=0,
              startup_test_transmitted_bytes=0)
(HERE / 'flash_record.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print('APPLICATION_STARTUP_PASS: stable 115200 8N1 diagnostics; LOCK=1 CMD=0; no commands transmitted')
print(json.dumps({'first':observations[0],'last':observations[-1],'samples':len(observations)}, ensure_ascii=False))
