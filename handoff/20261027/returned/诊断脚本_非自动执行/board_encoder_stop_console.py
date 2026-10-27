from pathlib import Path
import json,subprocess,time
unit='pynq-car-console.service'
assert '/home/xilinx/v011_uart_recovery_20261026_r17b' in Path('/etc/systemd/system/'+unit).read_text()
subprocess.run(['systemctl','stop','--no-block',unit],check=True,timeout=3)
deadline=time.monotonic()+25
while time.monotonic()<deadline:
 text=subprocess.check_output(['systemctl','show',unit,'-p','MainPID','-p','ActiveState','-p','SubState','-p','Result'],text=True)
 state=dict(line.split('=',1) for line in text.splitlines())
 if state.get('MainPID')=='0' and state.get('SubState') in ['dead','failed']:
  break
 time.sleep(.5)
else:raise RuntimeError('Console has not finished stopping; no register reads attempted')
print(json.dumps({'service':state,'motor_commands_sent':False,'scales_changed':False}))
