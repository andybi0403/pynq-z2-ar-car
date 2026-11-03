"""Verify current package hashes and unchanged original artifacts; no hardware access."""
from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent
m=json.loads((r/'SOURCE_MANIFEST.json').read_text('utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
actual={p.relative_to(r).as_posix() for p in r.rglob('*') if p.is_file()
        and '.git' not in p.relative_to(r).parts and '__pycache__' not in p.parts
        and not p.name.endswith('.pyc') and p.relative_to(r).parts[0]!='validation'}
assert actual==set(m['files'])|{'SOURCE_MANIFEST.json'},'Unexpected or missing packaged files'
for n,h in m['files'].items():
 p=r/n
 assert n.isascii() and ' ' not in n,'Non-English or spaced package path: '+n
 assert p.is_file() and sha(p)==h,n
old=json.loads((r/'verification/original_source_manifest.json').read_text('utf8'))
for n,h in old['files'].items():
 if Path(n).suffix.lower() in {'.bit','.hwh','.bin','.hex','.so'}:
  assert sha(r/n)==h,'Original binary changed: '+n
for n,h in old.get('fpga_source_verified',{}).items():
 if '/rtl/' in n:
  assert sha(r/n)==h,'Bound RTL changed: '+n
print('PASS:',len(m['files']),'files; ASCII paths; original binaries and bound RTL unchanged;',m['version'])
