from pathlib import Path
import hashlib,json,zipfile,subprocess,sys,shutil,argparse
ROOT=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
validation=ROOT/'validation';validation.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--artifacts',type=Path,default=ROOT/'build/r3_artifacts');args=parser.parse_args()
binding=json.loads((args.artifacts/'artifact_source_binding.json').read_text('utf8'))
changes=[]
for name,before in binding['source_identity']['sources'].items():
    rel=name.removeprefix('workspace/') if name.startswith('workspace/') else 'pynq_fpga/'+name
    p=ROOT/rel
    if sha(p)!=before:
        if rel=='pynq_fpga/preintegration/native/car_video.c':
            native_patch=json.loads((ROOT/'native_camera_patch.json').read_text('utf8'))
            assert native_patch['path']==rel and native_patch['before']==before and native_patch['after']==sha(p), 'undeclared native source drift'
            native_receipt=json.loads((ROOT/'runtime/native/build_receipt.json').read_text('utf8'))
            assert native_receipt['source_sha256']==sha(p) and native_receipt['library_sha256']==sha(ROOT/'runtime/native/libcar_video.so'), 'native rebuild required'
        else:
            assert rel=='stm32预备程序/pc/pynq_link.py',f'unexpected build-source drift: {rel}'
        changes.append(dict(path=rel,before=before,after=sha(p)))
base=ROOT.parents[1]/'dist/v012_plain_motor_demo_20261028_r7_source.zip'
software=[]
with zipfile.ZipFile(base) as z:
    prefix=z.namelist()[0].split('/')[0]+'/'
    for folder in ['pynq_fpga/host','pynq_fpga/preintegration/host','stm32预备程序/pc','stm32_pynq对接版/Source/APP']:
        for p in (ROOT/folder).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix not in ('.py','.js','.html','.sh','.c','.h'):continue
            rel=p.relative_to(ROOT).as_posix()
            try:old=hashlib.sha256(z.read(prefix+rel)).hexdigest()
            except KeyError:old=None
            new=sha(p)
            if old!=new:software.append(dict(path=rel,base_r7_sha256=old,sha256=new))
report=dict(schema='demo-resilience-software-patch/v1',hardware='PENDING',
    control_mode='direct_manual',pl_role='telemetry only; independent UART control worker',
    video_policy=('1280x720 genuine PL pixels; two independent complete-frame native decoders, merged chroma upsampling, capture/output 25fps; PL JPEG 4:2:2 Q85; one source copy, identity-bound completion trailer; bounded decode/PL overlap; 200ms maximum frame age' if binding['source_identity']['video_profile']=='wireless720_jpeg' else 'profile '+binding['source_identity']['video_profile']+'; manual Q65; source cadence matched, newest-only bounded slots; strict frame age'),
    journal_policy='bounded asynchronous writer; batch 1s or 256KiB; critical FIFO flush; loss/error invalidates evidence; bounded immutable pickle snapshot on producer; JSON formatting on writer',
    policy=dict(forward_stop_mm=250,unknown_range='advisory; prior detected near retained until valid >250mm',
        network_intent_lease_ms=500,late_network_packet='drop without renewing lease',
        socket_disconnected='stop and require manual rearm',control_loop_max_age_ms=200,
        single_100ms_control_jitter='advisory',http_status_failure='independent from acknowledged control',
        internal_tab_change='zero output; retain ownership',console_duration_default_s=0),
    fpga_build=str(args.artifacts),fpga_source_changes=[],post_build_source_changes=changes,
    bit_sha256=sha(args.artifacts/'task7_8_LAB_ONLY.bit'),
    hwh_sha256=sha(args.artifacts/'task7_8_LAB_ONLY.hwh'),software_changes_from_r7=software)
