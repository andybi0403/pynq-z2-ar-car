"""Offline comparison only: do not replace physical QEI data or drive motors."""
import csv, hashlib, json, math, shutil, statistics
from collections import deque
from pathlib import Path

folder = Path(__file__).parent
out = Path('C:/Users/39909/Documents/Codex/2026-10-11/p-g/outputs/encoder_debug_20261011/round3')

def rolling_median(values, window):
    history = deque(maxlen=window)
    result = []
    for value in values:
        history.append(value)
        # No synthetic zero padding at startup.
        result.append(statistics.median(history))
    return result

def delta32(new, old):
    return ((new-old + (1 << 31)) % (1 << 32)) - (1 << 31)

def metrics(values, dt):
    return {'peak_counts_per_s': max(map(abs, values), default=0),
            'rms_counts_per_s': math.sqrt(sum(v*v for v in values)/len(values)) if values else 0,
            'integrated_signed_counts': sum(v*t for v,t in zip(values,dt)),
            'integrated_absolute_counts': sum(abs(v)*t for v,t in zip(values,dt)),
            'nonzero_samples': sum(abs(v) > 1e-9 for v in values)}

def analyze_rows(rows):
    dt = [b['t']-a['t'] for a,b in zip(rows,rows[1:])]
    assert all(t > 0 for t in dt)
    result = {'samples': len(rows), 'observed_seconds': rows[-1]['t']-rows[0]['t'],
              'median_sample_interval_s': statistics.median(dt), 'channels': {}}
    traces = {}
    for side in ('left','right'):
        increments = [delta32(b[side], a[side]) for a,b in zip(rows,rows[1:])]
        speeds = [d/t for d,t in zip(increments,dt)]
        traces[side] = {'raw': speeds, 'median3': rolling_median(speeds,3), 'median5': rolling_median(speeds,5)}
        illegal = [r[side+'_illegal'] for r in rows]
        channel = {'net_delta': delta32(rows[-1][side],rows[0][side]), 'position_start': rows[0][side],
                   'position_end': rows[-1][side], 'position_min': min(r[side] for r in rows),
                   'position_max': max(r[side] for r in rows),
                   'observed_abs_count_delta': sum(abs(v) for v in increments),
                   'nonzero_delta_intervals': sum(d != 0 for d in increments),
                   'max_abs_count_jump': max(map(abs,increments), default=0),
                   'illegal_start': illegal[0], 'illegal_end': illegal[-1],
                   'counter_saturated': max(illegal) == 255,
                   'first_illegal_seconds': next((r['t']-rows[0]['t'] for r in rows if r[side+'_illegal'] > 0),None),
                   'position_difference_demo': {method: metrics(values,dt) for method,values in traces[side].items()}}
        if side+'_valid' in rows[0]:
            # All values remain nominal: temporary SCALE, no physical rollout calibration.
            valid_rows = [r for r in rows if r[side+'_valid']]
            channel['pl_nominal_velocity'] = {'valid_samples': len(valid_rows), 'invalid_samples': len(rows)-len(valid_rows),
                'peak_mmps_among_valid': max((abs(r[side+'_velocity_q16'])/65536 for r in valid_rows), default=None),
                'nonzero_valid_samples': sum(r[side+'_velocity_q16'] != 0 for r in valid_rows)}
            # Compare actual T-method batches; deduplicate repeated host reads.
            histories = {3: deque(maxlen=3), 5: deque(maxlen=5)}
            outputs = {3: [], 5: []}
            last_seq = None
            for r in rows:
                if not r[side+'_valid']:
                    last_seq = None
                    for h in histories.values():
                        h.clear()
                    continue
                if r[side+'_sequence'] == last_seq:
                    continue
                last_seq = r[side+'_sequence']
                for w,h in histories.items():
                    h.append(r[side+'_velocity_q16']/65536)
                    outputs[w].append(statistics.median(h))
            channel['t_method_display_only_comparison'] = {str(w): {'new_valid_batches':len(v),
                'peak_nominal_mmps':max(map(abs,v),default=0),
                'illegal_diagnostics_deliberately_not_gated_for_comparison':True}
                for w,v in outputs.items()}
        # Demonstration quality gate: an illegal transition taints the stream,
        # including an already saturated counter. Never turn it into a valid zero.
        fault_seen = False
        valid_gate = []
        for r in rows:
            fault_seen = fault_seen or r[side+'_illegal'] > 0
            valid_gate.append(not fault_seen and r.get(side+'_valid',False))
        channel['shadow_quality_gate'] = {'rejected_samples': len(rows)-sum(valid_gate),
                                         'latched_illegal_fault': fault_seen,
                                         'rejection_output': None, 'writes_to_device': False}
        result['channels'][side] = channel
    result['fault_reproduced'] = any(c['observed_abs_count_delta'] > 0 or c['illegal_end'] > 0
                                      for c in result['channels'].values())
    return result, traces

