import base64, hashlib, json, sys, zlib
from pathlib import Path
name = sys.argv[1]
folder = Path(__file__).parent
envelope = json.loads((folder/(name+'_uart.json')).read_text('utf8'))
if envelope['returncode'] != 0:
    print(envelope['output'])
    raise SystemExit(envelope['returncode'])
record = next(json.loads(line) for line in envelope['output'].splitlines() if line.startswith('{') and '"archive"' in line)
archive = record.pop('archive')
raw = zlib.decompress(base64.b64decode(archive['zlib_base64']))
assert len(raw) == archive['bytes'] and hashlib.sha256(raw).hexdigest() == archive['sha256']
rows = [json.loads(line) for line in raw.decode().splitlines()]
assert len(rows) == record['samples']
assert record['restored'] and all(rows[i+1]['epoch'] > rows[i]['epoch'] for i in range(len(rows)-1))
record['sample_archive_sha256'] = archive['sha256']
record['static_diagnostic_fault'] = any(r[channel] != rows[0][channel] or r[channel+'_illegal'] > 0 or
    r[channel+'_filtered'] > 0 for r in rows for channel in ('left', 'right'))
record['first_diagnostic_event_seconds'] = next((r['t'] - rows[0]['t'] for r in rows if any(
    r[channel] != rows[0][channel] or r[channel+'_illegal'] > 0 or r[channel+'_filtered'] > 0
    for channel in ('left', 'right'))), None)
(folder/(name+'_summary.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), 'utf8')
(folder/(name+'_samples.jsonl')).write_bytes(raw)
print(json.dumps(record, ensure_ascii=False))
