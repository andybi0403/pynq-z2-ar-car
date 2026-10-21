"""Program the role-fix image through the STM32 ROM on the verified USART1 link.

The local uploader embeds the just-built image at the image placeholder,
streams this file through the PYNQ USB console, and captures the final JSON.
Only Q1 and PSTOP are sent after jumping to the application.
"""
from pathlib import Path
import base64
import hashlib
import json
import struct
import sys
import time

import serial

PACKAGE = Path('/home/xilinx/edge_console_v010_20261014_r2')
OUT = Path('/home/xilinx/stm32_sensors_platform_20261013/uart_live_fix_20261014')
OLD_IMAGE = PACKAGE / 'stm32_hybrid_v3.bin'
BACKUP = OUT / 'before_uart_role_fix.bin'
NEW_IMAGE = base64.b64decode(FIRMWARE_B64_PLACEHOLDER)
EXPECTED_OLD_SHA256 = '4c9406d9cd4f8c048e6d3a31eae0d6cbc7de34bcc24769373769171dc9c460b2'
EXPECTED_OLD_APP_SHA256 = 'a5bd2bc31d27539bf8003a5457933afec441cd8a24ac9928c96934ecfbc3c2e8'
EXPECTED_NEW_SHA256 = '8b043a342c839414f021bBD68700ddfac48113509577872ace9074bb806f4f2d'.lower()
FLASH_BASE = 0x08000000
FLASH_BYTES = 128 * 1024
PAGE_BYTES = 1024

sys.path.insert(0, str(PACKAGE))
from overlay_session import DeviceLease


def xor(data):
    value = 0
    for byte in data:
        value ^= byte
    return value


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def read_exact(port, size, timeout=3):
    end = time.monotonic() + timeout
    out = bytearray()
    while len(out) < size and time.monotonic() < end:
        out.extend(port.read(size - len(out)))
    if len(out) != size:
        raise TimeoutError(f'expected {size} bytes, received {out.hex()}')
    return bytes(out)


def ack(port, timeout=5):
    got = read_exact(port, 1, timeout)
    if got != b'\x79':
        raise RuntimeError(f'ROM ACK expected, received {got.hex()}')


def command(port, value):
    port.write(bytes((value, value ^ 0xFF)))
    port.flush()
    ack(port)


def identify_rom(port):
    # GETID is harmless and has a complete two-byte command. Try it first so
    # an already synchronized ROM is not corrupted by a second lone 0x7f.
    port.write(b'\x02\xfd')
    port.flush()
    try:
        initial = read_exact(port, 1, timeout=1)
    except TimeoutError:
        # A freshly reset ROM ignores commands until its autobaud byte.
        port.reset_input_buffer()
        port.write(b'\x7f')
        port.flush()
        ack(port)
        command(port, 0x02)
    else:
        if initial != b'\x79':
            raise RuntimeError('ROM is not at a command boundary; reset with BOOT0=1 before flashing')
    count = read_exact(port, 1)[0] + 1
    chip_id = read_exact(port, count)
    ack(port)
    return chip_id


def read_memory(port, address, size):
    if not 1 <= size <= 256:
        raise ValueError('invalid ROM read size')
    command(port, 0x11)
    encoded = struct.pack('>I', address)
    port.write(encoded + bytes((xor(encoded),)))
    port.flush()
    ack(port)
    count = bytes((size - 1, (size - 1) ^ 0xFF))
    port.write(count)
    port.flush()
    ack(port)
    return read_exact(port, size)


def parse_report(frame):
    try:
        text = frame.decode('ascii')
        if not text.startswith('$S1,') or not text.endswith('#'):
            return None
        body, check = text[:-1].rsplit(',', 1)
        if crc16(body.encode('ascii')) != int(check, 16):
            return None
        values = [int(part) for part in body[4:].split(',')]
        if len(values) != 15:
            return None
        keys = ('session', 'request', 'us_seq', 'us_age_ms', 'us_valid', 'mm',
                'ir_seq', 'ir_age_ms', 'ir_valid', 'ir', 'left', 'right',
                'lock', 'fault', 'drop')
        return dict(zip(keys, values))
    except (UnicodeDecodeError, ValueError):
        return None


