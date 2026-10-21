import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
out=Path('C:/Users/39909/Documents/Codex/2026-10-11/p-g/outputs/qei_algorithm_20261012')
pipeline_path=ROOT/'pynq_fpga/preintegration/evidence/complete_v09_qei_quality_20261012_r1/pipeline.json'
p=json.loads(pipeline_path.read_text('utf8'))
assert p['status']=='LAB_ONLY_CANDIDATE' and all(s['status']=='PASS' for s in p['stages'])
trial=json.loads((out/'台架复测结果.json').read_text('utf8'))
deploy=json.loads((out/'qei_quality_20261012_candidate_r1.json').read_text('utf8'))
assert deploy['returncode']==0 and deploy['receipt']['board_files_exactly_match_candidate']
assert trial['completed'] and trial['safe_unconfigured']
for source,name in ((pipeline_path,'完整构建流水线.json'),
    (Path(p['evidence_dir'])/'regression.log','完整回归日志.txt'),
    (Path(p['zip_path']),'v09_qei_quality_20261012_r1_LAB_ONLY.zip'),
    (ROOT/'work/qei_opt_20261011/board_trial.py','板端复测脚本.py')):
    destination=out/name
    if destination.exists():assert destination.read_bytes()==source.read_bytes()
    else:shutil.copy2(source,destination)
assert hashlib.sha256((out/'v09_qei_quality_20261012_r1_LAB_ONLY.zip').read_bytes()).hexdigest()==p['zip_sha256']
package=Path(p['package_dir']);manifest=json.loads((package/'lab_manifest.json').read_text('utf-8-sig'))
software=out/'算法源码';software.mkdir(exist_ok=False)
for name in ('qei_quality.py','perception_client.py','perception_replay.py','system_runtime.py','wireless_runtime.py','frame_metadata.py','joint_evidence.py','runtime_identity.py','README.md'):
    shutil.copy2(package/name,software/name)
left,right=trial['channels']['left'],trial['channels']['right']
rows='\n'.join(f"| {name} | {v['net_delta']} | {v['illegal_start']} → {v['illegal_end']} | {v['quality_fault_samples']} | {v['faulted_samples_displayed_as_valid']} |" for name,v in (('左路',left),('右路',right)))
text=f'''# 编码器算法优化与台架复测

2026-10-12。已修改程序、完成同源构建，并通过 COM14 部署到 PYNQ。候选为 `v09_qei_quality_20261012_r1`，契约仍为 `{trial['contract_id']}`。电机动力沿用本会话已断开的确认；本次不发送电机命令，不进行行驶验证。电脑 Wi-Fi 未切换。

| 改动 | 实际行为 |
|---|---|
| 输入稳定滤波 | 使用现有 PL 滤波器，两路 1000 tick / 10 微秒。设置前要求电机动力断开、两路 SCALE=0，设置后回读验证；已有完整标定不被自动覆盖。 |
| 质量拒绝 | 非法跳变计数非零或达到 255、里程故障、速度算术饱和时，拒绝该观测。有效位恢复不能抹掉累计故障。控制、启动检查和历史视频速度有效标记共用此判断。 |
| 显示中值 | 浏览器即时速度用最近三批新接受的、有效且质量合格的观测取中值。重复读取不增加样本；当前输入异常/过期或配置 epoch 改变会清空历史。中值保留被选中观测的时间戳，中值过期也停止显示；显示值不进入控制。 |
| 原始证据 | 原始计数、速度、诊断、批次和时间戳继续保留；无效显示 null / 不可用，不伪造有效零速。历史视频保留原始速度及有效标记，不额外平滑。 |

验证：121 项主机测试、147 项运行程序测试通过；完整流水线的 C/PC 回归、RTL 仿真、综合、实现、时序/DRC/HWH 检查及打包均通过，共 {len(p['stages'])} 个阶段。针对性覆盖单点尖峰、连续异常、方向反转、时间戳/序号回绕、重复读取、旧中值过期、配置变化、回读失败，以及真实生产 C 锁存逻辑的离线联动。C 联动测试证明离线夹具中故障会触发锁存，清除诊断不会自动重新驱动；不是电机实测结果。

上一轮真实原始记录回放：右路 3449 条全部因非法跳变被质量检查拒绝，143 条还存在速度算术饱和；保留右路 +19270 的原始漂移。旧记录缺少里程故障和完整 QEI 时间戳，此回放只检验已有诊断，不冒充完整控制/显示会话。见 `历史原始数据质量回放.json`。

本次板端采样：{trial['samples']} 条，实测 {trial['observed_seconds']:.2f} 秒，临时名义 SCALE={trial['temporary_scales']}，未经滚轮标定，仅用来暴露速度和故障。

| 通道 | 原始净计数变化 | 非法跳变计数 | 质量故障样本 | 故障却被显示为有效的样本 |
|---|---:|---:|---:|---:|
{rows}

控制放行次数为 {trial['unexpected_control_permits']}；这是风险关闭的无电机诊断，不等于带电机停止距离验收。结束寄存器：`{trial['final_registers']}`。两路 SCALE 已清零，RISK_ENABLE=0；10 微秒滤波作为新的台架候选设置保留。板温 {trial['temperature_start_c']:.1f}℃ → {trial['temperature_end_c']:.1f}℃。

算法能拒绝带诊断的坏数据，并抑制孤立显示尖峰；不能从持续乱跳恢复真实距离，也不能识别所有符合正交顺序的伪脉冲。这一轮的安静结果（如有）不能推翻前几轮间歇性噪声。真实方向、每圈计数、低速/高速计数损失、10 微秒滤波延迟与机械滚动标定仍待验证。排除输入故障后明确重载 Overlay、应用已测标定，并按既有控制流程人工重新使能；不自动清错或恢复驱动。

候选仍为 **LAB_ONLY_NO_MOTOR_NON_RELEASE**，完整构建通过不代表硬件发布验收通过。

- 原始采集 SHA-256：`{trial['raw_archive']['sha256']}`，文件 `台架原始采集.jsonl`。
- bit SHA-256：`{trial['bit_sha256']}`。
- 完整 ZIP SHA-256：`{p['zip_sha256']}`。
- 每个板端文件与完整候选逐一校验相符：`qei_quality_20261012_candidate_r1.json`。
- 新包、改动后的源码、构建日志和原始证据均在本目录；旧候选留存供回退。
'''
report=out/'算法优化与台架复测报告.md';assert not report.exists();report.write_text(text,'utf8')
print(str(report))
