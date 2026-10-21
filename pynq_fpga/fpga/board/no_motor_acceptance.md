# PYNQ-Z2无电机首轮验收程序

本程序只定义操作与证据，不表示已经上板执行。任何一步失败，保持STM32锁存且停止后续步骤。

## PL风险命令基线

`RISK_CMD`是只写寄存器，复位后`command_valid=0`。在PS首次写入有效命令并持续续租以前，PL风险核保持`stop=1`、`level=FAULT`且原因位bit1（`R_CMD_INVALID`）为1，这是预期的失效安全基线，不代表某次故障注入已经生效。`RISK_STATE`位布局为`reason_bits[31:16] / reserved[15:3] / level[2:1] / stop[0]`；若其他传感器均有效且只剩命令无效，原始值为`0x00020007`，实际首次快照还可能同时包含其他无效原因位。

当前LAB_ONLY `safety-loop`不会写`RISK_CMD`，也不会清除此基线。步骤9—10必须比较`reason_bits`在注入前后的变化，不能只看始终为1的`stop`位。生产循环的`RISK_CMD`写入与250ms续租策略仍为到板后待确认项。

| 步骤 | 操作 | 预期 | 失败即停止条件 | 证据 |
|---:|---|---|---|---|
| 1 | 断开TB6612电机输出或可靠拔除四个电机；PYNQ与小车分别断电 | 电机物理上不可能转动 | 不能确认断开 | `evidence/E/01_motor_disconnected.jpg` |
| 2 | 核对PYNQ丝印、PCB修订和跳线；比对R12/PA_v3 | 与本地资料一致 | 修订不明或网络不同 | `02_board_revision.jpg` |
| 3 | 只给两板上电，不接信号；测Pmod 3.3V、小车5V/3.3V与两板GND | 电压在器件额定范围，地电位差可接受 | 过压、反接、异常发热 | `03_power.csv` |
| 4 | 断电接共地和转换板；逐路测LVC245/AHCT125方向、OE与去耦 | 输出不超过3.3V，未出现悬空 | 任一PL输入可能见5V | `04_level_shift.csv` |
| 5 | 只接Echo/Trig；运行固定10us Trig，测试正常、无回波、持续高；分别用`lab_acceptance.py sensor-check`核对正常、fault 1、fault 2 | PL分别给出有效距离、无回波、卡高故障 | Echo>3.3V或故障分类错误 | `evidence/sensor_normal.json`、`sensor_us_no_echo.json`、`sensor_us_stuck_high.json` |
| 6 | 只接两路红外；分别遮挡/释放并测OUT；用`sensor-check`核对mask 0/1/2/3及stable | 低有效状态、消抖和IR故障位正确 | 3.3V供电不稳定或高电平超限 | `evidence/sensor_ir_clear.json`、`sensor_ir_left.json`、`sensor_ir_right.json`、`sensor_ir_both.json` |
| 7 | 只接左右前轮QEI（经LVC245）；手动慢转轮，不接电机 | A/B相序、计数方向、非法跳变和零速有效符合预期 | 信号超限、相序不明、计数漂移 | `07_qei.csv` |
| 7a | 编码器5V侧与LVC245 3.3V侧分别示波器/逻辑分析仪抓A/B：高低电平、慢转与较快转动边沿 | 5V侧高电平≤5.5V且稳定；3.3V侧0—3.3V满摆幅、无振铃回勾 | 转换后幅度不足、边沿毛刺、5V出现在PL侧 | `07a_qei_levels.csv` |
| 7b | 电机动力线断开，左前/右前轮分别手转整10圈，读两路POS_LIVE增量并多圈平均 | 每路10圈约24960个x4计数（1:48，13×48×4；边界±几计数属正常） | 明显接近46800（买到1:90）或偏离24960超出边界误差——保持SCALE=0并停止联调 | `07b_handroll_counts.json` |
| 7c | 同侧前后轮悬空对比：只给同侧供电低占空比转动，观察前轮QEI速度与后轮目视/听觉转速差、电流 | 同侧前后轮转向一致、转速差可接受 | 反向或转速差过大：换/匹配电机处理，不得用SCALE或PID掩盖 | `07c_side_pair.json` |
| 7d | 原装轮胎、正常整车载荷下，左右轮分别推车测多圈实际滚动距离 | 每圈滚动距离=总距离/圈数，左右分别记录 | 不做带载标定而直接写直径估算值 | `07d_rollout.csv` |
| 7e | 用`lab_acceptance.py qei-config --motor-disconnected`写两路SCALE：先`--qei-profile TT_48_ORIGINAL_WHEEL_FRONT_2`（临时5362），带载标定后用`--left-scale/--right-scale`写实测值并读回验证 | 寄存器读回与写入一致，正反转符号与mm/s量级正确，累计距离与动态风险输入联动 | 读回不一致、符号错误或单位异常——失效安全停车 | `evidence/qei_config.json` |
| 7f | 转接板`/OE`装10k上拉到3.3V并接JA9/W18；分别在PL未配置、同步复位、复位释放后测量 | 前两阶段高电平禁用，复位释放后低电平使能；任一异常均不接A/B到PL | 上电即低、悬空、振荡或电平超限 | `07f_qei_oe.csv` |
| 8 | 拔下蓝牙，接UART TX/RX/GND；先只发送STOP/零速有效帧 | 9600 8N1、帧校验和锁存原因正确 | 任一运动输出或双驱动冲突 | `08_uart_stop.log` |
| 9 | 读取ID `0xC4251006`，触发全局快照并检查epoch和各组seq/ts；记录首次`RISK_STATE`解码值 | 同一epoch、独立时间戳、不撕裂；未写`RISK_CMD`时command-invalid基线明确 | ID错误、epoch不变/撕裂，或把基线stop误当注入结果 | `09_snapshot.jsonl` |
| 10 | 运行`lab_acceptance.py safety-loop --motor-disconnected`，依次注入US超龄、IR障碍、QEI无效和命令租约过期；比较`risk_reason_changes` | 同一时间线内新增原因位与注入一致，STM32新`$CAR`保持锁存零输出 | 原因位不随注入变化、任一故障允许非零输出、epoch停止或STOP响应>300ms | `evidence/safety_loop.json` |
| 11 | 不接摄像头，先显示RGB色条；再接C270读取900帧 | 色序正确、HPDN/VDMA IRQ工作，无地址漂移 | 黑屏、色序错、丢帧超预算 | `11_video_metrics.json` |
| 12 | 维持电机断开，以`--duration 1800`运行联合安全闭环，同时运行视频压力测试 | 无锁死、超温、地址/epoch漂移 | 任一异常或自动恢复运动 | `evidence/safety_loop.json`、`12_soak.log` |

完成以上证据后仍只允许轮子悬空、低占空比电机测试；地面运动和解除release门禁需要单独人工确认。

QEI补充（2026-09-20）：落地直行测试仍属release后人工确认项，但记录要求提前明确——正常载荷直线行驶固定距离，比对两路QEI里程与实际距离、左右偏差；同侧前后轮共享PWM，前轮QEI即该侧速度，后轮无可观测性，不虚构后轮数据。LVC245 `/OE`固定采用10k上拉到3.3V并由JA9/W18控制，须在步骤4和7f记录配置前、复位中及复位释放后的电平；禁止硬接GND。
