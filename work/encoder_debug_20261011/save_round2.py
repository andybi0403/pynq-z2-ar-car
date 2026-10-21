import csv, json, shutil
from pathlib import Path

work = Path(__file__).parent
out = Path('C:/Users/39909/Documents/Codex/2026-10-11/p-g/outputs/encoder_debug_20261011/round2')
out.mkdir(parents=True, exist_ok=True)
names = ['round2_01_baseline', 'round2_02_filter10us', 'round2_03_filter100us', 'round2_04_baseline_return']
trials = [json.loads((work/(name+'_summary.json')).read_text('utf8')) for name in names]
audit = json.loads((work/'round2_source_audit.json').read_text('utf8'))
assert all(trial['completed'] and trial['restored'] for trial in trials)
assert audit['all_sources_matched']
combined = []
for trial in trials:
    name = trial['trial']
    for suffix in ('_uart.json', '_summary.json', '_samples.jsonl', '.py'):
        shutil.copy2(work/(name+suffix), out/(name+suffix))
    rows = [json.loads(line) for line in (work/(name+'_samples.jsonl')).read_text('utf8').splitlines()]
    combined.extend({'trial': name, 'filter_ticks': trial['filter_ticks'], 'seconds': row['t']-rows[0]['t'], **row} for row in rows)
shutil.copy2(work/'round2_source_audit.json', out/'源码与管脚核对.json')
with (out/'第二轮计数采集.csv').open('w', newline='', encoding='utf-8-sig') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(combined[0]))
    writer.writeheader()
    writer.writerows(combined)
temperatures = [trial[key] for trial in trials for key in ('temperature_start_c', 'temperature_end_c')]
summary = {'date_local': '2026-10-11', 'candidate': 'v09_video_opt_20261011_r1',
           'physical_stationary_confirmed': True, 'user_statement': '刚才没有人转动车轮',
           'j2_three_wires_connected_user_confirmed': True,
           'transport': 'COM14 board debug UART', 'pc_network_mutated': False,
           'samples': len(combined), 'nominal_observation_seconds': sum(t['target_seconds'] for t in trials),
           'trials': trials, 'source_identity_matched': True,
           'existing_simulation_checks': audit['existing_same_candidate_simulation'],
           'new_rtl_regression_run': False, 'production_rtl_changed': False,
           'permanent_filter_change': False, 'final_registers': trials[-1]['final_registers'],
           'temperature_endpoints_range_c': [min(temperatures), max(temperatures)],
           'motor_commands_sent': False, 'electrical_verified': False,
           'channel_mapping_physically_verified': False, 'cpr_verified': False,
           'rollout_calibrated': False,
           'result': 'STATIONARY_INPUT_ANOMALY_REPRODUCED' if any(t['static_diagnostic_fault'] for t in trials) else 'NO_REPRODUCTION_THIS_ROUND_PREVIOUS_FAULT_UNRESOLVED'}
