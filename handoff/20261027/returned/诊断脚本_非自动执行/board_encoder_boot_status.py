from pathlib import Path
import json,subprocess
result={'uptime':Path('/proc/uptime').read_text().strip(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
for key,args in {
 'service':['systemctl','show','pynq-car-console.service','-p','MainPID','-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStartTimestampMonotonic'],
 'uart_owners':['fuser','/dev/ttyPS1'],
 'shutdown_timer':['systemctl','is-active','encoder-wiring-poweroff-20261027.timer'],
}.items():
 p=subprocess.run(args,capture_output=True,text=True,timeout=3)
 result[key]={'returncode':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr.strip()}
path=Path('/sys/class/fpga_manager/fpga0/state')
result['fpga_state']=path.read_text().strip() if path.exists() else None
print(json.dumps(result))
