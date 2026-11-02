from pathlib import Path
import json,subprocess,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'pynq_fpga'
B=ROOT/'build/demo_hud_gate';B.mkdir(parents=True,exist_ok=True)
BIN=Path('C:/AMDDesignTools/2026.1/Vivado/bin')
shutil.copy2(P/'fpga/rtl/font_24x24_demo.mem',B)
commands=[['xvlog.bat','--sv',str(P/'fpga/rtl/car_axis_demo_hud.v'),str(P/'fpga/tb/tb_car_demo_hud.sv')],['xelab.bat','tb_car_demo_hud','-s','hud'],['xsim.bat','hud','-runall']]
for n,cmd in enumerate(commands):
 cmd[0]=str(BIN/cmd[0]);r=subprocess.run(cmd,cwd=B,capture_output=True,text=True,timeout=120)
 log=r.stdout+r.stderr;(B/f'step{n}.log').write_text(log,'utf8');assert r.returncode==0,log[-2500:]
assert 'TEST PASSED' in log and 'TEST FAILED' not in log,log[-2500:]
chars=json.loads((P/'fpga/rtl/font_24x24_demo.json').read_text('utf8'))['chars']
font=[int(x,16) for x in (P/'fpga/rtl/font_24x24_demo.mem').read_text().splitlines()]
cases=[['前方距离:  48.7 cm','是否锁车: 是','车辆左方状态: 正常','车辆右方状态: 过近'],
 ['前方距离: --    cm','是否锁车: --','车辆左方状态: --','车辆右方状态: --'],
 ['前方距离: 109.5 cm','是否锁车: 否','车辆左方状态: 过近','车辆右方状态: 正常'],
 ['前方距离: 409.5 cm','是否锁车: 否','车辆左方状态: 过近','车辆右方状态: 过近']]
for n,labels in enumerate(cases,1):
 expected=[0x112233]*(480*200)
 for row,label in enumerate(labels):
  for col,ch in enumerate(label.ljust(14)):
   for y in range(24):
    word=font[chars.index(ch)*32+y]
    for x in range(24):
     bit=1<<(23-x);index=(40+row*40+y)*480+24+col*24+x
     if (word>>24)&bit:expected[index]=0xffffff
     elif word&bit:expected[index]=0x101010
 actual=[int(x,16) for x in (B/f'status_f{n}.rgb').read_text().splitlines()]
 assert len(actual)==len(expected)
 bad=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
 assert not bad,(n,len(bad),bad[:8])
result={'pass':True,'frames':4,'pixels_compared':4*480*200,'random_backpressure':True,'midframe_changes_latched_at_SOF':True,'cases':cases,'rtl_sha256':hashlib.sha256((P/'fpga/rtl/car_axis_demo_hud.v').read_bytes()).hexdigest()}
(ROOT/'validation/demo_hud_gate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8');print(json.dumps(result,ensure_ascii=True))