(out/'第二轮调试结果.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), 'utf8')
table = []
for t in trials:
    event = '未出现' if t['first_diagnostic_event_seconds'] is None else f"{t['first_diagnostic_event_seconds']:.2f}秒"
    table.append(f"| {t['filter_ticks']/100:g}微秒 | {t['observed_seconds']:.1f}秒 | {t['left']['net_delta']} / {t['right']['net_delta']} | {t['left']['illegal_start']}→{t['left']['illegal_end']} / {t['right']['illegal_start']}→{t['right']['illegal_end']} | {t['left']['filtered_end']} / {t['right']['filtered_end']} | {event} |")
report = '''# 编码器第二轮静止调试

2026-10-11。用户确认上一轮无人转动车轮，本轮沿用静止、断开电机动力的台架条件。用户另确认 J2 的 GND、3V3、OEN 三根控制线都已接好。

结论：静止输入异常已经复现，增大滤波并没有消除非法跳变。当前不能认定编码器或 PCB 已调试通过，也没有证据锁定具体坏件。

## 实板结果

通过 COM14 执行四组有界采集，保持电脑 Wi-Fi。每组重新加载并验证同一 bit/HWH，清掉前一组饱和诊断计数，再设置临时滤波和已确认轮组的名义 SCALE=5362 用于观察批次位置。

| 滤波窗口 | 实际采集时长 | 净计数变化：左/右 | 非法跳变初→末：左/右 | 滤除抖动末值：左/右 | 首个异常采样 |
|---|---:|---:|---:|---:|---:|
''' + '\n'.join(table) + f'''

共 {len(combined)} 个采样点，计划观测窗口合计 {summary['nominal_observation_seconds']} 秒。100 微秒组约 6.24 秒时，左右滤除抖动计数在同一个约 100 毫秒采样点变为 255，同时右非法跳变变为 34，后来达到 255。两类计数均为 8 位饱和计数器，255 只代表至少 255 次，不能当作全部次数。

“净计数变化为零”不能代替输入稳定：短时计数可以相互抵消，非法的 AB 双位跳变也不计入位置。位置寄存器属于已发布速度批次，不是直接导出的原始 AB 电平。原始诊断字段和采样序号随记录保留。第一轮的右计数 +1142、非法跳变饱和证据仍然有效，未因本轮前两组平稳而撤销。

最后无滤波组静止约 120 秒，右计数由 1278 变为 5820，净增加 4542；左计数虽最后回到零，中途曾降至 −2。右非法跳变在该组第一个采样点前已经饱和，尽管每组重新加载过 FPGA，也不能用本组非法计数的末减初值零解释为“无错误”。这再次说明异常有间歇性，前两组平稳不足以宣告修复。

## 核对与本轮优化

核对了 QEI 解码器、速度核、整合顶层、板级封装、寄存器定义和 Python 消费端，共 9 个源码/配置文件的 SHA256，均与候选构建 manifest 匹配。板端包检查器每组验证 bit/HWH 与运行文件，读取契约 0xC4251009。布线报告的输入映射为左 JB1/W14、JB2/Y14，右 JB3/T11、JB4/T10，OEN 为 JA9/W18；此检查不代表实体接线已验证。

沿用同一候选今天已有的仿真证据：QEI 31 项、速度 124 项、里程计 16 项、整合架构 66 项通过。本轮没有改动生产 RTL，也未重新运行整套仿真。

改进了调试采集与判定：每组重置饱和计数、同时观察非法跳变和滤波拒绝计数、记录首次异常时间、检查采样序号、保存带 SHA256 的完整原始采样，并在 finally 中恢复参数。这样不会把“显示为零”误写成硬件通过。

每组结束后都读回确认：左右 SCALE=0、左右 FILTER=0、RISK_ENABLE=0。不发送任何电机命令，不保留临时滤波作为正式配置。起止温度读数范围 {min(temperatures):.1f}–{max(temperatures):.1f}°C，仅为本轮台架读数。

## 下一步

两个通道在同一采样点出现抖动，使公共连接（GND、3V3、5ENC、OEN）也成为排查对象；这是依据症状的推断，不是确定根因。J2 三根线“已接好”是用户确认，不能排除插头接触不良。

先断电重插 J2 控制线与 J1 的 GND（Pmod B 5脚），确认插头接触牢固后，重复无滤波静止采集。若仍异常，再断电交换 J3/J4 的整组编码器输入作定位：异常随线组移动时查编码器/线束，留在原通道时查 PCB 输出/PYNQ 接线。交换只用于诊断，保留原左右定义。尚未完成左右单轮正反转、每轮 10 圈计数和实测轮周长标定。
'''
(out/'第二轮调试记录.md').write_text(report, 'utf8')
print(json.dumps({'report': str(out/'第二轮调试记录.md'), 'samples': len(combined),
                  'result': summary['result'], 'final_registers': summary['final_registers']}, ensure_ascii=False))
