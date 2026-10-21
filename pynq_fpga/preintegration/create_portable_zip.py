"""Produce POSIX member paths for candidates deployed from Windows to Linux."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import zipfile


def verify_archive(archive):
    with zipfile.ZipFile(archive) as z:
        names=[]
        for info in z.infolist():
            name=info.orig_filename;relative=PurePosixPath(name)
            if '\\' in name or relative.is_absolute() or '..' in relative.parts:
                raise ValueError('nonportable or unsafe archive member: '+name)
            names.append(name)
        if len(names)!=len(set(names)):raise ValueError('duplicate archive member')
        manifest=json.loads(z.read('lab_manifest.json').decode('utf-8-sig'))
        expected={**manifest['runtime_files'],**manifest.get('wireless_files',{})}
        for item in manifest['artifacts'].values():expected[item['file']]=item['sha256']
        for name,digest in expected.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:
                raise ValueError('archive source/artifact mismatch: '+name)
        if z.testzip() is not None:raise ValueError('archive CRC check failed')
        return len(names)


def create_archive(directory,archive):
    folder=Path(directory).resolve()
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob('*')):
            if not path.is_file():continue
            path.resolve().relative_to(folder)
            z.write(path,path.relative_to(folder).as_posix())
    return verify_archive(archive)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('archive',type=Path)
    args=parser.parse_args()
    print('PORTABLE_ARCHIVE_PASS files='+str(create_archive(args.directory,args.archive)))
