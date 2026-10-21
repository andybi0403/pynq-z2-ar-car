from pathlib import Path
import json,hashlib,zipfile,datetime
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
PACKAGE=ROOT/'pynq_fpga/lab/task7_8_lab_only_v010_uart_role_fix_20261014_r3'
def read(name):return json.loads((OUT/name).read_text('utf8'))
startup=read('startup_entry_update.json');boot=read('reboot_startup_entry_proof.json');trial=read('reboot_acceptance_summary.json');audit=read('reboot_independent_audit.json')
assert audit['passed'] and boot['initial_UART_driver_absent'] and trial['passed']
assert trial['final_risk_enable']==0 and trial['final_scale']==[0,0]
text=(OUT/'FINAL_RESULT.md').read_text('utf8')
addition=f"""
## PYNQ重启与日常启动入口

已备份并修正`/home/xilinx/stm32_sensors_platform_20261013/prepare_hybrid.py`和`start_hybrid.sh`，两者现指向r3；仅替换包目录，Python编译与shell语法检查通过。旧入口存于平台目录`startup_before_uart_role_fix_20261014`。

实际重启PYNQ后，系统自动登录。监测程序最初等待手动登录，超时记录保留；启动日志确认已正常启动。重启后`/dev/ttyPS1`确实尚未启用；运行更新后的prepare入口，重新加载同版Overlay和UART设备树，调试串口保持可用。随后30秒正式链路收到{trial['state_reports']}条有效回传，协议错误0；{trial['samples']}次PL快照中，US有效{trial['valid_us_pl_samples']}次、IR有效{trial['valid_ir_pl_samples']}次。独立审核通过，最终LOCK=1、实际PWM=0、风险许可0、双轮SCALE=0。

证据：`startup_entry_update.json`、`pynq_reboot_automatic_login_proof.json`、`reboot_startup_entry_proof.json`、`reboot_independent_audit.json`。这是现有手动启动入口的重启恢复验证；没有新增上电自动运行服务。
"""
assert '## PYNQ重启与日常启动入口' not in text
text+=addition
(OUT/'FINAL_RESULT.md').write_text(text,encoding='utf8')
(PACKAGE/'UART_ROLE_FIX_README.md').write_text(text,encoding='utf8')
res=json.loads((PACKAGE/'UART_ROLE_FIX_RESULT.json').read_text('utf8'))
res['PYNQ_reboot_uart_PL']=audit;res['startup_entry']=boot
(PACKAGE/'UART_ROLE_FIX_RESULT.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf8')
startupdir=PACKAGE/'startup';startupdir.mkdir(exist_ok=True)
for name in ['prepare_hybrid.py','start_hybrid.sh']:
 (startupdir/name).write_bytes((OUT/name).read_bytes())
(PACKAGE/'startup/ENTRY_SHA256.json').write_text(json.dumps({x['path']:x['after_sha256'] for x in startup['entries']},indent=2),encoding='utf8')
comp=read('completion_audit.json')
comp['requirements'].append(dict(requirement='日常入口指向修复版且PYNQ重启后可重新启用UART恢复实测通信',evidence=['startup_entry_update.json','reboot_startup_entry_proof.json','reboot_independent_audit.json'],proved=True))
comp['all_requirements_proved']=all(x['proved'] for x in comp['requirements']);comp['timestamp_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
(OUT/'completion_audit.json').write_text(json.dumps(comp,ensure_ascii=False,indent=2),encoding='utf8')
progress=read('progress.json');progress['final_verification']['PYNQ_reboot']='reboot_independent_audit.json';progress['final_verification']['startup_entry']='startup_entry_update.json'
(OUT/'progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf8')
index=ROOT/'pynq_fpga/preintegration/current_verified_uart_runtime.json';i=json.loads(index.read_text('utf8'));i['board_startup_entry']='/home/xilinx/stm32_sensors_platform_20261013/start_hybrid.sh';i['PYNQ_reboot_reinitialization_verified']=True
index.write_text(json.dumps(i,ensure_ascii=False,indent=2),encoding='utf8')
old=read('final_package_audit.json');zip_path=Path(old['zip']);assert hashlib.sha256(zip_path.read_bytes()).hexdigest()==old['sha256']
files=sorted(p for p in PACKAGE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
temp=zip_path.with_suffix('.finishing.zip');assert not temp.exists()
with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.write(p,p.relative_to(PACKAGE).as_posix())
with zipfile.ZipFile(temp) as z:
 assert len(z.namelist())==len(files)
 for p in files:assert z.read(p.relative_to(PACKAGE).as_posix())==p.read_bytes()
temp.replace(zip_path)
old.update(files=len(files),sha256=hashlib.sha256(zip_path.read_bytes()).hexdigest(),startup_entry_included=True)
(OUT/'final_package_audit.json').write_text(json.dumps(old,indent=2),encoding='utf8')
print(json.dumps(dict(all_requirements_proved=comp['all_requirements_proved'],zip_sha256=old['sha256'],files=len(files)),indent=2))
