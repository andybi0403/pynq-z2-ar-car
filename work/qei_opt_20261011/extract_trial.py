import base64,hashlib,json,sys,zlib
from pathlib import Path
envelope=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
job=json.loads(envelope.read_text('utf8'))
results=[json.loads(line) for line in job['output'].splitlines() if line.startswith('{')]
result=next(r for r in results if r.get('kind')=='QEI_QUALITY_TRIAL')
archive=result.pop('raw_archive');raw=zlib.decompress(base64.b64decode(archive.pop('zlib_base64')))
assert len(raw)==archive['bytes'] and hashlib.sha256(raw).hexdigest()==archive['sha256']
result['raw_archive']=archive
for name,data in [('台架原始采集.jsonl',raw),('台架复测结果.json',json.dumps(result,ensure_ascii=False,indent=2).encode('utf8'))]:
    dest=out/name
    assert not dest.exists();dest.write_bytes(data)
print(json.dumps(result,ensure_ascii=False,indent=2))
