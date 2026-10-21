"""Offline verification of the actual full-device UART readbacks."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = ROOT / 'pynq_fpga/lab/task7_8_lab_only_v010_stm32_sensors_20261013_r3'
manifest = json.loads((PACKAGE / 'lab_manifest.json').read_text(encoding='utf-8'))
before = (HERE / 'before_flash_128k.bin').read_bytes()
after = (HERE / 'after_flash_128k.bin').read_bytes()
firmware = (PACKAGE / 'stm32_hybrid_v3.bin').read_bytes()
digest = lambda data: hashlib.sha256(data).hexdigest()
assert len(before) == len(after) == 128 * 1024
assert digest(before) == '54547087cb34ae92033bb86aee53d0a711afc9a951cb277f118b023666f45fe1'
assert digest(firmware) == manifest['artifacts']['stm32_bin']['sha256']
assert after[:len(firmware)] == firmware
expected = bytearray(before)
expected[:10 * 1024] = b'\xff' * (10 * 1024)
expected[:len(firmware)] = firmware
assert after == bytes(expected), 'Unexpected change outside programmed pages/padding'
options = 'A5 5A FF FF FF FF FF FF FF FF FF FF FF FF FF FF'
assert options in (HERE / 'chip_identification.log').read_text(encoding='utf-8-sig')
assert options in (HERE / 'readback.log').read_text(encoding='utf-8-sig')
record = {
    'schema': 'stm32-uart-flash/v1',
    'verified_at_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'FLASH_VERIFIED_BOOT_RESET_PENDING',
    'hardware': True,
    'port': 'COM5', 'bootloader_baud': 115200, 'bootloader_parity': 'EVEN',
    'chip_id': '0x410', 'bootloader_version': '2.2',
    'factory_flash_size_kib': 128,
    'uid_bytes_hex': '301a021e7116303030303032',
    'package_contract': manifest['integrated_id'],
    'firmware_hex': str(PACKAGE / 'stm32_hybrid_v3.hex'),
    'firmware_hex_sha256': manifest['artifacts']['stm32_hex']['sha256'],
    'firmware_bin_sha256': digest(firmware),
    'firmware_bytes': len(firmware), 'flash_start': '0x08000000',
    'erased_pages': list(range(10)), 'page_bytes': 1024,
    'backup_file': 'before_flash_128k.bin', 'backup_sha256': digest(before),
    'readback_file': 'after_flash_128k.bin', 'readback_sha256': digest(after),
    'full_flash_readback_verified': True,
    'outside_erased_pages_unchanged': True, 'option_bytes_unchanged': True,
    'application_startup_verified': False,
    'pynq_deployed_in_this_task': False, 'nonzero_motor_command_sent': False,
    'sensor_joint_tested': False,
}
(HERE / 'flash_record.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print('FLASH_READBACK_PASS: 9372 firmware bytes match; remaining Flash and option bytes preserved')
