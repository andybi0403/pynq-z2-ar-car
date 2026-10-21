import hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'pynq_fpga/preintegration/evidence/qei_display_20261013'
pipeline=ROOT/'pynq_fpga/preintegration/evidence/complete_v09_qei_display_20261013_r2/pipeline.json'
p=json.loads(pipeline.read_text('utf8'))
assert p['status']=='LAB_ONLY_CANDIDATE' and all(s['status']=='PASS' for s in p['stages'])
deploy=json.loads((OUT/'qei_display_20261013_candidate_r2.json').read_text('utf8'))
assert deploy['returncode']==0 and deploy['receipt']['board_files_exactly_match_candidate']
board=json.loads((OUT/'board_result.json').read_text('utf8'))
assert board['completed'] and board['safe_unconfigured'] and board['zero_estimated_samples']==board['samples']
replay=json.loads((OUT/'replay_summary.json').read_text('utf8'))
sample_count=sum(row['samples'] for row in replay['rounds'])
package=Path(p['package_dir'])
impl=json.loads((OUT/'implementation_audit.json').read_text('utf8'));assert impl['status']=='PASS'
audit=json.loads((OUT/'board_independent_audit.json').read_text('utf8'));assert audit['status']=='PASS'
guide=f'''# 显示稳定化实施说明

2026-10-13。已实现独立的网页运动估计层，完成回归、完整候选构建、逐文件部署核验和实际 PYNQ 台架短测。目标是让网页显示稳定；没有将估计值伪装为编码器实测，也没有用估计解除原有控制故障。

| 状态 | 网页行为 |
|---|---|
| 正常合格双轮观测 | 三批中值后平滑，按时间限制显示速度变化；显示速度最大绝对值默认 2000 mm/s、变化率默认 600 mm/s²、平滑时间常数 0.25 秒。这些是展示参数，不是实测车辆极限。 |
| 双轮明显不一致 | 不直接取较小值；当前展示容差为 80 mm/s 加 25% 的较大绝对轮速，仅用于展示融合，不作为车辆故障门限。 |
| 短时无合格观测 | 从上一可信观测时刻起最多保持 1 秒，重复读取不会续期。估计位移/路程不把坏计数继续积分。 |
| 持续无合格观测 | 有新鲜实际 LOCK=1、双轮 PWM=0 反馈时可显示锁车零速估计；导入实测 PWM—速度模型且实际反馈新鲜时可使用模型估计。缺少条件则显示估计不可用。 |
| 明确启用静止展示 | `--display-stationary` 将当前显示周期定义为静止假设，估计速度和新增估计路程为 0，并标为静止展示估计。移动时关闭这个选项。 |
| 运行线程或遥测中断 | 网页撤销估计可用状态，不把网页轮询当成新的采样。 |

显示数据在独立 `motion_display` 字段，带 `estimated=true`、模式、原因及有效期限。旧的 `speed_valid`、`speed_mm_s`、`odometry_valid`、原始寄存器和控制决策仍保留。网页的主数字使用估计字段；HDMI/PL 历史帧测量、UART/实际 PWM、制动、风险判断和放行条件保持原语义。新旧程序不能混包，包校验已把 `motion_display.py` 纳入运行源文件清单。

## 验证结果

两轮此前实际静止采集共 {sample_count} 个快照，用生产回放解码器重新读取。静止展示模式下全部显示速度/位移/路程为 0；原始文件 SHA-256 未改变，所有原故障仍未被提升成有效测量，控制许可结果与原记录一致。此项是历史硬件记录的离线回放，不是又做了 {sample_count} 次实板采样。见 `replay_summary.json`。

新增 10 项显示算法检查，137 项完整主机测试通过；完整流程包含 151 项运行程序测试，以及原生产 C、协议、寄存器、RTL、像素、综合、整机布线、时序/DRC/HWH 与打包检查。网页渲染器在 Node 中验证了估计字段和断更处理，并在浏览器里实际查看了回放页面；截图保存为 `display_preview.png`。

最终整机时序余量 setup {impl['setup_worst_ns']:.3f} ns、hold {impl['hold_worst_ns']:.3f} ns，两项总线偏斜余量 {impl['bus_skew_slacks_ns']} ns，DRC 仅保留 2 项既有 REQP-181 Advisory，无 Error/Critical Warning。独立读取实际报告的复核见 `implementation_audit.json`。

首个候选 r1 在完整回归时暴露已有视频关闭竞态：最后已完成的提交可能因停止标志丢失日志。已添加独立 `frame_shutdown_submission` 记录，保留完成的提交证据，不给它正常运行帧数或帧率信用；新增确定性收尾用例通过。失败候选保留在 `../complete_v09_qei_display_20261013_r1`，没有用于部署。

本次新候选上板短测 {board['observed_seconds']:.2f} 秒，共 {board['samples']} 个快照，采用明确的静止展示假设和临时名义 SCALE，仅核验显示层。估计速度/位移/路程为零的样本 {board['zero_estimated_samples']}，原测量速度无效的样本 {board['invalid_measurement_samples']}，控制许可 {board['control_permits']}。最后非法计数为 {board['illegal_last']}；此数据不证明输入毛刺已消失。最终 SCALE 两路清零、RISK_ENABLE=0，滤波保持 10 微秒，没有发送电机命令。见 `board_result.json` 和 `board_samples.jsonl`。

独立复核本次原始快照：左右净计数分别 {audit['wheels'][0]['net_count']}、{audit['wheels'][1]['net_count']}，右轮原始速度绝对峰值 {audit['wheels'][1]['raw_velocity_peak_mm_s']:.2f} mm/s，但静止估计始终为零。左轮净计数不变却已有非法计数饱和，也不能判定正常。见 `board_independent_audit.json`。

## 直接使用

本机完整候选：`{package.as_posix()}`。板端目录：`{deploy['receipt']['remote']}`。在板端该目录执行：

```sh
cd {deploy['receipt']['remote']}
sudo env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 wireless_runtime.py --video-only --motor-disconnected --display-stationary --duration 600 --web-port 8080
```

这条命令适用于当前静止、断开电机的展示；依赖已接好的摄像头和既有网络，终端输出实际浏览器地址与令牌。视频-only 使用既有只测视频路径，执行器控制按钮禁用，不能获得整车联合验收通过；没有绕过正常联合运行的采集就绪门槛。正常传感器联调通过后，可在原联合运行命令中使用显示估计，关闭静止假设。

下一次上板按 `docs/03_硬件与接线/14_编码器下一步上板计划_20261013.md` 推进：先处理输入/线束异常，接着手转核对和左右比例标定，再跑联合会话。移动展示必须关闭静止假设；真实 PWM—速度模型需在允许运动的后续版本里采集，评估加减速、反转和转弯时的估计延迟。网页稳定不替代这些入口。

运行模型接口是 `--display-model 文件.json`。需要真实非零 PWM—速度测量点、`measured=true` 和测量来源，按范围内插值；不外推，也不把请求 PWM 冒充实际反馈。本次没有实际非零 PWM—速度标定，未生成假标定文件。软件测试夹具不应当作实际模型使用。

完整流水线：`../complete_v09_qei_display_20261013_r2/pipeline.json`；ZIP SHA-256：`{p['zip_sha256']}`；bit SHA-256：`{board['bit_sha256']}`；实际采样原始 SHA-256：`{board['raw_archive']['sha256']}`。候选仍为 LAB_ONLY_NO_MOTOR_NON_RELEASE，物理输入故障、运动标定和整车联合验收仍待解决。

![网页估计显示的离线回放预览]({(OUT/'display_preview.png').as_posix()})
'''
path=OUT/'显示稳定化实施说明.md';assert not path.exists();path.write_text(guide,'utf8')
source=OUT/'scripts';source.mkdir(exist_ok=False)
for file in (ROOT/'work/qei_display_20261013').glob('*.py'):
    shutil.copy2(file,source/file.name)
for name in ('targeted.log','host_full.log','runtime_full.log','page_test.log','joint_targeted.log','complete_build_r2.log'):
    shutil.copy2(ROOT/'work/qei_display_20261013'/name,OUT/name)
print(str(path))
