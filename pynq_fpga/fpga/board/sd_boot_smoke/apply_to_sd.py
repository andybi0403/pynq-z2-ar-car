"""Back up and temporarily replace only BOOT.BIN on the identified school card.

--restore restores the verified original 3.0.1 boot file. Both modes leave the
Linux partition and project files alone, read back the FAT partition physically,
and attempt safe ejection. Administrator rights are required.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import shutil
import struct
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REPORT = HERE / 'output/card_deployment.json'
spec = importlib.util.spec_from_file_location('recovery', ROOT / 'tmp/reflash_pynq_301.py')
REC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REC)
IO = REC.IO

def save(stage, **kwargs):
    REPORT.write_text(json.dumps({'stage': stage, 'time': time.strftime('%Y-%m-%d %H:%M:%S'), **kwargs},
                                indent=2, ensure_ascii=False), encoding='utf-8')

def fat16_root_hashes(data):
    sector = struct.unpack_from('<H', data, 11)[0]
    cluster_size = data[13] * sector
    reserved = struct.unpack_from('<H', data, 14)[0]
    fats = data[16]
    entries = struct.unpack_from('<H', data, 17)[0]
    fat_sectors = struct.unpack_from('<H', data, 22)[0]
    assert sector == 512 and entries > 0 and fat_sectors > 0
    fat_start = reserved * sector
    root_start = fat_start + fats * fat_sectors * sector
    data_start = root_start + ((entries * 32 + sector - 1) // sector) * sector
    hashes = {}
    for offset in range(root_start, root_start + entries * 32, 32):
        entry = data[offset:offset+32]
        if entry[0] == 0:
            break
        if entry[0] == 0xe5 or entry[11] == 0x0f or entry[11] & 0x18:
            continue
        name = entry[:8].decode('ascii').rstrip()
        extension = entry[8:11].decode('ascii').rstrip()
        name += '.' + extension if extension else ''
        cluster = struct.unpack_from('<H', entry, 26)[0]
        size = struct.unpack_from('<I', entry, 28)[0]
        content = bytearray()
        seen = set()
        while 2 <= cluster < 0xfff8 and len(content) < size:
            assert cluster not in seen
            seen.add(cluster)
            start = data_start + (cluster - 2) * cluster_size
            assert start + cluster_size <= len(data)
            content.extend(data[start:start+cluster_size])
            cluster = struct.unpack_from('<H', data, fat_start + cluster * 2)[0]
        assert len(content) >= size
        hashes[name] = hashlib.sha256(content[:size]).hexdigest()
    return hashes

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if not C.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('Administrator rights required; card not changed.')
    target = json.loads((ROOT / 'tmp/pynq_301_card_target.json').read_text(encoding='utf-8-sig'))
    deployment = json.loads((ROOT / 'tmp/pynq_301_deployment_manifest.json').read_text(encoding='utf-8'))
    verification = json.loads((HERE / 'output/verification.json').read_text(encoding='utf-8'))
    assert verification['status'] == 'OFFLINE_VERIFIED_BOARD_PENDING'
    disk = REC.inspect(target['Number'])
    assert disk['PNP'] == target['PNP'] and disk['Size'] == 31914983424 and disk['BusType'] == 'USB'
    assert not disk['IsBoot'] and not disk['IsSystem'] and not disk['IsReadOnly']
    parts = sorted(disk['Partitions'], key=lambda item: item['Offset'])
    assert len(parts) == 2 and parts[0]['Offset'] == 4096 and parts[0]['Size'] == 136314880
    assert parts[0]['DriveLetter'] == 'E' and parts[1]['Offset'] == 137363456 and parts[1]['Size'] == 7721444352
    root = Path('E:/')
    expected = dict(deployment['boot_files'])
    source = ROOT / 'tmp/pynq_301_original_boot/BOOT.BIN' if args.restore else HERE / 'output/BOOT.BIN'
    new_hash = deployment['boot_files']['BOOT.BIN'] if args.restore else verification['boot_bin_sha256']
    current_hash = verification['boot_bin_sha256'] if args.restore else deployment['boot_files']['BOOT.BIN']
    assert REC.sha(source) == new_hash
    for name, digest in expected.items():
        assert REC.sha(root / name) == (current_hash if name == 'BOOT.BIN' else digest)
    project = root / deployment['card_directory']
    for name, digest in deployment['project_files'].items():
        assert REC.sha(project / name) == digest
    backup_dir = ROOT / 'tmp/sd_boot_smoke_backups' / time.strftime('%Y%m%d_%H%M%S')
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = backup_dir / 'BOOT.BIN'
    shutil.copyfile(root / 'BOOT.BIN', backup)
    assert REC.sha(backup) == current_hash
    save('backup_verified', backup=str(backup), sha256=current_hash, restore=args.restore)
    shutil.copyfile(source, root / 'BOOT.BIN')
    assert REC.sha(root / 'BOOT.BIN') == new_hash
    expected['BOOT.BIN'] = new_hash
    for name, digest in expected.items():
        assert REC.sha(root / name) == digest
    for name, digest in deployment['project_files'].items():
        assert REC.sha(project / name) == digest
    volume = raw = buffer = None
    try:
        volume = IO.open_device(r'\\.\E:')
        IO.check(IO.K.FlushFileBuffers(volume), 'Flush updated boot file')
        locked = False
        for _ in range(20):
            if IO.ioctl(volume, 0x00090018):
                locked = True
                break
            time.sleep(0.5)
        IO.check(locked, 'Lock updated boot volume')
        IO.check(IO.ioctl(volume, 0x00090020), 'Dismount updated boot volume')
        raw = IO.open_device(r'\\.\PhysicalDrive' + str(disk['Number']), 0xA0000000)
        length = C.c_longlong()
        IO.check(IO.ioctl(raw, 0x0007405c, length), 'Confirm physical capacity')
        assert length.value == 31914983424
        chunk = 4 * 1024 * 1024
        buffer = IO.check(IO.K.VirtualAlloc(None, chunk, 0x3000, 0x04), 'Allocate aligned read buffer')
        IO.check(IO.K.SetFilePointerEx(raw, parts[0]['Offset'], None, 0), 'Seek FAT partition')
        content = bytearray()
        count = IO.W.DWORD()
        while len(content) < parts[0]['Size']:
            amount = min(chunk, parts[0]['Size'] - len(content))
            IO.check(IO.K.ReadFile(raw, buffer, amount, C.byref(count), None), 'Read FAT partition physically')
            assert count.value == amount
            content.extend(C.string_at(buffer, amount))
        hashes = fat16_root_hashes(content)
        assert all(hashes[name] == digest for name, digest in expected.items())
        IO.K.CloseHandle(volume)
        volume = None
        ejected = bool(IO.ioctl(raw, 0x002d4808))
        save('complete', restore=args.restore, boot_bin_sha256=new_hash, backup=str(backup),
             physical_fat_readback_pass=True, other_boot_files_verified=True,
             project_files_verified=len(deployment['project_files']),
             ejected=ejected, eject_error=None if ejected else C.get_last_error(),
             board_boot_verified=False)
    finally:
        if buffer:
            IO.K.VirtualFree(buffer, 0, 0x8000)
        if raw is not None:
            IO.K.CloseHandle(raw)
        if volume is not None:
            IO.K.CloseHandle(volume)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        save('failed', error=traceback.format_exc())
        raise
