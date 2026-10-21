import json,os,subprocess
from pathlib import Path
base=Path('/home/xilinx/video_opt_20261011_candidate_a')
p=Path('/sys/bus/iio/devices/iio:device0')
temp=(float((p/'in_temp0_raw').read_text())+float((p/'in_temp0_offset').read_text()))*float((p/'in_temp0_scale').read_text())/1000
print(json.dumps({'old_candidate_exists':base.is_dir(),'temperature_c':temp,
    'uptime_s':float(Path('/proc/uptime').read_text().split()[0]),
    'interfaces':subprocess.check_output(['ip','-brief','address'],text=True)}))
