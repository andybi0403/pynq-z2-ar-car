"""Bounded, logged checks of the PYNQ debug console. No motion commands."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'deps'))
import argparse
from datetime import datetime, timezone, timedelta
import json
import re
import time
import serial
from serial.tools import list_ports

HERE = Path(__file__).resolve().parent

def clean(text):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'(?i)(#token=|Bearer\s+)[\w.-]+', r'\1[REDACTED]', text)
    return text

def read_for(port, seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(8192))
    return bytes(data)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM10')
    args = parser.parse_args()
    ports = list(list_ports.comports())
    inventory = [dict(device=p.device, description=p.description, vid=p.vid, pid=p.pid, serial=p.serial_number) for p in ports]
    matching = [p for p in ports if p.device == args.port and (p.vid, p.pid) == (0x0403, 0x6010)]
    if len(matching) != 1:
        raise RuntimeError('Specified port is not the expected PYNQ FTDI interface: ' + repr(inventory))
    port = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=2)
    port.port = args.port
    port.dtr = False
    port.rts = False
    try:
        port.open()
        raw = read_for(port, 2)
        port.write(b'\r')
        port.flush()
        raw += read_for(port, 3)
    finally:
        port.close()
    output = clean(raw.decode('utf8', 'replace').replace('\r\n', '\n'))
    result = dict(time=datetime.now(timezone(timedelta(hours=8))).isoformat(), port=args.port,
                  baudrate=115200, inventory=inventory, sent='one carriage return',
                  console=output, motion_commands_sent=False)
    path = HERE / ('console-peek-' + datetime.now().strftime('%H%M%S') + '.json')
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=True, indent=2))
    print('EVIDENCE', str(path).encode('ascii', 'backslashreplace').decode())

if __name__ == '__main__':
    main()
