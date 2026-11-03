"""Bind and export a fresh, independent demo package. Never touch original releases."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,ast,hashlib,json,re,shutil,sys,zipfile,os
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'runtime'
def portable(p):
 return not any(part in {'__pycache__','work','evidence','board-setup','native-build','.pytest_cache','node_modules','xsim.dir','.Xil','obj'} for part in p.relative_to(ROOT).parts) and p.suffix not in ['.pyc','.wdb','.jou','.pb']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def literal(path,name):
 tree=ast.parse(path.read_text('utf8'))
 return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--artifacts',type=Path,required=True)
 parser.add_argument('--name',default='v012_plain_motor_demo_20261027_r2');parser.add_argument('--software-only',action='store_true');parser.add_argument('--reuse-fpga-from');args=parser.parse_args()
 if not re.fullmatch('[A-Za-z0-9_-]+',args.name):raise ValueError('simple package name required')
 artifacts=args.artifacts if args.artifacts.is_absolute() else ROOT/args.artifacts
 binding=json.loads((artifacts/'artifact_source_binding.json').read_text('utf8'))
 identity=binding['source_identity']
 os.environ['PYNQ_VIDEO_PROFILE']=identity['video_profile']
 build=artifacts.with_name(artifacts.name.removesuffix('_artifacts'))
 assert identity['integrated_id']=='0xC425100E' and identity['motor_profile']=='plain_motor_demo'
 if args.reuse_fpga_from:
  assert re.fullmatch('[A-Za-z0-9_-]+',args.reuse_fpga_from)
  prior=ROOT.parents[1]/'releases'/args.reuse_fpga_from
  for item in binding['artifacts'].values():
   assert sha(prior/item['file'])==item['sha256'],'FPGA reuse identity differs'
 out=ROOT/'dist';out.mkdir(exist_ok=True)
 archives=[out/(args.name+'.zip'),out/(args.name+'_source.zip')]
 if any(p.exists() for p in archives):raise FileExistsError('immutable archive already exists; choose a new name')
 prior_firmware_sha=sha(RUNTIME/'stm32_hybrid_v3.bin')
 for key,item in binding['artifacts'].items():
  assert sha(artifacts/item['file'])==item['sha256']
 for folder in [ROOT/'pynq_fpga/host',ROOT/'pynq_fpga/preintegration/host']:
  for p in folder.iterdir():
   if p.is_file() and p.name!='README.md' and ((RUNTIME/p.name).exists() or p.name in ('async_journal.py','video_profile.py','tactical_state.py','wireless_jpeg_dma.py','jpeg_parallel.py')):shutil.copy2(p,RUNTIME/p.name)
 license_dir=RUNTIME/'licenses';license_dir.mkdir(exist_ok=True)
 shutil.copy2(ROOT/'pynq_fpga/third_party/mjpegZero/LICENSE',license_dir/'mjpegZero_LICENSE.txt')
 shutil.copy2(ROOT/'pynq_fpga/third_party/mjpegZero/provenance.json',license_dir/'mjpegZero_provenance.json')
 shutil.copy2(ROOT/'assets/font/OFL.txt',license_dir/'NotoSansSC_OFL.txt')
 for name in ['bin','hex','elf']:
  shutil.copy2(ROOT/'stm32_pynq_firmware/build_safe'/('safe_car.'+name),RUNTIME/('stm32_hybrid_v3.'+name))
 shutil.copy2(ROOT/'stm32_tools/pc/pynq_link.py',RUNTIME/'pynq_link.py')
 for p in artifacts.iterdir():
  if p.is_file():shutil.copy2(p,RUNTIME/p.name)
 for name in ['car_video.c','CMakeLists.txt']:
  shutil.copy2(ROOT/'pynq_fpga/preintegration/native'/name,RUNTIME/'native'/name)
 for script in RUNTIME.glob('*.sh'):
  assert b'\r' not in script.read_bytes(), 'CRLF shell script: '+str(script)
 stamp=datetime.now(timezone.utc).isoformat()
 # RUNTIME_FILES is constructed from a tuple comprehension; import this pure module.
 sys.path.insert(0,str(RUNTIME))
 from runtime_identity import RUNTIME_FILES
 from wireless_runtime import WIRELESS_FILES
 from trial_control import PWM_LIMIT,DRIVE_LEASE_MS
 from hwh_contract import audit_hwh
 from wireless_dma import audit_wireless_hwh
 audit_hwh(RUNTIME/'task7_8_LAB_ONLY.hwh',require_placeholder=False)
 audit_wireless_hwh(RUNTIME/'task7_8_LAB_ONLY.hwh')
 manifest=json.loads((RUNTIME/'lab_manifest.json').read_text('utf8'))
 with zipfile.ZipFile(ROOT.parents[1]/'dist/v012_plain_motor_demo_20261028_r7.zip') as base_zip:
  base_hash=hashlib.sha256(base_zip.read('v012_plain_motor_demo_20261028_r7/lab_manifest.json')).hexdigest()
 if args.software_only:
  with zipfile.ZipFile(out/'v012_plain_motor_demo_20261027_r2.zip') as base_zip:
   base_hash=hashlib.sha256(base_zip.read('v012_plain_motor_demo_20261027_r2/lab_manifest.json')).hexdigest()
 manifest.update(name=args.name,generated_at=stamp,integrated_id='0xC425100E',video_profile=identity['video_profile'],
   source_identity=identity,build_parameters=identity['risk_parameters'],
   source_project=str(build/'task7_8_integrated.xpr'),
   runtime_files={n:sha(RUNTIME/n) for n in RUNTIME_FILES},wireless_files={n:sha(RUNTIME/n) for n in WIRELESS_FILES},
   profile={'name':'plain_motor_demo','encoders_required':False,'speed_display':False,'mileage':'estimated_actual_pwm_time','fixed_forward_stop_mm':250},
   physical_validation={k:False for k in manifest['physical_validation']},
   sensor_console={'schema':'car-sensor-console/v4','offline_launcher':'desktop/open_console.pyw','hardware_result':'PENDING','encoder_required':False},
   software_patch_history=[{'file':'software_patch_manifest.json','sha256':sha(RUNTIME/'software_patch_manifest.json'),'scope':'host/video changes bound to selected FPGA source identity'}],software_revision={'kind':'DIRECT_MANUAL_ISOLATED','name':args.name,'base_package':'v012_plain_motor_demo_20261028_r7','base_manifest_sha256':base_hash,'fpga_rebuilt':identity['video_profile'] in ('wireless360','wireless720_jpeg'),'fpga_reused_from':None if identity['video_profile'] in ('wireless360','wireless720_jpeg') else 'v013_plain_motor_demo_20261028_r3','validation':'validation/resilience_tests.json; validation/browser/browser-results.json; hardware pending'},
   firmware_revision={'kind':'US_250_UNKNOWN_ADVISORY','base_package':'v012_plain_motor_demo_20261028_r7','recompiled':False,'reflashed':False,'firmware_reused_from':'v013_plain_motor_demo_20261028_r3','wire_protocol':'Q1/S1/D1/R1 unchanged'})
 for key in ['bit','hwh']:
  p=RUNTIME/binding['artifacts'][key]['file'];manifest['artifacts'][key]={'file':p.name,'bytes':p.stat().st_size,'sha256':sha(p)}
 if args.reuse_fpga_from:
  manifest['software_revision'].update(fpga_rebuilt=False,fpga_reused_from=args.reuse_fpga_from)
 for ext in ['bin','hex','elf']:
  p=RUNTIME/('stm32_hybrid_v3.'+ext)
  assert sha(p)==sha(ROOT/'stm32_pynq_firmware/build_safe'/('safe_car.'+ext))
  manifest['artifacts']['stm32_'+ext]={'file':p.name,'bytes':p.stat().st_size,'sha256':sha(p)}
 build=artifacts.with_name(artifacts.name.removesuffix('_artifacts'))
 log_bytes=(build/'build_console.log').read_bytes()
 log=log_bytes.decode('utf-16' if log_bytes.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf8',errors='replace')
 assert 'PLAIN_MOTOR_FPGA_AND_HWH_PASS' in log and not re.search(r'^ERROR:',log,re.M)
 wns=float(re.findall(r'^TASK7_8_LAB_ONLY_WNS_NS=([-0-9.]+)',log,re.M)[-1])
 whs=float(re.findall(r'^TASK7_8_LAB_ONLY_WHS_NS=([-0-9.]+)',log,re.M)[-1]);assert min(wns,whs)>=0
 manifest['timing']={'wns_ns':wns,'tns_ns':0,'whs_ns':whs,'ths_ns':0}
 write(RUNTIME/'lab_manifest.json',manifest)
 desktop=RUNTIME/'desktop'
 for name in ['wireless_page.html','console_ui.js','wireless_player.js']:
  shutil.copy2(RUNTIME/name,desktop/'pynq_fpga/preintegration/host'/name)
 console={'schema':'car-integrated-console/v1','classification':'CONTROLLED_CONSOLE_NOT_RELEASE','name':args.name,
   'generated_at':stamp,'base_manifest_sha256':sha(RUNTIME/'lab_manifest.json'),
   'files':{n:sha(RUNTIME/n) for n in ['console_backend.py','console_ui.js','trial_control.py','start_console.sh']},
   'desktop_files':{p.relative_to(RUNTIME).as_posix():sha(p) for p in desktop.rglob('*') if p.is_file() and portable(p)},
   'profile':'plain_motor_demo','startup_mode':'locked_no_mode','control_flow':'claim_release','control_mode':'direct_manual','pl_guard_applied':False,'operation_mode_required':False,'automatic_release':False,'infrared_policy':'warning_only',
   'limits':{'pwm':PWM_LIMIT,'default_pwm':1800,'continuous_burst_s':None,'control_lease_ms':DRIVE_LEASE_MS},'hardware_result':'PENDING','production_release_approved':False,
   'encoder_required':False,'speed_display':False,'mileage':'estimated_actual_pwm_time','fixed_forward_stop_mm':250}
 write(RUNTIME/'console_manifest.json',console)
 # Bind all packaged support files as well as the runtime's minimum inventories.
 files=[p for p in RUNTIME.rglob('*') if p.is_file() and portable(p) and p.name!='package_inventory.json']
 write(RUNTIME/'package_inventory.json',{'schema':'plain-motor-package-inventory/v1','name':args.name,'files':{p.relative_to(RUNTIME).as_posix():sha(p) for p in sorted(files)}})
 with zipfile.ZipFile(archives[0],'x',zipfile.ZIP_DEFLATED) as z:
  for p in sorted([*files,RUNTIME/'package_inventory.json']):z.write(p,args.name+'/'+p.relative_to(RUNTIME).as_posix())
 # Hardware input identity plus the active software, firmware, tools, tests and docs.
 selected=set()
 for name in identity['sources']:
  rel=name.removeprefix('workspace/') if name.startswith('workspace/') else 'pynq_fpga/'+name
  p=ROOT/rel
  if p.is_file():selected.add(p)
 for name in ['runtime','tests','tools','validation','assets','delivery_docs','pynq_fpga/preintegration/tests','pending_joint_stop_100mm','stm32_pynq_firmware/Source','stm32_tools/pc']:
  for p in (ROOT/name).rglob('*'):
   if p.is_file() and portable(p) and p.suffix not in ['.pyc','.dll','.obj','.lib','.exp','.exe','.o','.pdb']:selected.add(p)
 for name in ['pynq_fpga/host','pynq_fpga/preintegration/host']:
  selected.update(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in ['.py','.html','.js','.sh','.json','.md','.txt','.ps1','.cmd','.c','.h'])
 for vendor in ['PYNQ','verilog-axi','mjpegZero']:
  for p in (ROOT/'pynq_fpga/third_party'/vendor).iterdir():
   if p.is_file() and (p.name in ['LICENSE','COPYING','THIRD_PARTY_LIC','AUTHORS','README.md']):selected.add(p)
 for p in ROOT.iterdir():
  if p.is_file() and p.name!='delivery_manifest.json':selected.add(p)
 for name in ['bin','hex','elf']:selected.add(ROOT/'stm32_pynq_firmware/build_safe'/('safe_car.'+name))
 with zipfile.ZipFile(archives[1],'x',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(selected):z.write(p,args.name+'_source/'+p.relative_to(ROOT).as_posix())
 receipt={'schema':'plain-motor-delivery/v1','name':args.name,'created_at':stamp,'integrated_id':'0xC425100E',
   'hardware_result':'PENDING','stm32_changed':sha(RUNTIME/'stm32_hybrid_v3.bin')!=prior_firmware_sha,'original_encoder_version_preserved':True,
   'runtime_inventory_sha256':sha(RUNTIME/'package_inventory.json'),
   'archives':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in archives}}
 write(ROOT/'delivery_manifest.json',receipt)
 print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
