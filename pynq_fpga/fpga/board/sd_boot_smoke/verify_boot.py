"""Check generated boot structures and exact FSBL/PL/app payload identities."""
from array import array
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output'
ROOT = HERE.parents[3]
image = (OUT / 'BOOT.BIN').read_bytes()
original = (ROOT / 'tmp/pynq_301_original_boot/BOOT.BIN').read_bytes()
word = lambda offset: struct.unpack_from('<I', image, offset)[0]
assert word(0x20) == 0xaa995566 and word(0x24) == 0x584c4e58 and word(0x28) == 0
assert sum(word(offset) for offset in range(0x20, 0x4c, 4)) & 0xffffffff == 0xffffffff
provenance = json.loads((OUT / 'input_provenance.json').read_text())
assert word(0x34) == word(0x40) == provenance['fsbl_bytes']
assert word(0x38) == provenance['fsbl_load'] and word(0x3c) == provenance['fsbl_entry']
fsbl = image[word(0x30):word(0x30)+word(0x34)]
assert hashlib.sha256(fsbl).hexdigest() == provenance['fsbl_sha256']
assert fsbl == (OUT / 'fsbl_original.bin').read_bytes()
assert image[:0x8a0] == original[:0x8a0], 'BootROM header differs from the official image'
table = word(0x98)
assert word(table + 4) == 3
partition_start = word(table + 8) * 4
assert partition_start == word(0x9c)
parts = []
for index in range(3):
    values = struct.unpack_from('<16I', image, partition_start + index * 64)
    assert sum(values) & 0xffffffff == 0xffffffff
    size, load, entry, offset, attributes = values[1]*4, values[3], values[4], values[5]*4, values[6]
    assert values[0] == values[1] == values[2] and offset + size <= len(image)
    assert attributes in (0x10, 0x20)
    parts.append({'size': size, 'load': load, 'entry': entry, 'offset': offset, 'attributes': attributes})
assert parts[0]['attributes'] == 0x10 and parts[0]['load'] == parts[0]['entry'] == 0
assert image[parts[0]['offset']:parts[0]['offset']+parts[0]['size']] == fsbl
assert parts[1]['attributes'] == 0x20 and parts[1]['load'] == parts[1]['entry'] == 0
bit_file = (OUT / 'sd_boot_led.bit').read_bytes()
position = 2 + struct.unpack_from('>H', bit_file, 0)[0]
assert struct.unpack_from('>H', bit_file, position)[0] == 1
position += 2
for expected_tag in b'abcde':
    assert bit_file[position] == expected_tag
    position += 1
    if expected_tag == ord('e'):
        size = struct.unpack_from('>I', bit_file, position)[0]
        position += 4
        bit = bit_file[position:position+size]
        assert position + size == len(bit_file)
    else:
        size = struct.unpack_from('>H', bit_file, position)[0]
        position += 2 + size
swapped = array('I', bit)
swapped.byteswap()
pl = image[parts[1]['offset']:parts[1]['offset']+parts[1]['size']]
assert pl[:len(bit)] == swapped.tobytes(), 'PL configuration differs from the compiled bitstream'
assert len(pl) - len(bit) == 4
assert pl[len(bit):] == struct.pack('<I', 0x20000000)  # Bootgen alignment NOP.
assert parts[2]['attributes'] == 0x10 and parts[2]['load'] == parts[2]['entry'] == 0x200000
assert parts[2]['size'] == 4
assert image[parts[2]['offset']:parts[2]['offset']+4] == struct.pack('<I', 0xeafffffe)
implemented = (OUT / 'implemented.v').read_text()
assert '.I(\\<const1> ),\n        .O(led[0])' in implemented
assert all(f'.I(\\<const0> ),\n        .O(led[{index}])' in implemented for index in (1, 2, 3))
record = {'status': 'OFFLINE_VERIFIED_BOARD_PENDING', 'boot_bin_bytes': len(image),
          'boot_bin_sha256': hashlib.sha256(image).hexdigest(),
          'official_bootrom_header_identical': True, 'official_fsbl_payload_identical': True,
          'partition_checksums_valid': True, 'compiled_bitstream_payload_identical': True,
          'implemented_led0_high': True, 'expected': 'DONE and LED0 steady on after successful early boot',
          'drc_errors': 0, 'drc_warning': 'ZPS7-1: PL-only diagnostic; PS initialization is performed by the preserved official FSBL',
          'partitions': parts, 'board_boot_verified': False, 'sd_card_modified': False}
(OUT / 'verification.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({key: record[key] for key in ('status','boot_bin_bytes','official_bootrom_header_identical',
                 'official_fsbl_payload_identical','partition_checksums_valid','compiled_bitstream_payload_identical')}, indent=2))