def application_check():
    import serial as app_serial

    session = 0x5A17C0DE
    rx = bytearray()
    reports = []
    raw = bytearray()
    tx = {'Q1': 0, 'PSTOP': 0, 'unexpected': 0}
    with app_serial.Serial('/dev/ttyPS1', 115200, bytesize=8, parity='N',
                           stopbits=1, timeout=0.025, write_timeout=1,
                           exclusive=True) as port:
        port.reset_input_buffer()
        port.write(b'$PSTOP#')
        tx['PSTOP'] += 1
        start = time.monotonic()
        seq = 0
        while time.monotonic() - start < 10:
            seq += 1
            body = f'$Q1,{session},{seq}'.encode('ascii')
            frame = body + f',{crc16(body):04X}#'.encode('ascii')
            port.write(frame)
            tx['Q1'] += 1
            if seq % 10 == 0:
                port.write(b'$PSTOP#')
                tx['PSTOP'] += 1
            chunk = port.read(512)
            raw.extend(chunk)
            rx.extend(chunk)
            while True:
                start_frame = rx.find(b'$')
                if start_frame < 0:
                    rx.clear()
                    break
                if start_frame:
                    del rx[:start_frame]
                end_frame = rx.find(b'#')
                if end_frame < 0:
                    if len(rx) > 256:
                        rx.clear()
                    break
                report = parse_report(bytes(rx[:end_frame + 1]))
                del rx[:end_frame + 1]
                if report is not None:
                    reports.append(report)
    (OUT / 'application_after_go_RX.bin').write_bytes(raw)
    if any(r['lock'] != 1 or r['left'] != 0 or r['right'] != 0 for r in reports):
        raise RuntimeError('application returned an unlocked or nonzero actual output')
    if any(r['session'] != session or not 0 < r['request'] <= seq for r in reports):
        raise RuntimeError('application returned a foreign session or request')
    if any(a['request'] >= b['request'] for a, b in zip(reports, reports[1:])):
        raise RuntimeError('application returned duplicate or backward requests')
    good = reports
    if len(good) < 20:
        raise RuntimeError(f'application returned only {len(good)} safe S1 reports; tx={tx}')
    return {'duration_s': round(time.monotonic() - start, 3),
            'tx': tx, 'valid_s1_reports': len(reports), 'safe_reports': len(good),
            'last_report': good[-1], 'motor_release_or_drive_sent': False,
            'passed': True}


started = time.monotonic()
if hashlib.sha256(NEW_IMAGE).hexdigest() != EXPECTED_NEW_SHA256:
    raise RuntimeError('local firmware SHA-256 does not match the build manifest')
if len(NEW_IMAGE) > FLASH_BYTES:
    raise RuntimeError('firmware does not fit in the expected flash')
if len(NEW_IMAGE) % 4:
    raise RuntimeError('firmware length must be word aligned for this ROM')
if len(NEW_IMAGE) % 2:
    raise RuntimeError('firmware length must be half-word aligned')
old = BACKUP.read_bytes()
old_app = OLD_IMAGE.read_bytes()
if len(old) != FLASH_BYTES or hashlib.sha256(old).hexdigest() != EXPECTED_OLD_SHA256:
    raise RuntimeError('on-board full-flash backup failed its SHA-256 guard')
if hashlib.sha256(old_app).hexdigest() != EXPECTED_OLD_APP_SHA256 or old[:len(old_app)] != old_app:
    raise RuntimeError('on-board backup does not match the known flashed v3 image')

pages = (len(NEW_IMAGE) + PAGE_BYTES - 1) // PAGE_BYTES
if pages != 10:
    raise RuntimeError(f'unexpected erase span: {pages} pages')

