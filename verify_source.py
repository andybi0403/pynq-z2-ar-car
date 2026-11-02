from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent
m=json.loads((r/'SOURCE_MANIFEST.json').read_text('utf8'))
for n,h in m['files'].items():
 p=r/n
 assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==h,n
print('PASS:',len(m['files']),'files; deployed identity',m['version'])
