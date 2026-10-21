"""Independent read-only check of the completed candidate and transfer ZIP."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT/'preintegration/host'))
sys.path.insert(0,str(ROOT/'preintegration'))
from source_provenance import check, sha256
from lab_acceptance import verify_package

candidate=json.loads((ROOT/'preintegration/latest_candidate.json').read_text(encoding='utf-8-sig'))
assert candidate['name']=='v09_front_20261001_r1',candidate['name']
assert candidate['status']=='LAB_ONLY_CANDIDATE' and candidate['hardware']=='PENDING'
folder=Path(candidate['package_dir']);evidence=Path(candidate['evidence_dir']);build=Path(candidate['build_dir'])
source=check(evidence/'source_start.json')
assert check(build/'source_contract.json')==source
feature_hashes=json.loads((OUT/'feature_source_hashes.json').read_text(encoding='utf-8'))
for name,digest in feature_hashes.items():
    assert sha256(ROOT/name)==digest,name
    assert source['sources'][name]==digest,name
assert 'front_overlay' in (ROOT/'fpga/rtl/car_board_video_wrapper.v').read_text(encoding='utf-8')

for stage in candidate['stages']:
    assert stage['status']=='PASS',stage
    assert sha256(evidence/(stage['name']+'.log'))==stage['log_sha256'],stage['name']
assert sha256(candidate['zip_path'])==candidate['zip_sha256']
package=verify_package(folder/'task7_8_LAB_ONLY.bit',folder/'task7_8_LAB_ONLY.hwh',folder/'lab_manifest.json')
assert package['source_identity']==source
binding=json.loads((folder/'artifact_source_binding.json').read_text(encoding='utf-8-sig'))
assert binding['source_identity']==source
for key in ('bit','hwh'):
    assert sha256(folder/binding['artifacts'][key]['file'])==binding['artifacts'][key]['sha256']
with zipfile.ZipFile(candidate['zip_path']) as archive:
    assert archive.testzip() is None
    members=[m for m in archive.infolist() if not m.is_dir()]
    assert len(members)==len({m.filename for m in members})
    assert {m.filename for m in members}=={p.name for p in folder.iterdir() if p.is_file()}
    for member in members:
        assert hashlib.sha256(archive.read(member)).hexdigest()==sha256(folder/member.filename),member.filename
timing=package['timing']
assert timing['wns_ns']>=0 and timing['whs_ns']>=0 and timing['tns_ns']==0 and timing['ths_ns']==0
raw_regression=(evidence/'regression.log').read_bytes()
regression=raw_regression.decode('utf-16' if raw_regression.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig',errors='replace')
assert 'ARCHITECTURE_SOFTWARE_RTL_PASS (not hardware acceptance)' in regression
assert 'MODULE_SYNTHESIS_COMPLETED' in regression
for marker in ('SUPERVISOR_FAULT_MATRIX_PASS (14 scenarios;',
               'FRAME_DISPLAY_CHAIN_PIXEL_PASS', 'FRONT_OVERLAY_PIXEL_PASS', 'STATUS_OSD_PIXEL_PASS',
               'COMPARE PASSED (all scenarios pixel-exact)', '[ok] 640x480: pixel-exact'):
    assert marker in regression,marker
python_counts=[int(n) for n in re.findall(r'Ran (\d+) tests in',regression)]
rtl=re.findall(r'PASS: (tb_\w+) simulation \((\d+) checks\)',regression)
assert python_counts==[20,105,78],python_counts
assert len(rtl)==15,rtl
drc={}
for path in (build/'drc_integrated_impl.rpt',folder/'drc_LAB_ONLY.rpt'):
    rows=re.findall(r'\|\s*([A-Z]+-\d+)\s*\|\s*(Advisory|Warning|Critical Warning|Error)\s*\|[^\n]*?\|\s*(\d+)\s*\|',path.read_text(errors='replace'))
    assert rows,path
    assert all(severity=='Advisory' for _,severity,_ in rows),rows
    drc[path.name]=[{'rule':rule,'severity':severity,'checks':int(n)} for rule,severity,n in rows]
ooc={}
(OUT/'ooc_reports').mkdir(exist_ok=True)
for name in ('car_qei_top','car_sensors_top','car_axil_regs','car_risk_core','car_perception_top',
             'car_axis_osd','car_axis_front_overlay','car_axis_status_osd','car_axis_frame_metadata','car_board_video_wrapper'):
    path=ROOT/'fpga/build/acceptance_synth'/f'{name}_timing.rpt'
    match=re.search(r'Setup\s*:[^\n]*Worst Slack\s+(-?[0-9.]+)ns',path.read_text(errors='replace'))
    assert match and float(match.group(1))>=0,name
    ooc[name]=float(match.group(1))
    for suffix in ('timing','utilization'):
        src=path.with_name(f'{name}_{suffix}.rpt')
        shutil.copyfile(src,OUT/'ooc_reports'/src.name)
route_log=(build/'task7_8_integrated.runs/impl_1/runme.log').read_text(errors='replace')
assert re.findall(r'Number of Unrouted Nets\s*=\s*(\d+)',route_log)[-1]=='0'
assert re.findall(r'Number of Partially Routed Nets\s*=\s*(\d+)',route_log)[-1]=='0'
assert 'route_design completed successfully' in route_log
resource=(build/'utilization_integrated_impl.rpt').read_text(errors='replace')
resources={}
for key in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'):
    match=re.search(r'\|\s*'+re.escape(key)+r'\*?\s*\|\s*([0-9.]+)',resource)
    resources[key]=None if match is None else float(match.group(1))
result={'schema':'car-front-overlay-final-check/v1','passed':True,'candidate':candidate['name'],
        'source_files_bound':len(source['sources']),'feature_source_files_verified':len(feature_hashes),'stage_logs_verified':len(candidate['stages']),
        'runtime_sources_verified':len(package['runtime_files']),'zip_members_verified':len(members),
        'zip_sha256':candidate['zip_sha256'],'timing':timing,'resources':resources,
        'drc':drc,'ooc_setup_slack_ns':ooc,'unrouted_nets':0,'partially_routed_nets':0,
        'python_test_counts':python_counts,'rtl_tests':[{'name':n,'checks':int(c)} for n,c in rtl],
        'hardware':'PENDING','classification':package['classification']}
(OUT/'final_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
