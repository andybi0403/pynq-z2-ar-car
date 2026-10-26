"""Build a public handoff snapshot without opening hardware or reading credentials."""
from pathlib import Path
import argparse,collections,hashlib,json,os,re,shutil,time,zipfile
ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/'handoff/20261026'
OUT=ROOT/'output/handoff_20261026'
REPO=ROOT/'github_repo'
PART=24*1024*1024
SKIP_DIR={'.git','.Xil','__pycache__','node_modules','.pytest_cache','.metadata',
          '.cache','.venv','venv','xsim.dir','ip_user_files','.ip_user_files'}
SKIP_SUFFIX={'.o','.obj','.exe','.dll','.lib','.exp','.dcp','.rpx','.vcd','.wdb','.pb','.str','.pyc','.pyo'}
SKIP_PREFIX=('tmp/sd_recovery_backups/','tmp/pynq27_download_parts/','pynq-z2资料/系统镜像/')
BROWSER_DIR={'browser-profile','browser_profile','edge-profile','chrome-profile','user-data','User Data'}
TEXT={'.txt','.log','.jou','.rpt','.json','.jsonl','.md','.csv','.yaml','.yml','.xml','.html','.js','.py','.ps1','.sh','.tcl','.diff','.ini','.cfg','.v','.sv','.h','.c','.xdc','.bat','.xpr','.prj','.ipynb','.css','.toml','.properties','.manifest','.url'}
SOURCE_TOP={'docs','skill','tools','validation','9.17夜间任务队列','9.18夜间任务队列','9.19夜间任务队列','stm32_pynq对接版','stm32预备程序'}
HARDWARE_TOP={'pynq-z2资料','stm32-4wd小车零件资料','pdf_review','tmp_pdf','pdf_review'}
SOURCE_FPGA={'rtl','tb','registers','board','constraints','scripts'}
SOURCE_PRE={'board_repo','camera','constraints','host','manifests','native','rtl','tb','tests','validation'}
PRIVATE_PATTERNS=[
 (re.compile(r'(?i)((?:#|%23|[?&])token=)[A-Za-z0-9_%.-]{12,}'),r'\1REDACTED'),
 (re.compile(r'(?i)(Bearer\s+)[A-Za-z0-9_.~+/-]{12,}'),r'\1REDACTED'),
 (re.compile(r'(?i)(["\x27](?:access_token|refresh_token|control_token|auth_token|token|password)["\x27]\s*:\s*["\x27])([^"\x27\r\n]{8,})(["\x27])'),r'\1REDACTED\3'),
 (re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,})\b'),'REDACTED_PRIVATE_TOKEN'),
 (re.compile(r'(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b'),'REDACTED_MAC'),
 (re.compile(r'(?i)((?:GUID|Physical address|AP BSSID)\s*:\s*)[^\r\n\\]*'),r'\1REDACTED'),
]
def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def clean(data):
 try:s=data.decode('utf8')
 except UnicodeDecodeError:return data,0
 n=0
 for pattern,replacement in PRIVATE_PATTERNS:
  s,k=pattern.subn(replacement,s);n+=k
 return s.encode('utf8'),n
def reason(rel):
 p=Path(rel);parts=p.parts
 if any(x in SKIP_DIR or x in BROWSER_DIR or x.endswith(('.runs','.cache','.sim','.hw','.gen','.srcs'))for x in parts):return 'rebuildable cache, generated IP, browser profile, or nested VCS'
 if rel.startswith('pynq_fpga/fpga/build/sim') and p.suffix.lower() in {'.rgb','.bgr0','.yuv','.ppm','.mem','.crf','.vdb'}:return 'regenerable simulator frame/output; testbench and logs retained'
 if rel.startswith(SKIP_PREFIX):return 'large local SD/system image or download chunks; retained locally'
 if rel.startswith('pynq_fpga/third_party/PYNQ-Z2_sobel_filter_HDMI/'):return 'reference project has no redistribution license; see THIRD_PARTY_NOTICES'
 if p.suffix.lower() in SKIP_SUFFIX:return 'rebuildable object/checkpoint/waveform/tool binary'
 if p.name.startswith('.env') or p.suffix.lower()in{'.pem','.key','.pfx'}:return 'private local configuration/credential material'
 if rel=='work/five_round_20261026/raw_evidence.tar.gz':return 'duplicate container; extracted raw_evidence/ fully included'
 if rel.endswith('.zip.partial'):return 'incomplete transfer'
 return None
def category(rel):
 p=Path(rel);q=p.parts
 if len(q)==1:return 'source'
 if q[0]=='handoff':return 'source'
 if q[0]in HARDWARE_TOP:return 'hardware'
 if q[0]in SOURCE_TOP:return 'source'
 if q[0]=='pynq_fpga':
  if len(q)==2 or q[1]in{'host','release','third_party'}:return 'source'
  if q[1]=='fpga'and(len(q)==3 or q[2]in SOURCE_FPGA):return 'source'
  if q[1]=='preintegration'and(len(q)==3 or q[2]in SOURCE_PRE):return 'source'
  if q[1]=='nightly'and(len(q)==3 or q[2]=='native'):return 'source'
 return 'debug'
