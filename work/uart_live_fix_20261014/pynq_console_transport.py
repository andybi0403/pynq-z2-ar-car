"""Bounded board jobs over its debug console, without changing PC networking."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import time
import zlib

import serial


def wifi_state():
    # Read-only: this helper deliberately has no WLAN connect/disconnect command.
    return subprocess.run(['netsh', 'wlan', 'show', 'interfaces'],
                          capture_output=True, text=True, errors='replace').stdout


def authenticate_root(uart, password):
    """Send the known board password only after sudo disables terminal echo."""
    marker = 'UART_AUTH_' + secrets.token_hex(12)
    uart.write((f"timeout 10s sudo -v -p '{marker}_PASSWORD:'; "
                f"printf '\\n{marker}_END:%s\\n' \"$?\"\n").encode())
    received = bytearray()
    supplied = False
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        received.extend(uart.read(4096))
        normalized = received.decode('utf8', 'replace').replace('\r\n', '\n')
        match = re.search(r'(?:^|\n)' + marker + r'_END:(\d+)\n', normalized)
        if match:
            if int(match[1]):
                raise RuntimeError('board sudo authentication failed')
            return
        if received.endswith((marker + '_PASSWORD:').encode()):
            if supplied:
                raise RuntimeError('board sudo rejected password; no retry')
            uart.write(password.encode() + b'\n')
            supplied = True
    raise TimeoutError('board sudo authentication did not finish within its bound')


def execute(source, *, seconds=90, root=False, password=None):
    if not 1 <= seconds <= 600:
        raise ValueError('board job timeout must be between 1 and 600 seconds')
    marker = 'UART_JOB_' + secrets.token_hex(12)
    digest = hashlib.sha256(source.encode()).hexdigest()
    encoded = base64.b64encode(zlib.compress(source.encode(), 9)).decode()
    lines = ["import base64,zlib,hashlib", "payload=("]
    lines += [repr(encoded[n:n+512]) for n in range(0, len(encoded), 512)]
    lines += [")", "body=zlib.decompress(base64.b64decode(payload))",
              f"assert hashlib.sha256(body).hexdigest()=={digest!r}",
              "exec(compile(body,'<uart-board-job>','exec'))"]
    privilege = 'sudo -n ' if root else ''
    delimiter = marker + '_SOURCE'
    command = (f"printf '\\n{marker}_BEGIN\\n'\n"
               f"{privilege}timeout -s INT -k 10 {seconds}s env XILINX_XRT=/usr "
               "PYTHONDONTWRITEBYTECODE=1 /usr/local/share/pynq-venv/bin/python3 "
               f"- <<'{delimiter}'\n" + '\n'.join(lines) +
               f"\n{delimiter}\nprintf '\\n{marker}_END:%s\\n' \"$?\"\n")
    before = wifi_state()
    uart = serial.Serial(port=None, baudrate=115200, timeout=.02, write_timeout=2)
    uart.port = 'COM14'
    uart.dtr = False
    uart.rts = False
    received = bytearray()
    try:
        uart.open()
        uart.write(b'\r')
        until = time.monotonic() + 2
        prompt = bytearray()
        while time.monotonic() < until:
            prompt.extend(uart.read(4096))
        if not re.search(rb'xilinx@pynq:[^\r\n]*\$\s*$', prompt):
            raise RuntimeError('authenticated board shell not idle; no job sent')
        # Disable echo before a large transfer; echoed payload can saturate RX.
        uart.write(b'stty -echo\n')
        echo_prompt=bytearray();echo_deadline=time.monotonic()+3
        while time.monotonic()<echo_deadline:
            echo_prompt.extend(uart.read(4096))
            if re.search(rb'xilinx@pynq:[^\r\n]*\$\s*$',echo_prompt):break
        else:raise RuntimeError('no prompt after disabling console echo')
        if root and password is not None:
            try:
                authenticate_root(uart, password)
            except Exception:
                uart.write(b'\x03'); uart.flush()
                time.sleep(.1)
                raise
        upload_started = time.monotonic()
        for line in command.splitlines():
            uart.write(line.encode() + b'\n')
            received.extend(uart.read(4096))
        # Execution wait starts after upload. The board timeout still begins
        # when Python starts; a large transfer must not consume observation time.
        started = time.monotonic()
        end = re.compile(r'(?:^|\n)' + marker + r'_END:(\d+)(?:\r?\n)')
        begin = re.compile(r'(?:^|\n)' + marker + r'_BEGIN\r?\n')
        while time.monotonic() - started < seconds + 25:
            received.extend(uart.read(4096))
            transcript = received.decode('utf8', 'replace').replace('\r\n', '\n')
            finished = end.search(transcript)
            begun = begin.search(transcript)
            if finished and begun:
                return dict(source_sha256=digest, returncode=int(finished[1]),
                            output='\n'.join(line for line in
                                transcript[begun.end():finished.start()].splitlines()
                                if '\x1b[' not in line and not
                                line.startswith('timeout -s INT -k ')).strip(),
                            elapsed_seconds=time.monotonic()-upload_started,
                            upload_seconds=started-upload_started,
                            transport='COM14 board debug UART',
                            pc_wifi_before=before, pc_wifi_after=wifi_state(),
                            pc_network_mutated=False)
        raise TimeoutError('no completion marker; board timeout remains the job bound')
    finally:
        if uart.is_open:
            uart.write(b'stty echo\n');uart.flush()
        uart.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--seconds', type=int, default=90)
    parser.add_argument('--root', action='store_true')
    args = parser.parse_args()
    if args.evidence.exists():
        raise FileExistsError(args.evidence)
    result = execute(args.source.read_text('utf8'), seconds=args.seconds, root=args.root)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({key: result[key] for key in ('returncode', 'elapsed_seconds', 'transport', 'pc_network_mutated')}))
    print(result['output'])
    raise SystemExit(result['returncode'])
