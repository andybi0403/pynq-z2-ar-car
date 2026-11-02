"""Run the demo's affected regressions; never access UART or load PL."""
from pathlib import Path
import argparse,json,subprocess,sys,time,os,shutil
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--rtl',action='store_true');args=p.parse_args()
 out=ROOT/'validation'/('regression_'+time.strftime('%Y%m%d_%H%M%S'));out.mkdir(parents=True)
 commands=[
  ['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','pynq_fpga/host/c_build/build_car_c_dll.ps1'],
  [sys.executable,'-m','unittest','discover','-s','tests','-p','test_plain_motor.py','-v'],
  [sys.executable,'-m','unittest','discover','-s','tests','-p','test_driving_policy.py','-v'],
  [sys.executable,'-m','unittest','discover','-s','pynq_fpga/host/tests','-p','test_control_supervisor.py','-v'],
  [sys.executable,'-m','unittest','discover','-s','pynq_fpga/preintegration/tests','-p','test_console_backend.py','-v'],
  [sys.executable,'-m','unittest','discover','-s','pynq_fpga/host/tests','-p','test_supervisor_c_loop.py','-v'],
  [sys.executable,'-m','unittest','discover','-s','pynq_fpga/host/tests','-p','test_hybrid_c_loop.py','-v'],
  ['node','tests/test_browser.js']]
 if (ROOT/'pending_joint_stop_100mm').exists():
  commands.extend([
   ['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','pending_joint_stop_100mm/pynq_fpga/host/c_build/build_car_c_dll.ps1'],
   [sys.executable,'-m','unittest','discover','-s','tests','-p','test_joint_stop_candidate.py','-v']])
 if args.rtl:
  for top in ['tb_plain_motor_demo','tb_car_external_sensors','tb_car_frame_metadata','tb_plain_motor_hud']:
   commands.append(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','pynq_fpga/fpga/scripts/run_sim.ps1',
                    '-Top',top,'-TbFile',('../../../tests/' if top=='tb_plain_motor_hud' else '')+top+'.sv'])
 rows=[]
 for i,cmd in enumerate(commands):
  env=os.environ.copy()
  if cmd[0]=='powershell':cmd[0]=shutil.which('pwsh') or cmd[0]
  result=subprocess.run(cmd,env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=180)
  (out/f'{i:02d}.log').write_text(result.stdout+result.stderr,'utf8')
  rows.append({'command':cmd,'returncode':result.returncode,'log':str((out/f'{i:02d}.log').relative_to(ROOT))})
  print(('PASS ' if result.returncode==0 else 'FAIL ')+str(cmd[-1]))
  if result.returncode:break
 record={'hardware':False,'scope':'affected software, actual-C and browser regressions; optional RTL',
         'commands':rows,'passed':len(rows)==len(commands) and all(r['returncode']==0 for r in rows)}
 (out/'results.json').write_text(json.dumps(record,indent=2)+'\n','utf8')
 print('RESULT '+str(out/'results.json'))
 return 0 if record['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
