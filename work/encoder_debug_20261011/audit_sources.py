import hashlib, json
from pathlib import Path
root = Path('pynq_fpga')
package = root/'lab/task7_8_lab_only_v09_video_opt_20261011_r1'
manifest = json.loads((package/'lab_manifest.json').read_text('utf8'))
names = ['fpga/rtl/car_qei.v', 'fpga/rtl/car_qei_core.v', 'fpga/rtl/car_qei_velocity.v',
         'fpga/rtl/car_perception_top.v', 'fpga/rtl/car_board_video_wrapper.v',
         'fpga/board/board_manifest.json', 'fpga/registers/register_map.json',
         'host/perception_client.py', 'host/car_regs.py']
entries = []
for name in names:
    expected = manifest['source_identity']['sources'][name]
    actual = hashlib.sha256((root/name).read_bytes()).hexdigest()
    entries.append({'path': name, 'expected': expected, 'actual': actual, 'matched': actual == expected})
log = root/'preintegration/evidence/complete_v09_video_opt_20261011_r1/regression.log'
log_raw = log.read_bytes()
log_text = log_raw.decode('utf16' if log_raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig', errors='replace')
tests = [line for line in log_text.splitlines() if line.startswith('PASS: tb_car_') and any(name in line for name in ('qei ', 'qei_odometry ', 'velocity ', 'perception_arch '))]
result = {'manifest_sha256': hashlib.sha256((package/'lab_manifest.json').read_bytes()).hexdigest(),
          'contract': manifest['integrated_id'], 'tick_hz': manifest['source_identity']['tick_hz'],
          'sources': entries, 'all_sources_matched': all(e['matched'] for e in entries),
          'existing_same_candidate_simulation': tests,
          'new_rtl_regression_run': False, 'regression_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
          'pin_map': {'left_a': 'JB1/W14', 'left_b': 'JB2/Y14', 'right_a': 'JB3/T11',
                      'right_b': 'JB4/T10', 'oe_n': 'JA9/W18'}}
Path('work/encoder_debug_20261011/round2_source_audit.json').write_text(json.dumps(result, indent=2), 'utf8')
print(json.dumps(result, indent=2))
assert result['all_sources_matched']