def synthetic_evaluation():
    cases = {'one_sample_impulse':[0]*10+[1000]+[0]*10,
             'two_sample_impulse':[0]*10+[1000]*2+[0]*10,
             'ten_sample_burst':[0]*10+[1000]*10+[0]*10,
             'real_speed_step':[0]*10+[1000]*20,
             'real_reversal':[1000]*10+[-1000]*20}
    results = {}
    for name, values in cases.items():
        results[name] = {str(window): {'peak':max(map(abs,rolling_median(values,window))),
                                       'final':rolling_median(values,window)[-1]}
                        for window in (3,5)}
    assert results['one_sample_impulse']['3']['peak'] == 0
    assert results['two_sample_impulse']['5']['peak'] == 0
    assert results['two_sample_impulse']['3']['peak'] == 1000
    assert results['ten_sample_burst']['5']['peak'] == 1000
    assert results['real_speed_step']['3']['final'] == 1000
    assert results['real_reversal']['3']['final'] == -1000
    results['scope'] = 'Synthetic illustrations, not wheel-motion validation; a brief real motion has the same samples as an impulse and can also be removed.'
    return results

if __name__ == '__main__':
    name = 'round3_01_baseline'
    trial = json.loads((folder/(name+'_summary.json')).read_text('utf8'))
    rows = [json.loads(line) for line in (folder/(name+'_samples.jsonl')).read_text('utf8').splitlines()]
    result, traces = analyze_rows(rows)
    result.update(trial=trial, synthetic_evaluation=synthetic_evaluation(),
                  replay_only=True, production_algorithm_changed=False,
                  filtering_raw_cumulative_position=False,
                  j2_three_wires_connected_user_confirmed=True,
                  physical_stationarity_basis='Continuing the user-confirmed stationary setup; no commanded motor motion.')
    out.mkdir(parents=True, exist_ok=True)
    for suffix in ('.py','_uart.json','_summary.json','_samples.jsonl'):
        shutil.copy2(folder/(name+suffix),out/(name+suffix))
    shutil.copy2(Path(__file__),out/'round3_analysis.py')
    with (out/'第三轮原始采集.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (out/'中值滤波离线对照.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['seconds','raw_left_count_rate','median3_left_count_rate','median5_left_count_rate',
                                                 'raw_right_count_rate','median3_right_count_rate','median5_right_count_rate'])
        for i,r in enumerate(rows[1:]):
            writer.writerow([r['t']-rows[0]['t']]+[traces[side][method][i] for side in ('left','right') for method in ('raw','median3','median5')])
    (out/'第三轮调试与算法回放.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    right = result['channels']['right']
    original = right['position_difference_demo']['raw']['integrated_signed_counts']
    comparison = '\n'.join(f"| {method} | {data['peak_counts_per_s']:.1f} | {data['rms_counts_per_s']:.1f} | {data['integrated_signed_counts']:.1f} |"
                           for method,data in right['position_difference_demo'].items())
    report = f'''# 编码器第三轮复测与算法评估

2026-10-11，延续用户确认的无人转动车轮、断开电机动力、J2 三根线已连接的台架条件。未收到本轮重新插拔接线的确认，不据此宣称硬件接触已改善。

## 复测结果

异常再次复现。重新验证并加载 v09_video_opt_20261011_r1，契约 0xC4251009，通过 COM14 采集约 {result['observed_seconds']:.1f} 秒，共 {len(rows)} 点，中位采样间隔 {result['median_sample_interval_s']*1000:.2f} 毫秒。

左计数始终为零；右计数 {right['position_start']}→{right['position_end']}，净增加 {right['net_delta']}。右通道共有 {right['nonzero_delta_intervals']} 个采样间隔出现位置变化，单次最大 {right['max_abs_count_jump']} 个计数。它并非只有一个孤立尖峰。

右非法跳变计数从第一个采样点开始已经为 255，此字段饱和，不能计算实际错误总数或以“255 未增加”认为干净。右 PL 速度有效位在 3446 个样本中为真，其中 140 个为非零速度，最大名义值约 32768 mm/s，是 Q16.16 正数饱和值；这是错误输入导致的读数，不是真实车速。左侧没有计数变化仍不能代替接线与真实转动验收。

本轮使用明确的临时轮组 profile SCALE=5362，只为观察速度批次位置，不是实测轮周长标定。采集结束后读回左右 SCALE=0、FILTER=0、RISK_ENABLE=0；未发送电机命令，电脑 Wi-Fi 未切换。起止温度约 {trial['temperature_start_c']:.1f}°C / {trial['temperature_end_c']:.1f}°C。

## 已完成的离线算法比较

以相邻位置批次的差分除以实际时间间隔，构造“观察到的计数变化率”，比较因果 3 点与 5 点中值。下面单位是计数/秒及计数，不是经过标定的真实速度、实际里程，也不是直接对 PL T 法速度做的效果证明。

| 方法 | 峰值计数/秒 | RMS计数/秒 | 输出积分的虚假计数 |
|---|---:|---:|---:|
{comparison}

5 点滤波仍留下约 {right['position_difference_demo']['median5']['integrated_signed_counts']/original*100:.1f}% 的虚假漂移。这说明平滑能降低某些尖峰，但无法从这份数据恢复真实的零运动。中值取窗口排序后的中间值；一般定义参见 [SciPy 官方说明](https://docs.scipy.org/doc/scipy/tutorial/signal.html#median-filter)。这里使用 Python 标准库实现可复现的因果回放，未安装或调用 SciPy。

另对真正的 PL T 法速度批次回放，按序号去重，在有效位为假时清空滤波历史。为了独立观察平滑效果，这项对照刻意没有叠加非法跳变故障隔离；3 点/5 点输出仍出现约 {right['t_method_display_only_comparison']['3']['peak_nominal_mmps']:.1f} / {right['t_method_display_only_comparison']['5']['peak_nominal_mmps']:.1f} mm/s 的名义峰值。右流已经发生非法跳变，所以这些滤后输出仍不可用于控制。

另做了合成波形比较：3 点能消除单点尖峰，5 点能消除连续两点尖峰；两者都不能消除持续 10 点的异常台阶。持续真实速度和反转最终能通过，但存在延迟，短暂真实运动也可能被删掉。这些是离线示例，不是实物转动验证。

## 建议的算法方案

1. **在 PL 输入处过滤短毛刺。** 沿用已有同步器、AB 稳定窗口和合法相位状态机；5–10 微秒可列为下一版候选，必须通过真实正反转/高速计数验证后定值。上一轮 10 微秒组平稳，同时无滤波第一组也平稳，因此不能把“10 微秒有效”当作已证明。100 微秒组已经失败，不建议为了归零继续无界增加窗口。连续采样确认电平的原理可参考 [TI 输入资格判定说明](https://www.ti.com/document-viewer/lit/html/SSZT713/GUID-67EF369C-B916-4DA7-8D98-DE1DD243EE4D)。

2. **对有效速度做短窗中值，仅先用于显示/诊断。** 候选是 3 个新的有效批次，按 sequence 与 timestamp 去重，失效/过期时立即停止输出可用速度。不要平滑累计原始位置，也不要把显示结果写回原计数。本轮批次更新并非严格等间隔；以主机约 52 毫秒采样推算延迟不能替代真实批次时序验收。5 点比 3 点延迟更长，会影响起步、制动和方向改变，因此当前不建议把它接入风险控制。

3. **把输入质量异常纳入有效性，使用故障状态隔离错误数据。** 使用已有非法跳变诊断与里程计 fault 字段，出现新的非法跳变或计数器饱和时，将该路标为不可用并保留故障记录。恢复需要明确重新确认干净输入与新观测批次，不自动清空错误计数来掩盖问题，也不将不可用数据填成有效零速。AB 双位同时变化作为编码错误的原理见 [TI eQEP 官方 API](https://software-dl.ti.com/C2000/docs/C2000_driverlib_api_guide/f28p65x/build/html/modules/eqep.html)。当前 PL 里程计已有非法跳变故障锁存，但速度有效位可在后续零速观测或可计算周期后重新为真；将质量故障用于所有速度消费者是下一步可以补的算法约束。

离线的故障隔离原型把右侧全部 {len(rows)} 个样本判为不可用。这证明能识别这一轮已知坏流，不是“100%恢复正确速度”；未产生可用的新速度或计数，也未部署到板端控制程序。当前所有临时参数已还原。

## 实施边界

无需一开始加入卡尔曼或复杂模型。先做“短毛刺过滤 + 有效批次短窗中值 + 质量故障隔离”，用可解释规则处理两种不同问题。物理速度/加速度阈值需要实测，不直接用安全核的 5000 mm/s 上限代替电机机械边界。禁止仅因 PWM=0 就强行显示零速，因为滑行、手推和倒溜可能是真实运动；左右速度也不能简单互相替代，因为转弯本来就不同。

本次完成实板复测、真实日志回放、合成边界示例和实施方案。生产 RTL、bit/HWH、控制算法均未修改。正式接入前还需要真实低速、高速、短促转动、反向与制动的计数保真和延迟验证；对持续错误输入，算法只能识别和隔离，具体输入故障点仍需定位。
'''
    (out/'第三轮复测与算法方案.md').write_text(report,'utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