def selected():
 prefixes=['docs','pynq_fpga','stm32_pynq对接版','stm32预备程序','tools','skill','validation','work','tmp','pynq-z2资料','stm32-4wd小车零件资料','9.17夜间任务队列','9.18夜间任务队列','9.19夜间任务队列','pdf_review','tmp_pdf','handoff','output/documents','output/pdf']
 for top in prefixes:
  path=ROOT/top
  if not path.exists():continue
  for directory,dirs,files in os.walk(path,followlinks=False):
   rel_dir=Path(directory).relative_to(ROOT).as_posix()
   kept=[]
   for name in sorted(dirs):
    r=rel_dir+'/'+name
    why=reason(r+'/')
    if why:
     yield None,r+'/',why
    elif not Path(directory,name).is_symlink():kept.append(name)
   dirs[:]=kept
   for name in sorted(files):
    f=Path(directory,name);rel=f.relative_to(ROOT).as_posix()
    if f.is_symlink():yield None,rel,'symlink to external dependency';continue
    why=reason(rel)
    if rel.startswith('handoff/20261026/archives/')or f.name in{'archive_manifest.json','package_inventory.jsonl','publication_summary.json'}:continue
    yield f,rel,why
 for f in sorted(ROOT.iterdir()):
  if f.is_file():yield f,f.name,reason(f.name)
def census():
 counts=collections.defaultdict(lambda:{'files':0,'bytes':0});omit=collections.Counter()
 for f,r,why in selected():
  if why:omit[why]+=1;continue
  c=category(r);counts[c]['files']+=1;counts[c]['bytes']+=f.stat().st_size
 print(json.dumps({'selected':dict(counts),'omitted':dict(omit)},ensure_ascii=False,indent=2))
def build():
 if (OUT/'COMPLETE.json').exists():raise SystemExit('Immutable output exists; choose a new handoff revision instead of overwriting.')
 OUT.mkdir(parents=True,exist_ok=True);(REPO/'handoff/20261026/archives').mkdir(parents=True,exist_ok=True)
 inventory=[];excluded=[];stats=collections.Counter();zips={}
 for c in ('debug','hardware'):zips[c]=zipfile.ZipFile(OUT/(c+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True)
 try:
  for f,rel,why in selected():
   if why:excluded.append({'path':rel,'reason':why});continue
   c=category(rel);data=f.read_bytes();original=digest(data);redactions=0
   # Preserve source and frozen packages byte-for-byte. Only publish sanitized evidence/chat copies.
   if (c!='source'or rel.startswith('handoff/20261026/chat/'))and f.suffix.lower()in TEXT:
    data,redactions=clean(data)
   if f.stat().st_size>=100*1024*1024 and c=='source':
    c='debug'
   item={'path':rel,'category':c,'original_bytes':f.stat().st_size,'published_bytes':len(data),'original_sha256':original,'published_sha256':digest(data),'redactions':redactions}
   inventory.append(item);stats[c]+=1;stats['redacted_files']+=int(redactions>0)
   if c=='source':
    dest=REPO/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists()or sha(dest)!=item['published_sha256']:dest.write_bytes(data)
   else:zips[c].writestr(rel,data)
   if len(inventory)%1000==0:print(json.dumps({'processed_files':len(inventory),'category':c},ensure_ascii=False),flush=True)
 finally:
  for z in zips.values():z.close()
 archives=[]
 # Source archive contains the actual synchronized current tree selected above, not obsolete clone files.
 source_zip=OUT/'source.zip'
 with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True)as z:
  for item in inventory:
   if item['category']=='source':z.write(REPO/item['path'],item['path'])
 for c in ('source','debug','hardware'):
  archive=OUT/(c+'.zip');record={'name':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive),'parts':[]}
  with archive.open('rb')as f:
   i=1
   while chunk:=f.read(PART):
    name=f'{c}.zip.part{i:03d}';target=REPO/'handoff/20261026/archives'/name;target.write_bytes(chunk)
    record['parts'].append({'file':'archives/'+name,'bytes':len(chunk),'sha256':digest(chunk)});i+=1
  with zipfile.ZipFile(archive)as z:
   failed=z.testzip()
   if failed:raise RuntimeError('Bad archived member '+failed)
   record['entries']=len(z.infolist())
  archives.append(record);print(json.dumps({'archive':c,'bytes':record['bytes'],'parts':len(record['parts']),'entries':record['entries']}),flush=True)
 manifest={'schema':1,'created_local':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'latest_package':'pynq_fpga/release/v011_uart_recovery_20261026_r17b.zip','latest_package_sha256':'e03d5e463cf318f0e58737927e1c459565f7e18cc11033e706753d0d9a7d8199','archives':archives,'excluded':excluded,'counts':dict(stats),'redaction_policy':'Evidence/chat public copies only; source/runtime archives preserve original bytes. Original files remain on the original computer.'}
 inv=''.join(json.dumps(x,ensure_ascii=False)+'\n'for x in inventory)
 for dest in(DOC,REPO/'handoff/20261026'):
  (dest/'archive_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf8')
  (dest/'package_inventory.jsonl').write_text(inv,'utf8')
 summary={'counts':dict(stats),'archives':[{k:v for k,v in x.items()if k!='parts'}for x in archives],'source_entries':sum(x['category']=='source'for x in inventory)}
 (OUT/'COMPLETE.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf8')
 print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--build',action='store_true');args=parser.parse_args()
 build()if args.build else census()

