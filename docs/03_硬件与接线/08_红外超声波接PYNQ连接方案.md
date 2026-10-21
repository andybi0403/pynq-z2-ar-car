# 红外与超声波连接 PYNQ 方案

> 9月18日验收修订：当前实现与测试以 `pynq_fpga/nightly/interface_contract.md` 和任务1—4验收报告为准；旧方案中的工期、参数和硬件能力描述不等于实测结果。

> 日期：2026-09-17。依据：`infrad sensor v1.0` 模块原理图、原厂 `bsp_ultrasonic.c` 驱动、BST-4WD V4.2/V4.5 原理图（J9/J10/J17/K1 接口）、PYNQ-Z2 官方 `base.xdc`、PYNQ-Z2 参考手册（Pmod 电源规格）。

## 1. 两个传感器的电气本质（先分清"协议"是什么）

### 1.1 红外避障模块（亚博 Infrared sensor v1.0，车上左右各一块）

- 电路：红外发射 LED（100Ω 限流）+ 接收管 + **LM393 比较器**，OUT 经 10kΩ 上拉到**模块自己的 VCC**。
- 输出特性：**静态电平信号，不是通信协议**——检测到障碍 OUT=低电平，无障碍=高电平（低有效）；SW11 电位器调检测距离（约 2–30cm 可调）。
- 关键推论与前提条件：
  1. **上拉接在模块 VCC 上，输出高电平=供电电压**。给模块供 3.3V，输出就是 3.3V，PYNQ 可以直读；供 5V 则必须转换。
  2. LM393 芯片供电范围 3–32V，但**芯片能工作不等于整块模块在 3.3V 下可靠**：红外发射 LED 电流随电压下降、接收管输出幅度与比较器输入共模范围都需实测。3.3V 供电属于"理论可行、待实物核验"，核验方法：3.3V 供电下分别在 0.1/0.2/0.3m 摆放障碍物，万用表读 OUT 电平并记录检测距离；不满足再切 5V 供电 + LVC245 转换的备选通道。

### 1.2 超声波模块（J17 接口，VCC/SCL_C=Trig/SDA_C=Echo/GND）

- 原厂驱动确认：**标准 HC-SR04 类脉冲协议，也不是通信协议**——给 Trig 一个 ≥10µs 高脉冲，模块发射 8 个 40kHz 声波脉冲，Echo 输出高电平，宽度=声波往返时间，距离 mm = 脉宽µs × 0.343 ÷ 2（58µs/cm）。
- 模块标称 5V 供电。3.3V 供电下发射功率不足，量程和可靠性下降，**不推荐**。
- Trig 是输入（PYNQ 3.3V 驱动 5V 模块）：HC-SR04 类输入阈值约 2V（TTL），3.3V 通常能直接触发，但亚博定制模块规格未公开，留升压芯片保险。
- Echo 是输出（5V）：**绝不能直连 PYNQ**——7 系列 HR bank 的 LVCMOS33 引脚上钳位二极管会被 5V 导通，长期损坏 IO。

### 1.3 结论表

| 传感器 | "协议" | PYNQ PL 侧处理 |
|---|---|---|
| 红外 ×2 | 静态电平（低有效） | 自研 IP 内两级同步 + 连续 3 次采样一致才更新的消抖 |
| 超声波 | Trig≥10µs 脉冲 / Echo 脉宽 | 自研 IP：计数器测脉宽（100MHz 下 1 tick=10ns，往返距离量化约 0.0017mm，器件与声速波动才是主要误差源）、**100ms 测量后空闲间隔（另加测量时间）**（<200ms 数据有效期，见 §2.1）、无回波/持续高/超量程判无效 |
| PL→PS | — | AXI-Lite 寄存器（距离 mm、有效标志、红外位图），供风险状态机与 $P 组帧 |
| PYNQ→STM32 | UART $P 帧 | 见协议 V2.1 文档 |

## 2. 接线总表（含电平处理）

