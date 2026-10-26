
"""Verify public handoff parts and optionally restore into a new directory."""
from pathlib import Path
import argparse,hashlib,json,zipfile

def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract',type=Path,help='new, nonexistent restoration directory')
    args=parser.parse_args()
    here=Path(__file__).resolve().parent
    root=here.parents[1]
    manifest=json.loads((here/'archive_manifest.json').read_text('utf8'))
    package=root/manifest['latest_package']
    if package.exists():
        assert sha(package)==manifest['latest_package_sha256'],'latest runtime package differs'
    for archive in manifest['archives']:
        for part in archive['parts']:
            file=here/part['file']
            assert file.is_file() and file.stat().st_size==part['bytes'],part['file']
            assert sha(file)==part['sha256'],part['file']
        print('PARTS_OK',archive['name'],len(archive['parts']))
    if args.extract:
        target=args.extract.resolve()
        assert not target.exists(),'restore into a NEW directory; existing paths are refused'
        target.mkdir(parents=True)
        for archive in manifest['archives']:
            joined=target/archive['name']
            with joined.open('xb') as output:
                for part in archive['parts']:
                    with (here/part['file']).open('rb')as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):output.write(block)
            assert joined.stat().st_size==archive['bytes'] and sha(joined)==archive['sha256']
            with zipfile.ZipFile(joined)as z:
                assert z.testzip() is None,'archive CRC failure'
                for member in z.infolist():
                    path=Path(member.filename)
                    assert not path.is_absolute()and'..'not in path.parts and'\\'not in member.filename
                    assert (target/path).resolve().is_relative_to(target)
                z.extractall(target)
            print('RESTORED',archive['name'],archive['entries'])
    print('HANDOFF_VERIFIED')

if __name__=='__main__':main()
