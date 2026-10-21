> 当前v0.10混合采集：先烧录包内stm32_hybrid_v3.hex，UART双方115200 8N1，超声波/红外恢复STM32接口，编码器仍经原PCB接PYNQ。新运行器先启动查询并原子提交传感器，再进行就绪检查；具体接线与协议见包内HYBRID_SETUP.md。旧9600/P帧步骤不适用于此版本。仍为电机动力断开的LAB_ONLY。

# 任务7/8 LAB_ONLY 无电机台架包

2026-10-01新增中央前方描边、近似厘米距离与风险颜色，详见随包 `FRONT_OVERLAY.md`。该距离是超声波正前方读数，不绑定单个视觉轮廓；无效时为紫色 `FRONT ~--- CM`。实际构建身份、回归与时序结果以本包 manifest 和 `latest_candidate.json` 为准。

本目录是PYNQ-Z2无电机台架候选，**不是发布版本**。它只允许验证Overlay、MMIO、传感器只读状态、UART STOP、VDMA、OSD、C270和HDMI。禁止发送非零PWM，禁止发送`$PREL#`，禁止在电机连接状态运行。

## 当前状态

2026-10-12 编码器质量策略：`QEI*_INFO` 的非法跳变计数非零（含 255 饱和）、里程故障或速度算术饱和，立即使上层控制观测无效。有效位重新出现不代表恢复，保留原始计数、速度和诊断；原始记录与历史视频速度不作平滑。浏览器即时速度仅使用三批新的、未过期且质量合格的数据取中值，携带被选中样本的原始时间戳，重复读取不延长有效期；异常显示不可用，不置成有效零速。此中值不进入控制链。

未配置 SCALE 且显式声明电机动力断开时，联合/无线台架入口设置两路 1000 tick（10 微秒）输入稳定滤波并核对回读；已有标定沿用其参数，视频单独运行不自动声称动力断开。10 微秒仅为候选参数，尚待真实转轮校验方向、计数、最大速度和延迟。输入故障排除后需明确重载 Overlay/恢复标定，显示重新积累三批有效样本；控制锁存仍要求既有人工重新使能流程，禁止自动恢复驱动。

- bit/hwh已由Vivado 2026.1从完全布线的生产核集成候选生成。
- HWH确认存在`car_system`，不存在控制/OSD占位核。
- 控制窗口固定为`0x43C00000/0x1000`，统一ID为`0xC4251009`（v0.9）。
- release门禁保持BLOCKED；尚未完成实板验收，因此构建包不包含硬件PASS结论。

## 文件

- `task7_8_LAB_ONLY.bit/.hwh`：同名PYNQ Overlay文件。
- `lab_manifest.json`：SHA-256、时序、分类和实物状态。
- `lab_acceptance.py`：板端分阶段验收入口。
- `board_runtime.py`、`perception_client.py`等：从当前权威源码自动复制的运行依赖。
- `timing_LAB_ONLY.rpt`、`drc_LAB_ONLY.rpt`、`io_LAB_ONLY.rpt`：生成时的Vivado证据。

## 到板后的执行顺序

本包是FPGA Overlay与运行程序，不是SD卡系统镜像。PYNQ上需要Python 3.10及以上、PYNQ、NumPy、pyserial和FFmpeg；先确认`python3 --version`。从完整包目录运行只读部署检查，它不加载Overlay或打开串口：

```bash
python3 deployment_check.py --board --output evidence/deployment.json
```

依赖或设备路径不齐先处理检查结果；不把安装依赖、摄像头设备出现或GPIO供电正常当作实板验收通过。

先把整个目录复制到PYNQ。仅做文件与HWH契约检查：

```bash
cd ~/task7_8_lab_only_20260919
python3 lab_acceptance.py contract
```

分项检查完成后用同一进程联合启动，电机仍物理断开。标定文件必须是保存的左右轮配置；未完成实测时可以省略，但不能获得最终联合验收通过：

```bash
python3 system_runtime.py --motor-disconnected --duration 1800 --video \
  --calibration calibration.json --web-bind 0.0.0.0 --web-port 8080
```

浏览器使用终端打印的带会话令牌地址查看状态、配置与日志；细节见`STATUS_PAGE.md`。HDMI历史数值随画面同行，最新安全提示与实际STM32反馈保持独立；帧格式及测量边界见`FRAME_METADATA.md`。不要同时启动第二个视频/控制会话。

结束后以本次实际部署文件独立核验：

```bash
python3 joint_evidence.py --directory evidence/joint --package-dir . --calibration calibration.json
```

默认审核真实1800秒联合记录、帧/传感器/控制覆盖、包与标定身份及显示时间。照片、电气/机械测量和曝光至屏幕扫描延迟仍需另行记录；没有硬件证据保持PENDING。

确认板卡修订版、电源和电平，保持电机物理断开，然后加载Overlay并采集20个一致快照：

```bash
python3 lab_acceptance.py mmio --evidence-dir evidence
```

接显示器后提交RGB色条；脚本只证明帧已提交，颜色顺序仍需人在屏幕上确认并补照片：

```bash
python3 lab_acceptance.py color-bars --hold-seconds 30 --evidence-dir evidence
```