### 2.1 超声波测量节拍与数据有效期（与协议强绑定的约定）

STM32 侧数据年龄上限为 200ms（超龄锁车），且 $P 心跳**不得用重发旧值延长样本寿命**。因此 PL 的超声波候选实现采用 **100ms 测量后空闲间隔**，每个等待阶段超时39ms：4m回波宽度约23.32ms，模块响应等待还需计入；当前两阶段超时预算下故障周期约178.01ms。PS轮询与串口发送时延另行核算，不能由此宣称端到端200ms已验证。PL 每完成一次真实测量即更新距离寄存器与样本时间戳，PS 组帧时读到的 V/MMM 必须对应最近一次真实样本；若采集停滞，PS 侧 pynq_link 会在样本超龄后主动发送 V=0 撤销帧（与 STM32 的 200ms 规则双保险），不允许用 100ms 心跳重发旧 V=1 掩盖采集停滞。

Pmod B 八线已满（4 编码器 + 2 超声波 + 2 UART），红外落在 **Pmod A**（官方 base.xdc 引脚已核实；Pmod A 与树莓派 GPIO 复用，本项目不用树莓派口，无冲突）。

| # | 信号 | 从（传感器侧） | 到（PYNQ 侧） | 方向 | 电平处理 |
|---|---|---|---|---|---|
| 1 | 左编码器 A/B | 霍尔编码器TT马达（左前轮，板载上拉，5V域） | Pmod B 1/2（W14/Y14） | →PYNQ | SN74LVC245A ch0/1 |
| 2 | 右编码器 A/B | 霍尔编码器TT马达（右前轮） | Pmod B 3/4（T11/T10） | →PYNQ | LVC245 ch2/3 |
| 3 | 超声波 Echo | J17.3（SDA_C） | Pmod B 8（W16） | →PYNQ | LVC245 ch4 |
| 4 | 超声波 Trig | J17.2（SCL_C） | Pmod B 7（V16） | ←PYNQ | 直连（实测不行则 74AHCT125 升压） |
| 5 | 左红外 OUT1 | J9.2 | Pmod A 1（Y18） | →PYNQ | **3.3V 供电直读，无转换** |
| 6 | 右红外 OUT2 | J10.2 | Pmod A 2（Y19） | →PYNQ | 同上 |
| 6b | 扩展编码器（左后 A/B） | 编码器电机 | Pmod A **3/4**（Y16/Y17） | →PYNQ | 第二片 LVC245（见 09 选型报告） |
| 6c | 扩展编码器（右后 A/B） | 编码器电机 | Pmod A **7/8**（U18/U19） | →PYNQ | 同上；实体 9/10（W18/W19）留作余量，**实体 5=GND、6=3.3V 不可作信号** |
| 7 | 红外供电 | Pmod A 6/12 脚（3.3V） | J9.1 / J10.1 | — | 每模块约 20–25mA，两模块约 50mA，PYNQ-Z2 每 Pmod 3.3V 可供约 1A，余量充足 |
| 8 | 超声波供电 | J17.1（VCC） | 保持原车 MVCC 轨 | — | 保持 5V 原厂工况；MVCC 实际电压用万用表核对（板上 3.3V/5V 跳线），**不建议改由 PYNQ 供电** |
| 9 | UART TX | Pmod B 9（V12） | K1.3 → 经S5接通2–3 → STM32 PA3/USART2_RX | ←PYNQ | 图纸映射；当前USART1/2自识别固件与现有接线已通信通过，见17号实测报告 |
| 10 | UART RX | Pmod B 10（W13） | K1.4 ← STM32 PA2/USART2_TX | →PYNQ | 图纸针号勘误；现装有效UART路径按17号实物证据与r3修复方案使用 |
| 11 | 共地 | Pmod A/B GND（5/11 脚） | K1.2、小车信号地 | — | 单点共地；PYNQ 独立电源不接小车电 |