with DeviceLease():
    with serial.Serial('/dev/ttyPS1', 115200, bytesize=8, parity='E',
                       stopbits=1, timeout=0.1, write_timeout=2,
                       exclusive=True) as port:
        port.reset_input_buffer()
        chip_id = identify_rom(port)
        if chip_id != b'\x04\x10':
            raise RuntimeError(f'unexpected STM32 chip ID {chip_id.hex()}')
        device_bytes = struct.unpack_from('<H', read_memory(port, 0x1FFFF7E0, 4))[0] * 1024
        if device_bytes != FLASH_BYTES:
            raise RuntimeError(f'unexpected flash capacity {device_bytes}')

        expected = bytearray(old)
        expected[:pages * PAGE_BYTES] = b'\xFF' * (pages * PAGE_BYTES)
        expected[:len(NEW_IMAGE)] = NEW_IMAGE
        before = b''.join(read_memory(port, FLASH_BASE + offset,
                                      min(256, FLASH_BYTES - offset))
                          for offset in range(0, FLASH_BYTES, 256))
        already_new = before == expected
        if before != old and not already_new:
            raise RuntimeError('current full flash differs from both backup and target; no erase sent')
        print(json.dumps({'phase': 'CURRENT_FLASH_VERIFIED',
                          'already_target': already_new}), flush=True)
        written = 0
        erased_pages = []
        if not already_new:
            command(port, 0x43)
            erase_body = bytes((pages - 1,)) + bytes(range(pages))
            port.write(erase_body + bytes((xor(erase_body),)))
            port.flush()
            ack(port, timeout=20)
            erased_pages = list(range(pages))
            for offset in range(0, len(NEW_IMAGE), 256):
                block = NEW_IMAGE[offset:offset + 256]
                if len(block) % 4:
                    raise RuntimeError('ROM write block is not word aligned')
                command(port, 0x31)
                address = struct.pack('>I', FLASH_BASE + offset)
                port.write(address + bytes((xor(address),)))
                port.flush()
                ack(port)
                payload = bytes((len(block) - 1,)) + block
                port.write(payload + bytes((xor(payload),)))
                port.flush()
                ack(port)
                written += len(block)
        print(json.dumps({'phase': 'FLASH_WRITTEN', 'bytes': written}), flush=True)
        actual = b''.join(read_memory(port, FLASH_BASE + offset,
                                      min(256, FLASH_BYTES - offset))
                          for offset in range(0, FLASH_BYTES, 256))
        actual_sha = hashlib.sha256(actual).hexdigest()
        if actual != expected:
            mismatch = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
            raise RuntimeError(f'full-flash verification mismatch at {mismatch:#x}')
        if actual[:len(NEW_IMAGE)] != NEW_IMAGE:
            raise RuntimeError('firmware region readback mismatch')
        if actual[pages * PAGE_BYTES:] != old[pages * PAGE_BYTES:]:
            raise RuntimeError('flash outside the erase span did not match backup')
        (OUT / 'after_uart_role_fix.bin').write_bytes(actual)
        (OUT / 'flash_verified.json').write_text(json.dumps({
            'firmware_sha256': hashlib.sha256(NEW_IMAGE).hexdigest(),
            'full_readback_sha256': actual_sha, 'readback_bytes': len(actual),
            'outside_erase_span_preserved': True, 'written_bytes': written}))
        print(json.dumps({'phase': 'FULL_FLASH_READBACK_VERIFIED',
                          'bytes': len(actual)}), flush=True)

        command(port, 0x21)
        go_address = struct.pack('>I', FLASH_BASE)
        port.write(go_address + bytes((xor(go_address),)))
        port.flush()
        ack(port)

    time.sleep(0.5)
    app = application_check()

result = {
    'kind': 'STM32_UART_ROLE_FIX_FLASH_AND_LIVE_CHECK',
    'hardware': True,
    'chip_id': chip_id.hex(),
    'flash_bytes': device_bytes,
    'old_full_flash_sha256': hashlib.sha256(old).hexdigest(),
    'old_application_sha256': hashlib.sha256(old_app).hexdigest(),
    'firmware_bytes': len(NEW_IMAGE),
    'firmware_sha256': hashlib.sha256(NEW_IMAGE).hexdigest(),
    'erased_pages': erased_pages,
    'already_target_before_run': already_new,
    'written_bytes': written,
    'readback_bytes': len(actual),
    'readback_sha256': actual_sha,
    'full_readback_matches_backup_plus_image': True,
    'outside_erase_span_preserved': True,
    'application_after_rom_go': app,
    'elapsed_s': round(time.monotonic() - started, 3),
    'motor_power': 'disconnected by user',
    'motor_release_or_drive_sent': False,
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'flash_result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, separators=(',', ':')))
