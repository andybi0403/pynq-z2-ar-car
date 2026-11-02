"""Verify the v13 package plus declared post-build software changes. Read-only."""
from pathlib import Path
import hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 baseline=json.loads((ROOT/'baseline_preservation.json').read_text('utf8'))
 original=Path(baseline['original_root']);checked=0;unchanged=[]
 if original.exists():
  for name,expected in baseline['files'].items():
   if not (original/name).is_file() or sha(original/name)!=expected:unchanged.append(name)
   checked+=1
 assert not unchanged,unchanged
 runtime=ROOT/'runtime';sys.path.insert(0,str(runtime))
 from lab_acceptance import verify_package
 from wireless_runtime import verify_wireless
 from console_backend import verify_console
 p=verify_package(runtime/'task7_8_LAB_ONLY.bit',runtime/'task7_8_LAB_ONLY.hwh',runtime/'lab_manifest.json')
 verify_wireless(runtime/'lab_manifest.json',runtime/'task7_8_LAB_ONLY.hwh');verify_console(runtime,runtime/'lab_manifest.json')
 assert p['integrated_id']=='0xC425100E' and p['profile']['encoders_required'] is False
 for ext in ['hex','bin','elf']:
  assert sha(runtime/('stm32_hybrid_v3.'+ext))==sha(ROOT/'stm32_pynq对接版/build_safe'/('safe_car.'+ext))
 inventory=json.loads((runtime/'package_inventory.json').read_text('utf8'))
 for name,expected in inventory['files'].items():assert sha(runtime/name)==expected,name
 binding=json.loads((runtime/'artifact_source_binding.json').read_text('utf8'))
 patch=json.loads((runtime/'software_patch_manifest.json').read_text('utf8'))
 delta={item['path']:item for item in patch['post_build_source_changes']}
 assert set(delta)<={'stm32预备程序/pc/pynq_link.py'}
 for item in binding['artifacts'].values():assert sha(runtime/item['file'])==item['sha256']
 for name,expected in binding['source_identity']['sources'].items():
  rel=name.removeprefix('workspace/') if name.startswith('workspace/') else 'pynq_fpga/'+name
  if rel in delta:
   assert expected==delta[rel]['before'] and sha(ROOT/rel)==delta[rel]['after']
  else:assert sha(ROOT/rel)==expected,'undeclared built source changed: '+rel
 for item in patch['software_changes_from_r7']:assert sha(ROOT/item['path'])==item['sha256']
 for item in p['software_patch_history']:assert sha(runtime/item['file'])==item['sha256']
 receipt=json.loads((ROOT/'delivery_manifest.json').read_text('utf8')) if (ROOT/'delivery_manifest.json').is_file() else {'archives':{}}
 for name,info in receipt['archives'].items():
  archive=ROOT/'dist'/name
  if archive.is_file():
   assert sha(archive)==info['sha256'],name
   with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 print(json.dumps({'passed':True,'original_files_checked':checked,'original_encoder_files_changed':0,
  'stm32_firmware_changed':True,'post_build_software_changes':len(delta),'package_files':len(inventory['files']),
  'integrated_id':p['integrated_id'],'hardware_result':'PENDING'},ensure_ascii=False))
 return 0
if __name__=='__main__':raise SystemExit(main())
