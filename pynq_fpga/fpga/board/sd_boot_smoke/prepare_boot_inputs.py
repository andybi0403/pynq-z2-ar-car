"""Preserve the official FSBL payload exactly in a single-segment ARM ELF.

This only prepares local diagnostic inputs; it never accesses a removable disk.
"""
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE / 'output'
OUT.mkdir(exist_ok=True)
source = ROOT / 'tmp/pynq_301_original_boot/BOOT.BIN'
manifest = json.loads((ROOT / 'tmp/pynq_301_deployment_manifest.json').read_text(encoding='utf-8'))
data = source.read_bytes()
assert hashlib.sha256(data).hexdigest() == manifest['boot_files']['BOOT.BIN']
word = lambda offset: struct.unpack_from('<I', data, offset)[0]
assert word(0x20) == 0xaa995566 and word(0x24) == 0x584c4e58
assert word(0x28) == 0  # unencrypted original
assert (sum(word(offset) for offset in range(0x20, 0x4c, 4)) & 0xffffffff) == 0xffffffff
offset, length, load, entry, total = [word(position) for position in (0x30, 0x34, 0x38, 0x3c, 0x40)]
assert length == total and offset + length <= len(data)
assert load == 0 and entry == 0 and length < 0x30000
payload = data[offset:offset+length]

def elf(payload, load, entry):
    ident = b'\x7fELF' + bytes([1, 1, 1, 0]) + bytes(8)
    header = struct.pack('<16sHHIIIIIHHHHHH', ident, 2, 40, 1, entry, 52, 0,
                         0x05000000, 52, 32, 1, 0, 0, 0)
    program = struct.pack('<IIIIIIII', 1, 0x1000, load, load, len(payload), len(payload), 7, 0x1000)
    return header + program + bytes(0x1000 - len(header) - len(program)) + payload

(OUT / 'fsbl_original.bin').write_bytes(payload)
(OUT / 'fsbl_original.elf').write_bytes(elf(payload, load, entry))
idle = struct.pack('<I', 0xeafffffe)  # ARM: b .; no peripheral access or outputs.
(OUT / 'idle.elf').write_bytes(elf(idle, 0x00200000, 0x00200000))
register_init = [struct.unpack_from('<II', data, 0xa0 + index * 8) for index in range(256)]
active_init = [(address, value) for address, value in register_init if address != 0xffffffff]
init_line = ''
if active_init:
    (OUT / 'original_init.int').write_text(''.join(f'0x{a:08x} 0x{v:08x}\n' for a, v in active_init), encoding='ascii')
    init_line = '    [init] output/original_init.int\n'
(HERE / 'boot.bif').write_text('diagnostic:\n{\n' + init_line +
    '    [bootloader] output/fsbl_original.elf\n'
    '    output/sd_boot_led.bit\n'
    '    output/idle.elf\n}\n', encoding='ascii')
record = {'official_image_version': '3.0.1', 'official_boot_bin_sha256': hashlib.sha256(data).hexdigest(),
          'fsbl_source_offset': offset, 'fsbl_bytes': length, 'fsbl_load': load,
          'fsbl_entry': entry, 'fsbl_sha256': hashlib.sha256(payload).hexdigest(),
          'register_init_pairs': active_init, 'cpu_idle_load': 0x200000,
          'expected_led': 'LED0 steady on; LED1-3 off', 'board_tested': False}
(OUT / 'input_provenance.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({'fsbl_bytes': length, 'original_fsbl_preserved': True, 'init_pairs': len(active_init), 'sd_card_modified': False}))
