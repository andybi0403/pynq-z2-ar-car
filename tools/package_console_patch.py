"""Create an immutable console software patch, reusing verified FPGA/MCU files."""
import ast
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / 'pynq_fpga/preintegration'
sys.path.insert(0, str(PRE))
from create_portable_zip import create_archive, verify_archive


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='v010_connection_stability_20261025_r6')
    parser.add_argument('--base',default='v010_connect_console_20261025_r5')
    parser.add_argument('--validation',default='validation/20261025_connection_stability_r6.md')
    parser.add_argument('--integrated-console',action='store_true')
    args=parser.parse_args()
    name=args.name
    if Path(name).name!=name or Path(args.base).name!=args.base:raise ValueError('package names required')
    validation=Path(args.validation)
    if validation.is_absolute() or '..' in validation.parts:raise ValueError('relative validation path required')
    validation_source=PRE/validation
    if not validation_source.is_file():raise FileNotFoundError(validation_source)
    base = ROOT / 'pynq_fpga/release' / args.base
    out = base.parent / name
    archive = out.with_suffix('.zip')
    if out.exists() or archive.exists():
        raise FileExistsError('refusing to overwrite existing candidate')
    verify_archive(base.with_suffix('.zip'))
    manifest = json.loads((base / 'lab_manifest.json').read_text('utf-8-sig'))
    old = json.loads((ROOT / 'pynq_fpga/release/v010_uart_role_fix_20261014_r3/lab_manifest.json').read_text('utf-8-sig'))
    shutil.copytree(base, out, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (out/validation).parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(validation_source,out/validation)
    for filename in manifest['runtime_files']:
        matches = [folder / filename for folder in
                   (PRE / 'host', ROOT / 'pynq_fpga/host', ROOT / 'stm32预备程序/pc')
                   if (folder / filename).is_file()]
        if len(matches) != 1:
            raise ValueError(f'expected one authoritative source for {filename}: {matches}')
        shutil.copyfile(matches[0], out / filename)
    tree = ast.parse((PRE / 'host/wireless_runtime.py').read_text('utf8'))
    wireless = next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'WIRELESS_FILES' for t in node.targets))
    for filename in wireless:
        shutil.copyfile(PRE / ('host/' + filename) if not filename.startswith('native/') else PRE / filename, out / filename)
    for group in ('runtime_files', 'wireless_files'):
        names = manifest[group] if group == 'runtime_files' else wireless
        manifest[group] = {filename: digest(out / filename) for filename in names}
    stamp = datetime.now(timezone.utc).isoformat()
    changes = {k: v for group in ('runtime_files', 'wireless_files') for k, v in manifest[group].items()
               if old.get(group, {}).get(k) != v}
    manifest.update(name='task7_8_LAB_ONLY_' + name, generated_at=stamp)
    manifest['software_patch_history'] = [*manifest.get('software_patch_history', []),
                                          *([manifest['software_revision']] if 'software_revision' in manifest else [])]
    manifest['software_revision'] = {
        'kind': 'SOFTWARE_PATCH_REUSING_VERIFIED_FPGA', 'name': name,
        'base_manifest_sha256': digest(base / 'lab_manifest.json'),
        'base_package': base.name, 'fpga_rebuilt': False,
        'preserves_base_classification': True, 'sources': changes,
        'validation': args.validation,
    }
    manifest.setdefault('sensor_console',{}).update(schema='car-sensor-console/v3',
        offline_launcher='console_launcher.html', diagnostic_startup=True,
        hardware_result='PENDING', encoder_movement_source='position count, not velocity sample sequence')
    for item in manifest['artifacts'].values():
        if digest(out / item['file']) != item['sha256']:
            raise ValueError('base artifact mismatch: ' + item['file'])
    (out / 'lab_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf8')
    if args.integrated_console:
        desktop_files={}
        desktop_sources=[*(('tools/'+f,ROOT/'tools'/f) for f in (
            'open_car_console.py','connect_car_console.py','car_network_probe.py',
            'car_connection_control.py','car_deploy_console.py','car_board_known_hosts',
            'verify_live_car_console.js')),
            ('使用说明.md',ROOT/'tools/car_receiver/使用说明.md'),
            ('nominal_scale_plan.json',ROOT/'work/ir_advisory_20261026/nominal_scale_plan.json'),
            *(('pynq_fpga/preintegration/host/'+f,PRE/'host'/f) for f in (
                'wireless_page.html','wireless_player.js','console_ui.js'))]
        for relative,source in desktop_sources:
            target=out/'desktop'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
            desktop_files['desktop/'+relative]=digest(target)
        entry=out/'desktop/打开完整控制台.pyw'
        entry.write_text("from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parent/'tools'))\nfrom open_car_console import main\nraise SystemExit(main())\n",'utf8')
        desktop_files['desktop/打开完整控制台.pyw']=digest(entry)
        console={'schema':'car-integrated-console/v1',
                 'classification':'CONTROLLED_CONSOLE_NOT_RELEASE',
                 'name':name,'generated_at':stamp,
                 'base_manifest_sha256':digest(out/'lab_manifest.json'),
                 'files':{f:digest(out/f) for f in ('console_backend.py','console_ui.js','trial_control.py','start_console.sh')},
                 'desktop_files':desktop_files,
                 'startup_mode':'observe_locked','automatic_release':False,
                 'infrared_policy':'warning_only',
                 'limits':{'pwm':400,'continuous_burst_s':1,'control_lease_ms':250},
                 'hardware_result':'PENDING','production_release_approved':False,
                 'validation':args.validation}
        (out/'console_manifest.json').write_text(json.dumps(console,ensure_ascii=False,indent=2)+'\n','utf8')
    (out / 'README.md').write_text('''# AR 小车连接与稳定测试上位机

电脑双击 `console_launcher.html`，粘贴 PYNQ 本次启动链接后连接。
板端在解压目录执行 `chmod +x start_sensor_console.sh && sudo ./start_sensor_console.sh`。
默认 1800 秒；电机动力保持物理断开。

此版本修复登录键盘、请求超时、同地址新令牌不登录、重连竞争和断线残留显示。
提供诊断启动、真实编码器位置、联调报告导出与最终测试操作说明。
采集启动检查未通过时可进入诊断页面，但摘要仍为失败。

第一次部署先执行 `python3 deployment_check.py --board` 和 `python3 lab_acceptance.py contract`。
如无 ARM 原生库，执行 `cmake -S native -B native-build -DCMAKE_BUILD_TYPE=Release`，
再执行 `cmake --build native-build --parallel 2`。
所需依赖仍为 Python 3.10+、PYNQ、pyserial、aiohttp、ffmpeg、原生库构建依赖。
启动脚本使用板端 PYNQ 虚拟环境，先加载本包 Overlay 并恢复 UART1，再运行完整上位机。
默认电机动力断开；显式连接诊断可使用 `SENSOR_CONSOLE_MOTOR_MODE=connected-zero-output`，
该模式据实记录动力未断开，保持锁车和零输出，不作为台架验收或驾驶许可。
板间协议、接线、bit/HWH、STM32 固件沿用 r5/r3 基线。

详细的连接排错、短联调、30 分钟长稳与演示步骤见 `SENSOR_CONSOLE_GUIDE.md`。
原始基线说明见 `README_R3_BASE.md`。
本次是软件修复，实板结果 PENDING，仍为 LAB_ONLY_NO_MOTOR_NON_RELEASE。
''', 'utf8')
    if args.integrated_console:
        (out/'README.md').write_text(f'''# PYNQ AR 小车完整控制台 {name}

完整页面整合驾驶总览、原图与真实 PL 图、同帧冻结、传感器与双轮标定、
手动操控、实际执行反馈、记录导出与历史回放、六阶段演示流程。
电脑双击 `desktop/打开完整控制台.pyw`（需 Python 3.10+ 和 Edge），
先打开本地完整界面，由操作者点击连接助手后才联网；连接助手另需 paramiko。
包内 `desktop/使用说明.md` 说明完整流程，工作区桌面程序为 `tools/open_car_console.py`。

此包为配套板端完整服务，未部署、未进行本包实车验收。
bit/HWH/STM32 固件来自本包指定的已核验构建基线；文件身份见两个 manifest。
`lab_manifest.json` 保留原台架入口的身份和分类，完整控制服务另由
`console_manifest.json` 绑定，不表示已有整车驾驶 release。

板端依赖及 native 库检查沿用 SENSOR_CONSOLE_GUIDE.md。
启动完整服务：`sudo sh start_console.sh`。默认记录动力连接、仅观察并保持锁车，
不自动解锁；需要有效实测标定、新鲜感知与实际锁车反馈后才允许手动接管及解锁。
动力物理断开后可用 `SENSOR_CONSOLE_MOTOR_MODE=disconnected sudo -E sh start_console.sh`，
也可在仅观察模式据实更新动力状态后应用标定。
PWM 上限 400，连续单次动作上限 1 秒；超时、松手、失焦和断链停车。
红外触发、失效或断线只提示，不参与停车或解锁判断；须使用本包配套 FPGA 和 STM32 固件。
默认会话 1800 秒，视频保留；硬件异常不会以假速度或假里程代替。

旧 `start_sensor_console.sh` 仍为只观察、零输出的台架入口。
完整功能与本地验证见包内 {args.validation}。
''','utf8')
    files = create_archive(out, archive)
    record = {'schema': 'car-sensor-console-candidate/v1', 'name': name, 'created_at': stamp,
              'status': 'SOFTWARE_READY_HARDWARE_PENDING', 'hardware_result': 'PENDING',
              'package_dir': str(out), 'zip': str(archive), 'zip_sha256': digest(archive),
              'manifest_sha256': digest(out / 'lab_manifest.json'),
              'software_revision': manifest['software_revision'],
              'artifacts': manifest['artifacts'], 'portable_archive_files': files}
    if args.integrated_console:
        record.update(schema='car-integrated-console-candidate/v1',
                      classification='CONTROLLED_CONSOLE_NOT_RELEASE',
                      console_manifest_sha256=digest(out/'console_manifest.json'))
    (PRE / ('sensor_console_candidate_'+name.rsplit('_',1)[-1]+'.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf8')
    (PRE / 'sensor_console_candidate.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf8')
    archive.with_suffix('.zip.sha256.txt').write_text(digest(archive) + '  ' + archive.name + '\n', 'ascii')
    print(json.dumps({'package': str(out), 'archive_files': files, 'sha256': digest(archive)}))


if __name__ == '__main__':
    main()