(ROOT/'software_patch_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
tests=[
 *[['python','-m','unittest','discover','-s','tests','-p',name,'-v'] for name in
   ('test_tactical_filter_reference.py','test_tactical_snapshot.py','test_tactical_display_api.py')],
 *[['python','-m','unittest','discover','-s','pynq_fpga/preintegration/tests','-p',name,'-v'] for name in
   ('test_frame_metadata.py','test_console_health_page.py')],
 ['python','-m','unittest','discover','-s','tests','-p','test_uart_nonblocking.py','-v'],
 *[['python','-m','unittest','discover','-s','tests','-p',name,'-v'] for name in ('test_jpeg_parallel.py','test_native_parallel.py','test_hardware_jpeg_dma.py','test_hardware_jpeg_pipeline.py','test_uart_terminal_failure.py')],
 *[['python','-m','unittest','discover','-s','tests','-p',name,'-v'] for name in ('test_async_journal.py','test_async_journal_integration.py','test_video_statistics.py','test_video_scheduling.py')],
 ['python','-m','unittest','discover','-s','tests','-p','test_performance_batching.py','-v'],
 *[['python','-m','unittest','discover','-s','pynq_fpga/preintegration/tests','-p',name,'-v']
   for name in ('test_wireless.py','test_wireless_encode_queue.py','test_wireless_stale_pipeline.py',
                'test_wireless_cleanup.py','test_wireless_policy.py','test_wireless_startup.py')],
 ['python','-m','unittest','discover','-s','tests','-p','test_uart_clock_race.py','-v'],
 ['python','-m','unittest','discover','-s','tests','-p','test_direct_manual.py','-v'],
 ['python','-m','unittest','discover','-s','tests','-p','test_demo_resilience.py','-v'],
 ['python','test_integration_us250.py'],
 ['python','-m','unittest','discover','-s','pynq_fpga/host/tests','-p','test_supervisor_c_loop.py','-v'],
 ['python','-m','unittest','discover','-s','pynq_fpga/host/tests','-p','test_hybrid_c_loop.py','-v'],
 ['python','-m','unittest','discover','-s','pynq_fpga/preintegration/tests','-p','test_console_backend.py','-v'],
]
results=[]
for i,command in enumerate(tests):
    p=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf8',errors='replace')
    log=validation/f'resilience_test_{i}.log';log.write_text(p.stdout+p.stderr,'utf8')
    results.append(dict(command=command,returncode=p.returncode,log=str(log.relative_to(ROOT)),log_sha256=sha(log)))
    if p.returncode:print(p.stdout+p.stderr);sys.exit(p.returncode)
    if binding['source_identity']['video_profile']=='wireless720_jpeg' and 'test_native_parallel.py' in command and 'skipped=' in p.stderr:
        raise RuntimeError('720p native decoder acceptance requires the real compiled native library; set CAR_NATIVE_LIBRARY')
browser=subprocess.run(['node','tests/test_browser.js'],cwd=ROOT,capture_output=True,encoding='utf8',errors='replace',timeout=120)
(validation/'browser_regression.log').write_text(browser.stdout+browser.stderr,'utf8')
if browser.returncode:raise RuntimeError('Browser regression failed: '+browser.stderr[-2000:])
for gate,source in [('tactical_filter_gate.json','car_ultrasonic_display_filter.v'),('tactical_overlay_gate.json','car_axis_tactical.v')]:
    evidence=json.loads((validation/gate).read_text('utf8'))
    assert evidence.get('pass') is True and evidence['rtl_sha256']==sha(ROOT/'pynq_fpga/fpga/rtl'/source), 'stale RTL evidence: '+gate
lookup=json.loads((validation/'tactical_lookup_gate.json').read_text('utf8'))
assert lookup['pass'] and lookup['all_classifications_covered'] and lookup['boundary_cases']>=24664
assert lookup['rtl_sha256']==sha(ROOT/'pynq_fpga/fpga/rtl/car_ultrasonic_display_filter.v')
metadata=json.loads((validation/'tactical_metadata_gate.json').read_text('utf8'))
assert metadata.get('pass') is True and metadata.get('metadata_words')==24
for name,digest in metadata['sources'].items():assert sha(ROOT/name)==digest,'stale metadata evidence: '+name
chain=json.loads((validation/'tactical_chain_gate.json').read_text('utf8'))
assert chain.get('pass') is True and chain['geometry']==[1280,720] and chain['map_output_checked'] and chain['stale_map_disabled']
for name,digest in chain['sources'].items():assert sha(ROOT/name)==digest,'stale wrapper evidence: '+name
results.append(dict(command=['node','tests/test_browser.js'],result_file='validation/browser/browser-results.json',
                    sha256=sha(validation/'browser/browser-results.json')))
(validation/'resilience_tests.json').write_text(json.dumps(dict(hardware=False,results=results),indent=2),'utf8')
shutil.copy2(ROOT/'software_patch_manifest.json',ROOT/'runtime/software_patch_manifest.json')
print('Source drift constrained to declared host patch; regression logs saved')
