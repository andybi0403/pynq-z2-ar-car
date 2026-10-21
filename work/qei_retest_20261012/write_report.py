"""Write final reports only after verified deployment and both real trials."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'pynq_fpga/preintegration/evidence/qei_retest_20261012'
pipeline=ROOT/'pynq_fpga/preintegration/evidence/complete_v09_qei_retest_20261012_r2/pipeline.json'
p=json.loads(pipeline.read_text('utf8'))
assert p['status']=='LAB_ONLY_CANDIDATE' and all(s['status']=='PASS' for s in p['stages'])
receipt=json.loads((OUT/'qei_retest_20261012_candidate_r2.json').read_text('utf8'))
assert receipt['returncode']==0 and receipt['receipt']['board_files_exactly_match_candidate']
trials=[json.loads((OUT/name/'result.json').read_text('utf8')) for name in ('round1','round2')]
audits=[json.loads((OUT/name/'independent_audit.json').read_text('utf8')) for name in ('round1','round2')]
timing=json.loads((OUT/'routed_timing_audit.json').read_text('utf8'))
assert all(a['containment_pass'] for a in audits)
rows=[]
for i,(trial,audit) in enumerate(zip(trials,audits),1):
    for label,side in (('左','left'),('右','right')):
        c=audit['channels'][side]
        rows.append(f"| {i} | {trial['observed_seconds']:.2f} | {trial['samples']} | {label} | {c['net_delta']} | {c['observed_abs_delta']} | {c['illegal_first']} → {c['illegal_last']} | {c['bad_display_valid_samples']} |")
table='\n'.join(rows)
inputs_clean=all(a['stationary_input_pass'] for a in audits)
text=f'''# 编码器两轮上板实测与优化报告

任务于 2026-10-12 发起，跨夜完成于 2026-10-13。两轮代码优化和两轮实际 PYNQ 台架采集均已完成。软件故障隔离通过，当前两轮输入稳定性结论为 **{'通过本次静止观察，运动标定仍待测' if inputs_clean else '未通过，仍需接线与电气隔离'}**。不能据此宣布编码器或整车稳定。

## 两轮实测

用户在本次聊天直接确认电机动力线物理断开且无人转轮。通过 COM14 调试 UART 执行；电脑网络未修改；两轮都重新加载经过 manifest 核验的 Overlay，使用原 10 微秒滤波及临时名义左右 SCALE=5362。名义比例仅用于暴露速度和位置，未作为实际滚动标定。

第一轮是上一完整候选 `v09_qei_quality_20261012_r1` 的 300 秒基线；同时完成第一轮诊断修复。第二轮在第二轮显示算法优化及完整构建之后，部署新候选 `v09_qei_retest_20261012_r2`，采集 480 秒。两轮不是同一段日志拆分。

| 轮次 | 实测秒数 | 采样数 | 通道 | 原始净计数变化 | 点间变化绝对和 | 非法计数起止 | 故障却显示有效 |
|---:|---:|---:|---|---:|---:|---|---:|
{table}

点间变化绝对和仅是采样快照间可见变化，不能当全部边沿计数；8 位非法计数到 255 后饱和，不能据差值计算全部错误。完整数据、异常段及故障前后的有效位均保留在 `round1/samples.jsonl` 和 `round2/samples.jsonl`，独立核验分别在 `independent_audit.json`。

两轮控制许可次数均为 0，故障观测被显示为有效的次数均为 0。最终双轮 SCALE=0、RISK_ENABLE=0 且读回确认；没有发送电机命令。这是在风险许可禁用的断电机台架条件下完成，不是停车距离、UART STOP 或整车行驶实测。

## 第一轮优化：速度过载诊断

`car_qei_core.v` 与独立 `car_qei_top.v` 原本直接截取 16 位过载计数的低 8 位，累计 256 次时对外变成 0。修复后输出在 255 饱和，内部 16 位累计计数仍保留。寄存器地址、位宽与单位不变，属于既有诊断字段回绕缺陷修正。

主机公共质量判断加入速度计算过载及其诊断饱和拒绝，控制评估、即时显示、历史帧有效标记及联合审核沿用同一质量函数。计算器完成后速度有效位恢复，不再掩盖已累计的过载。滤波拒绝计数本身仍不直接判故障，以免正常滤波动作被误判。

新增 `tb_car_qei_diagnostics` 用真实合法正交输入制造计算过载，未强制内部计数。774 项检查覆盖 255、256、257 以及计算恢复后的累计诊断，并进入正式回归。第一轮主机针对性测试 13 项通过。该漏洞在代码和 RTL 仿真中被证实；两轮实测过载计数均为 0，这项修复补齐了代码漏洞，不能据此解释本次非法输入或认定昨日突变根因已解决。

## 第二轮优化：显示批次与反转

三批中值仍只作用于即时速度显示。正反转切换时丢弃旧方向的显示历史，途经零速也不能把旧方向混入新反转窗口；左右通道独立。序号按 16 位模数验证前进，拒绝倒退和半圈歧义；时间戳继续按 32 位模数验证，支持真实回绕。观测间隔达到 200 毫秒则重新建立显示窗口，重复读取不续样本时间。正常 100 毫秒静止零速窗口仍可显示。

反转及长间隔后需三批新合格观测，期间显示不可用，这会增加显示恢复延迟；控制保留原始速度，不经过中值。原始坏数据没有被改写成有效零速，也没有自动清错或自动恢复驱动。

第二轮针对性主机测试 18 项通过；127 项完整主机测试、147 项运行程序测试通过。五组新反例（四组显示批次/反转、另含过载质量拒绝）对保存的旧算法执行后全部失败、对新算法通过，证明测试能抓到实际差异。离线反转测试不替代真实手转验收。

## 构建、部署及证据

两轮代码改动合并为一次最终完整同源构建，{len(p['stages'])} 个流水线阶段全部通过，包含生产 C、协议、寄存器、RTL、像素、模块综合、整机综合/布线、时序/DRC/HWH 与打包检查。源文件身份在回归前后及最终包阶段均核验，未以旧产物冒充新构建。

最终布线 WNS={timing['wns_ns']:+.3f} ns、WHS={timing['whs_ns']:+.3f} ns，setup/hold 失败端点均为 0；额外核对 bus skew 独立报告，余量为 {timing['bus_skew_slacks_ns']} ns。DRC Error/Critical Warning/Warning 为 0，保留两项既有 VDMA BRAM REQP-181 Advisory，不宣称全部日志零告警。外部电气和引脚延迟仍受待测边界限制。见 `routed_timing_audit.json`。

ROSS 的文档检索与进度工具已使用；尝试 Vivado MCP 启动时代理在启动阶段退出、没有工具输出。随后使用项目现有 Vivado 2026.1 / XSim 入口完成诊断仿真和完整构建，保留原始日志，没有将 MCP 启动失败记为 RTL 失败。

- 完整流水线：`../complete_v09_qei_retest_20261012_r2/pipeline.json`。
- 新候选完整 ZIP：`{p['zip_path']}`。
- ZIP SHA-256：`{p['zip_sha256']}`。
- 第二轮 bit SHA-256：`{trials[1]['bit_sha256']}`。
- 板端新目录：`{receipt['receipt']['remote']}`，所有传输文件逐一 SHA-256 与新候选一致。
- 部署记录：`qei_retest_20261012_candidate_r2.json`。
- 原始采集 SHA-256 第一轮：`{trials[0]['raw_archive']['sha256']}`；第二轮：`{trials[1]['raw_archive']['sha256']}`。

候选仍为 **LAB_ONLY_NO_MOTOR_NON_RELEASE**。实际左右映射、A/B 电平、完整每圈计数、滤波导致的丢沿、带载滚动标定及整车联合验收仍待完成。合法正交顺序的伪脉冲不能只靠非法跳变诊断识别；软件保护不能修复丢失的真实距离。

下一步按项目文档 `docs/03_硬件与接线/14_编码器下一步上板计划_20261013.md` 执行。
'''
report=OUT/'两轮上板实测与优化报告.md'
assert not report.exists();report.write_text(text,'utf8')
plan=ROOT/'docs/03_硬件与接线/14_编码器下一步上板计划_20261013.md'
assert not plan.exists()
plan.write_text('''# 编码器下一步上板计划

制定于 2026-10-13，依据 10 月 12 日至 13 日两轮实际静止采集。目标是尽快打通可信计数→标定→整机联合测试；当前优先消除输入异常，不继续凭静止净计数或更长滤波推定正常。

## 第一场：定位电气与线束，预留 30—40 分钟

电机动力线保持物理断开。先断电核对公共地、左右编码器电源、四路 A/B 线序及接头，再与冻结图核对：左 JB1/JB2，右 JB3/JB4，使能 JA9。资料来源为 `12_双前轮编码器电平转换PCB设计需求_20260920.md` 第 2、4 节和 `pynq_fpga/fpga/board/board_manifest.json`；实际板卡/PCB 仍需按实物复核。

使用万用表核对编码器约 5V、LVC245 逻辑电源约 3.3V、DIR 与使能；加载 Overlay 后 JA9 所连 /OE 应为低。输出波形与幅度用示波器或逻辑分析仪核验，万用表不能证明没有毛刺。优先确认共同电源/地和使能，因为本次两路均出现非法跳变；这只是定位优先级，不是已确认根因。

每次只改一项，每次改线都断电。交换 PCB 两侧完整编码器输入线组作对照：异常跟着线组走则查编码器/线束，异常仍留在原逻辑通道则查对应 PCB 路径/PYNQ 接线；交换后恢复冻结映射。若两路同时异常，先查共享供电、地、DIR、/OE 和接口接触。禁止把裸悬空输入当正常对照。

每组对照重载同版 Overlay、读回滤波、临时比例并采集 60 秒，保留原始日志及改变项。最终正常接线连续静止采集 300 秒；双路无可见计数变化、非法计数始终 0、速度无非零尖峰才进入手转。计数稳定本身不证明输入连通；必须接着验证真实转轮能计数。仍异常就继续定位具体线路，不重复整机软件构建掩盖硬件问题。

## 第二场：可信计数与标定，预留 25—35 分钟

左右轮分别单独手转正反向，另一轮保持静止；确认通道映射、正反符号与 A/B 顺序。每轮正反各 10 圈、各重复 3 次，记录总 x4 合法计数、非法诊断、时间、滤波和来源版本。名义 1:48 / 13PPR 可作轮轴 x4 计数 2496 的对照，但采用实测计数，不把名义值写成测量结果。

在受控手转条件比较 10 微秒滤波与较小滤波的计数和波形，排除高转速丢沿，再选择实际设置；不要只根据静止噪声把滤波加大。不同参数各留独立记录，不合并或删掉异常段。

按已知实测滚动距离分别标定左右 mm/count，先清双轮 SCALE、写整套配置、逐项回读。若写入或读回失败，保持两路未标定。验收要求是映射、方向、每圈计数和左右比例都有原始证据，非法及计算过载计数为 0；任一失败回到第一场。软件反转滤波验证不算本步骤已完成。

## 第三场：恢复整机联调，预留 35—45 分钟

在固定新候选和实测标定下，保持电机断开，先跑 30 秒摄像头/无线页面/编码器/STM32 停止反馈联合检查，确认显示的是实际 LOCK、PWM 和新鲜反馈。单独执行摄像头、串口和线程故障场景并核验收尾；正常条件另开完整 1800 秒会话，不能将故障片段拼成稳定性日志。

用项目现有联合证据审核器检查同包、配置来源、新鲜度、原始异常及资源回收，通过才考虑下一阶段运动版本验收。当前 LAB_ONLY 不发送非零 PWM 或解锁命令；带电机低速短跑、制动距离与释放流程需独立制定并使用完成相应门禁的版本。

推进方式：第一场达到输入稳定条件就立即接第二场，不再排一轮泛化代码审查；仅在新反例或源码变化时做对应回归。每场记录“实际改了什么、原始证据、是否达到下一入口”，失败停在具体未闭合项，避免重跑无关视频或 FPGA 全量构建。
''','utf8')
repro=OUT/'reproducibility';repro.mkdir(exist_ok=False)
for name in ('round1_board.py','round2_board.py','analyze_round.py','deploy_final.py','prepare_trial.py','mutation_check.py','audit_timing.py'):
    shutil.copy2(ROOT/'work/qei_retest_20261012'/name,repro/name)
for name in ('optimization1_host.log','optimization1_rtl.log','optimization2_host.log','host_full.log','runtime_full.log','mutation_check.json','complete_build.log'):
    shutil.copy2(ROOT/'work/qei_retest_20261012'/name,OUT/name)
(repro/'README.md').write_text('''# 本轮脚本归档与复现

本目录保存执行过的脚本，归档副本不是脱离项目的一键部署包。权威工程根目录为 `C:/Users/39909/Desktop/FPGA`，原脚本在 `work/qei_retest_20261012`，串口执行器在 `work/encoder_debug_20261011/run_root.py` 和 `tmp/video_six_uart_exec_20261009.py`。必须保留项目相对布局，或显式把脚本 ROOT 改为实际工程根。

原命令：第一轮使用 `run_root.py work/qei_retest_20261012/round1_board.py pynq_fpga/preintegration/evidence/qei_retest_20261012/round1_uart.json 420 --quiet`；完整构建使用 `powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/build_complete.ps1 -Name v09_qei_retest_20261012_r2 -Wireless`；部署使用 `python work/qei_retest_20261012/deploy_final.py`；第二轮使用 `run_root.py work/qei_retest_20261012/round2_board.py pynq_fpga/preintegration/evidence/qei_retest_20261012/round2_uart.json 600 --quiet`。独立审核使用 `analyze_round.py <UART记录> <新的输出目录>`。

以上第一、第二轮命令中的 run_root.py 均指 `python work/encoder_debug_20261011/run_root.py`。实际构建、部署和采样输出拒绝覆盖；复测必须改用新的候选名称、板端目录和本地证据目录，原档案不得覆盖。板端 PACKAGE 必须指向完成所有构建与部署哈希校验的完整候选。

本次 COM14 及 PYNQ 账号仅适用于当前实物，迁移时重新核对。上板前真实确认电机动力线断开、轮子静止，保持风险许可关闭；临时比例不是实测标定。采样 finally 清双轮 SCALE 并读回 RISK_ENABLE=0。先检查 DeviceLease 和包 manifest；不要为绕过其他 MMIO 所有者而删锁文件。
''','utf8')
print(str(report));print(str(plan))