XDC 约束（全部 LVCMOS33。**2026-09-19核定：编码器A/B不启用PULLUP**——编码器板自带板载上拉（手册原文），且经SN74LVC245A推入3.3V，PL侧加PULLUP反而无益；Echo经LVC245同理不启用；红外3.3V直读由模块自身10k上拉决定电平，也不需要。**旧版"编码器/Echo/红外输入建议加PULLUP true"一句废止**）：

```tcl
# Pmod B（沿用 codex 分配）
set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {enc_l_a}]; # PmodB1
set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports {enc_l_b}]; # PmodB2
set_property -dict {PACKAGE_PIN T11 IOSTANDARD LVCMOS33} [get_ports {enc_r_a}]; # PmodB3
set_property -dict {PACKAGE_PIN T10 IOSTANDARD LVCMOS33} [get_ports {enc_r_b}]; # PmodB4
set_property -dict {PACKAGE_PIN V16 IOSTANDARD LVCMOS33} [get_ports {us_trig}]; # PmodB7 输出
set_property -dict {PACKAGE_PIN W16 IOSTANDARD LVCMOS33} [get_ports {us_echo}]; # PmodB8 输入
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports {uart_tx_o}]; # PmodB9
set_property -dict {PACKAGE_PIN W13 IOSTANDARD LVCMOS33} [get_ports {uart_rx_i}]; # PmodB10
# Pmod A（红外 + 历史扩展编码器脚位记录，官方 XDC 核实；实体脚：1-4=信号，5=GND，6=3.3V，7-10=信号，11=GND，12=3.3V）
set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports {ir_left}];   # PmodA1 红外左
set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports {ir_right}]; # PmodA2 红外右
set_property -dict {PACKAGE_PIN Y16 IOSTANDARD LVCMOS33} [get_ports {enc_l2_a}]; # PmodA3 扩展编码器（历史扩展建议，当前不实施）
set_property -dict {PACKAGE_PIN Y17 IOSTANDARD LVCMOS33} [get_ports {enc_l2_b}]; # PmodA4 扩展编码器（同上）
set_property -dict {PACKAGE_PIN U18 IOSTANDARD LVCMOS33} [get_ports {enc_r2_a}]; # PmodA7 扩展编码器（实体5/6为GND/3.3V，历史扩展建议，当前不实施）
set_property -dict {PACKAGE_PIN U19 IOSTANDARD LVCMOS33} [get_ports {enc_r2_b}]; # PmodA8 扩展编码器（同上）
```

**编码器电气结论（2026-09-19核定，详见10号文档）**：编码器为松甲霍尔编码器TT马达（1:48，双前轮），编码器电压4.5V—5V、AB相90°正交、**板载上拉输出**（手册原文）；A/B经SN74LVC245A（VCC=3.3V、输入5V容忍）进Pmod B，PL侧无PULLUP、不另加外部上拉。旧版"输出类型按推挽/开漏分支处理"的编码器条目废止。

## 3. 需要的连接模块（采购/制作清单）

| 物品 | 数量 | 作用 | 备注 |
|---|---|---|---|
| SN74LVC245A（DIP-20，3.3V 供电） | 2（1 用 1 备） | 5V→3.3V 单向转换：4 编码器 + Echo = 5 通道，余 3 通道留给"红外 3.3V 直读失败改 5V 供电"的备选路线 | LVC 家族输入 5V 容忍，B 侧接 PYNQ；DIR 固定 A→B |
| 74AHCT125（DIP-14，5V 供电） | 1 | Trig 3.3V→5V 升压（1 通道，余通道备用） | 若实测 3.3V 能稳定触发可免装 |
| Pmod 2×6 母座（或成品 Pmod 线） | 2 | Pmod A/B 引出 | 也可买 Pmod 转杜邦转接板 |
| PH2.0-4P 端子线（公对线） | 3 | J17 超声波、J9/J10 红外原接口引出 | 原车接口即 PH2.0 |
| 洞洞板 5×7cm + 排针排母 + 硅胶线 | 1 套 | 焊"信号转接小板"：LVC245 + AHCT125 + 2×Pmod 母座 + 3×PH2.0 端子 | 转换器全部集中在这一块板上 |
| 杜邦线、热缩管 | 若干 | — | — |