接入C270并确认`/dev/video0`后采集900帧。默认门限为实测≥25fps、P95帧间隔≤50ms、估算掉帧率≤5%；结果和门限都会写入JSON：

```bash
python3 lab_acceptance.py camera --camera-device /dev/video0 --frames 900 \
  --min-fps 25 --max-p95-ms 50 --max-drop-rate 0.05 --evidence-dir evidence
```

色条命令只证明DMA帧已经提交，不会自行宣称屏幕色序正确；仍需人工观察并保存照片。

UART STOP测试必须先拔掉电机，并安装`pyserial`。它只发送`$PSTOP#`及零速/无效心跳，不发送释放或运动帧；只有STOP请求后新收到的锁存零输出`$CAR`才能通过，默认响应时限为300ms：

```bash
python3 -m pip install pyserial
python3 lab_acceptance.py uart-stop --port /dev/ttyPS1 --duration 3 --stop-deadline-ms 300 --motor-disconnected --evidence-dir evidence
```

超声波与红外按`pynq_fpga/fpga/board/no_motor_acceptance.md`逐项改变物理条件，同时重复`mmio`采集。编码器只可在完成电平转换检查后连接：两块霍尔板的4.5—5V取自Arduino POWER头J7 pin 4（VCC5V0），A/B经SN74LVC245A进入JB1—JB4，`/OE`外部10k上拉到3.3V并由JA9/W18控制。Pmod电源脚只有3.3V，禁止把它当5V源；QEI电气未验收时不要把`QEI valid=false`判成工程失败。

传感器条件不要只靠人工阅读寄存器。稳定摆放目标后可直接检查正常距离与红外清除状态：

```bash
python3 lab_acceptance.py sensor-check --label normal --count 10 \
  --expect-us-valid 1 --expect-us-fault 0 --distance-min 250 --distance-max 2000 \
  --expect-ir-valid 1 --expect-ir-stable 1 --expect-ir-mask 0 \
  --evidence-dir evidence
```

断开Echo检查无回波故障码1；保持Echo高检查卡高故障码2。左右红外遮挡分别检查mask 1、2，同时遮挡检查3：

```bash
python3 lab_acceptance.py sensor-check --label us_no_echo --count 5 --expect-us-valid 0 --expect-us-fault 1 --evidence-dir evidence
python3 lab_acceptance.py sensor-check --label us_stuck_high --count 5 --expect-us-valid 0 --expect-us-fault 2 --evidence-dir evidence
python3 lab_acceptance.py sensor-check --label ir_left --count 5 --expect-ir-valid 1 --expect-ir-stable 1 --expect-ir-mask 1 --evidence-dir evidence
python3 lab_acceptance.py sensor-check --label ir_right --count 5 --expect-ir-valid 1 --expect-ir-stable 1 --expect-ir-mask 2 --evidence-dir evidence
python3 lab_acceptance.py sensor-check --label ir_both --count 5 --expect-ir-valid 1 --expect-ir-stable 1 --expect-ir-mask 3 --evidence-dir evidence
```

每个命令要求所有采样均符合预期；首个差异会连同原始寄存器和epoch写入对应JSON后返回非零。

完成单项检查后，保持电机断开，同时接入PYNQ和STM32，运行联合安全闭环。它使用生产`PerceptionClient`读取一致快照，经生产`CarLink`更新传感器与零速命令，并把PL风险原因和STOP后的新`$CAR`放入同一时间线；不会发送PREL或非零指令：

注意：`RISK_CMD`复位为无效，当前LAB_ONLY循环也不会写它。因此首次写入生产命令并续租前，PL风险核的预期基线是`stop=1`、`level=FAULT`、原因位bit1（command invalid）为1；其他传感器尚未有效时还会叠加更多原因位。`RISK_STATE`按`reason_bits[31:16] / level[2:1] / stop[0]`解码，只剩command-invalid时为`0x00020007`。不能用始终为1的stop位证明US/IR/QEI注入生效，应检查证据中的`baseline_pl_risk`和`risk_reason_changes`。生产循环由谁写`RISK_CMD`及250ms续租策略仍等待实板联调确认。

```bash
python3 lab_acceptance.py safety-loop --port /dev/ttyPS1 --duration 30 \
  --interval 0.05 --stop-deadline-ms 300 --motor-disconnected \
  --evidence-dir evidence
```

30秒检查通过后，最终稳定性运行使用`--duration 1800`。任何非零L/R、没有新锁存状态、STOP响应超过300ms或epoch停止推进都会失败并保留`safety_loop.json`；文件同时保存解码后的首帧风险基线及原因位变化序列。

## 合格边界

联合入口`system_runtime.py`在正式计时前执行最多5秒的静止采集就绪检查，要求健康状态连续稳定300ms，结果保存为`startup_readiness.json`。若检查失败，先修正传感器/标定，再重新启动；不能跳过异常以获得联合PASS。视频启动不阻塞控制采样。视频或帧源清理超时会记录资源终止未确认并判FAIL，串口关闭仍继续执行；此时须确认板端进程和DMA已经停止，不能直接把同一Overlay交给下一次运行。

LAB_ONLY通过仍不等于release：还需真实板卡修订版、电气测量、超声波/红外故障矩阵、UART停止时延、颜色顺序、C270性能和30分钟稳定性证据。所有证据完成后再更新板级manifest并重新生成发布包。
