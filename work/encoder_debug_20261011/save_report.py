import base64, csv, hashlib, json, shutil, zlib
from pathlib import Path
work = Path('work/encoder_debug_20261011')
out = Path('C:/Users/39909/Documents/Codex/2026-10-11/p-g/outputs/encoder_debug_20261011')
out.mkdir(parents=True, exist_ok=True)
envelope = json.loads((work/'capture_archive.json').read_text('utf8'))
archive = next(json.loads(line) for line in envelope['output'].splitlines() if line.startswith('{') and '"files"' in line)
for name, entry in archive['files'].items():
    if name not in ('status.json','samples.jsonl','markers.jsonl','monitor.py','monitor.log'):
        raise ValueError('unexpected archive filename')
    body = zlib.decompress(base64.b64decode(entry['zlib_base64']))
    assert len(body) == entry['bytes']
    assert hashlib.sha256(body).hexdigest() == entry['sha256']
    (out/name).write_bytes(body)
rows = [json.loads(line) for line in (out/'samples.jsonl').read_text().splitlines()]
status = json.loads((out/'status.json').read_text())
start, end = rows[0], rows[-1]
summary = {'date_local': '2026-10-11', 'candidate': 'v09_video_opt_20261011_r1',
    'contract': '0xC4251009', 'package_verified': True, 'fpga_loaded': True,
    'pc_network_mutated': False, 'transport': 'COM14 board debug UART',
    'router_address': '192.168.8.139', 'operator_hand_turn': False,
    'user_statement': '刚才没有人转动车轮', 'physical_stationary_confirmed': True,
    'samples': len(rows), 'duration_seconds': end['t']-start['t'],
    'left_start': start['left'], 'left_end': end['left'], 'left_delta': end['left']-start['left'],
    'right_start': start['right'], 'right_end': end['right'], 'right_delta': end['right']-start['right'],
    'left_illegal_start': start['left_illegal'], 'left_illegal_end': end['left_illegal'],
    'right_illegal_start': start['right_illegal'], 'right_illegal_end': end['right_illegal'],
    'right_illegal_saturated': end['right_illegal'] == 255,
    'scales_cleared': status['scales_cleared'], 'left_scale_final': status['left_scale_final'],
    'right_scale_final': status['right_scale_final'], 'motor_commands_sent': False,
    'electrical_verified': False, 'channel_mapping_verified': False, 'cpr_verified': False,
    'rollout_calibrated': False, 'result': 'RIGHT_CHANNEL_UNEXPECTED_TRANSITIONS_PENDING_WIRING_DIAGNOSIS'}
(out/'调试结果.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), 'utf8')
with (out/'计数采集.csv').open('w', newline='', encoding='utf-8-sig') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(start))
    writer.writeheader()
    writer.writerows(rows)
for name in ('board_inspection.json','baseline.json','baseline_retry.json','monitor_start.json','monitor_stopped.json','left_start.json','progress_01.json'):
    shutil.copy2(work/name, out/name)
report = f'''# 编码器第一轮实板调试记录

日期：2026-10-11。用户表示已连接编码器和路由器，随后确认暂时无法手转车轮；第二轮开始前补充确认：“刚才没有人转动车轮”。本记录按该确认更新解释，原始采样保持不变。

## 结果

已通过 COM14 板载调试 UART 连接 PYNQ，电脑 Wi-Fi 未切换。PYNQ eth0 链路已建立，路由器分配地址 192.168.8.139。片内 XADC 初次温度约 50.3°C；采集结束前记录约 48.0°C，这不是负载与散热验收。

已核对并加载候选 v09_video_opt_20261011_r1，板端目录 /home/xilinx/video_opt_20261011_candidate_a，契约 ID 0xC4251009。包 manifest 与本地候选一致，bit/HWH 和运行文件由包检查器逐项验证。30 次初始快照 epoch 正常推进。

用户已确认本轮无人转动车轮。本轮左通道保持不变，右通道有大量异常跳变：

| 项目 | 左通道 QEI0 | 右通道 QEI1 |
|---|---:|---:|
| 起始计数 | {start['left']} | {start['right']} |
| 结束计数 | {end['left']} | {end['right']} |
| 净变化 | {summary['left_delta']} | {summary['right_delta']} |
| 非法跳变累计：开始→结束 | {start['left_illegal']}→{end['left_illegal']} | {start['right_illegal']}→{end['right_illegal']} |

采集 {len(rows)} 点，约 {summary['duration_seconds']:.1f} 秒。非法跳变字段为 8 位饱和计数器，达到 255 后不再增长，因此不能将差值当作全部错误次数。最初 6 秒快照中右非法累计为 15，随后采集时升至饱和上限。

## 临时配置和清理

当前寄存器位置属于速度批次；SCALE=0 时该批次位置不更新。为本次计数定位，明确采用已确认 1:48 轮组的临时名义 profile TT_48_ORIGINAL_WHEEL_FRONT_2（左右 SCALE=5362），保持风险许可禁用，不发送任何电机命令。此配置只用于台架观测，不是轮周长标定。采集发现非法跳变后停止；左右 SCALE 均清回 0 并读回确认。

首次诊断脚本把寄存器常量 ID_VERSION 写成 ID，脚本报错后已修复重跑；原失败保留于 baseline.json，不作为硬件失败依据。

## 判断与下一步

车轮始终静止时右通道这些跳变属于异常输入，优先排查公共地、右编码器 A/B、PCB 输出到 JB3/JB4 的连接及接头接触。当前证据不能确认是哪一处故障，也不能把左通道不变写成左编码器正常。

先核对实际接线照片。若无法直接确定，断电后交换 PCB 的 J3/J4 编码器输入线组，再采集静止状态：若异常随线组移到左通道，优先查编码器/线束；若仍留在右通道，优先查右侧 PCB 和 PYNQ 接线。交换仅作诊断，不改变冻结的左右通道定义。异常消除后再进行左右单轮正反转、10 圈计数和带载滚动周长标定。

电气电平、通道映射、CPR、轮周长与运动联合测试均未通过验收。
'''
(out/'编码器调试记录.md').write_text(report, 'utf8')
print(json.dumps(summary, ensure_ascii=False))
print(str(out/'编码器调试记录.md'))