## 4. 需不需要自己画 PCB？

**结论：不需要，洞洞板转接小板即可满足比赛全部要求。**

- 命题指南评分里对硬件的要求是"自制部分的图纸、BOM 或接线图"——洞洞板 + 接线图 + BOM 完全合规；核心得分点在 PL 自研 IP 和系统集成，不在 PCB。
- 转接小板只有 2 颗 IC + 接插件，洞洞板 1–2 小时焊完，配合热熔胶固定可靠性足够。
- **可选加分路线**：如果时间富余（基础系统稳定后），画一块 2 层"传感器信号转接板"（嘉立创免费打样，约一周周期）——把 Pmod A/B 母座、LVC245、AHCT125、3×PH2.0 端子集成，替代洞洞板。价值：可靠性更好 + 报告"自制 PCB"叙事 + 工程完成度分。时间节点：11 月 1 日交设计文档，打样需在 10 月中旬前冻结原理图，**做不完就保持洞洞板，不要为它挤占联调时间**。

## 5. 转接小板内部连接（焊接待查清单）

```text
Pmod B 母座(2×6)                SN74LVC245A (VCC=3.3V, GND=PYNQ GND, DIR=H, OE=GND)
  1 W14 ←B0─── A0                A0..A4 ← 传感器 5V 侧（编码器×4、Echo）
  2 Y14 ←B1─── A1                B0..B4 → PYNQ 侧（W14/Y14/T11/T10/W16）
  3 T11 ←B2─── A2
  4 T10 ←B3─── A3                74AHCT125 (VCC=5V)
  7 V16 →A输入──1A/1Y→ J17.2      1A ← PmodB7(V16)，1Y → J17.2(Trig)
  8 W16 ←B4─── A4 ← J17.3(Echo)
  5/11 GND、6/12 3.3V             每颗 IC 的 VCC-GND 之间 100nF 去耦电容
Pmod A 母座(2×6)
  1 Y18 ←── J9.2 (OUT1)          （3.3V 直读）
  2 Y19 ←── J10.2 (OUT2)
  6/12 3.3V ──→ J9.1、J10.1（红外供电）
  5/11 GND ──→ 与小车信号地共地
```

## 6. 上电前核对清单（新增项并入改装说明清单）

- [ ] 万用表实测 J17.1（VCC）与 J9.1/J10.1 对地电压，确认 MVCC 轨实际电压与跳线位置。
- [ ] 红外模块 3.3V 供电下实测：有/无障碍的 OUT 电平与检测距离，不满足再切 5V+LVC245 备选通道。
- [ ] LVC245 方向跳线/DIR 脚确认（A→B 单向），每 IC 去耦电容已焊。
- [ ] **编码器（2026-09-19核定，10号文档为准）**：霍尔编码器板载上拉、4.5V—5V供电，A/B必经LVC245进PL，**PL侧无PULLUP、不另加上拉**；逐针通断确认PH2.0-6P线序（手册针序见10号文档第3节）后才能上电。
- [ ] Echo在5V侧的上拉/推挽类型确认，**按输出类型分支处理**：
  - 推挽输出：经 LVC245 直接转换，无需上拉；
  - 开漏/集电极开路输出：必须在 **5V 信号侧**上拉到 5V 后再进 LVC245（若某路不经 LVC245 直进 PL，则该路上拉到 3.3V；严禁开漏输出悬空，也严禁把上拉到 5V 的信号绕过转换器直进 PL）。
- [ ] 超声波 **100ms 测量后空闲间隔（另加测量时间）**下 Echo 波形逻辑分析仪抓取（余波、无回波、持续高三种异常都要复现过），并确认相邻测量无回波串扰。
