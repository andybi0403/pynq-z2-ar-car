# PYNQ-Z2板级管脚与电气审查（夜间E）

更新：2026-09-19。状态：板卡侧管脚证据完成；编码器型号/输出与接口方案已按厂家手册核定（见`docs/03_硬件与接线/10_霍尔编码器TT马达电气与QEI参数核定_20260919.md`）；**实物转换前后电平与上电顺序未测**，外接传感器与STM32电气仍待实物测量，release保持阻断。

## 证据优先级与板卡版本

本审查使用以下本地资料交叉核对：

1. `pynq-z2资料/引脚约束文件/pynq-z2_v1.0.xdc`：Pmod A/B与HDMI Tx的PACKAGE_PIN、IOSTANDARD。
2. `pynq-z2资料/board_files/pynq-z2/A.0/part0_pins.xml`：JA/JB和TMDS逻辑管脚到封装脚的第二份映射。
3. `pynq-z2资料/原理图/TUL_PYNQ Schematic_R12.pdf`：第3张图确认Pmod实体针脚、VCC3V3与保护网络；第6张图确认HDMI Tx/HPDN；第11张图确认Bank 34/35和封装脚。
4. `PYNQ-Z2_PA_v3.pdf`：确认双Pmod、USB Host和HDMI等板卡功能，但不用于代替逐脚XDC。

资料内部能够对应PYNQ-Z2、`xc7z020clg400-1`和board files A.0。当前没有实物丝印照片，故`hardware_revision_confirmed=false`；这不会阻止候选工程实现，但会阻止release。

## 连接分配

| 功能 | 连接器 | PACKAGE_PIN | Bank | 方向 | IOSTANDARD | 板卡证据 | 外接电气状态 |
|---|---|---:|---:|---|---|---|---|
| 左QEI A/B | JB1/JB2 | W14/Y14 | 34 | 输入 | LVCMOS33 | XDC + part0_pins + R12 | 霍尔编码器（左前轮）板载上拉、4.5—5V、必经LVC245；转换前后电平未实测 |
| 右QEI A/B | JB3/JB4 | T11/T10 | 34 | 输入 | LVCMOS33 | 同上 | 同上（右前轮） |
| 超声Trig | JB7 | V16 | 34 | 输出 | LVCMOS33 | 同上 | 3.3V直驱是否可靠待测；失败时使用5V供电AHCT125 |
| 超声Echo | JB8 | W16 | 34 | 输入 | LVCMOS33 | 同上 | HC-SR04类5V Echo严禁直连，必须先降到3.3V |
| PS UART1 TX/RX | JB9/JB10 | V12/W13 | 34 | 出/入 | LVCMOS33 | 同上 | STM32 PA3/PA2应为3.3V；实物测量和TX/RX交叉待确认 |
| 左/右红外 | JA1/JA2 | Y18/Y19 | 34 | 输入 | LVCMOS33 | 同上 | LM393 OUT上拉到模块VCC；3.3V供电检测距离待测 |
| QEI电平转换使能 `/OE` | JA9 | W18 | 34 | 输出 | LVCMOS33 | 外部10k上拉到3.3V | 配置前默认禁用；`car_board_video_wrapper`仅在同步复位释放后拉低使能 |
| HDMI TMDS | HDMI OUT | L16/L17等 | 35 | 输出 | TMDS_33 | XDC + part0_pins + R12 | 板载固定网络，板卡侧完成 |
| HDMI HPDN | HDMI OUT pin19 | R19 | 34 | 输入 | LVCMOS33 | XDC + part0_pins + R12 | Q8反相、R158上拉，主动低 |

完整逐端口机器表见`board_manifest.json`。Pmod B的八个信号位全部占用；Pmod A启用JA1/JA2和JA9，扩展四轮编码器的JA3/JA4/JA7/JA8暂不进入首版约束。

## 电气门禁

- **Echo**：按5V危险源处理。允许路线为5V侧信号进入3.3V供电、输入5V容忍的SN74LVC245A，再到W16；禁止分压值未知、BSS138 I2C双向板或直接连接。
- **Trig**：先在示波器/逻辑分析仪下验证V16的3.3V脉冲能稳定触发。若不稳定，使用5V供电74AHCT125，固定方向并使能；不得使用3.3V供电的普通HC系列声称输出5V。
- **红外**：LM393是开集电极结构，模块现有10k上拉到模块VCC。只有模块以3.3V供电并实测检测距离与高低电平后才允许直连；若必须5V供电，则经LVC245或把经核实可修改的上拉改到3.3V。
- **编码器**（2026-09-19核定，10号文档为准）：松甲霍尔编码器TT马达1:48，编码器电压4.5V—5V、AB相90°正交、**板载上拉输出**（手册原文，未证实输出级为推挽或裸开漏，对PYNQ按5V域高电平处理）。A/B必经3.3V供电、输入5V容忍的SN74LVC245A（DIR固定A→B，VCC-GND近端100nF去耦），PL侧XDC不启用PULLUP、不另加外部上拉；旧版"开漏优先上拉3.3V直入PL"分支废止。禁止把5V A/B直连PL，禁止电阻分压或74AHCT125替代LVC245方向。`/OE`优先10k上拉到3.3V默认禁用+使能点拉低；若硬接GND必须在验收记录注明上电顺序限制。编码器5V先上电、PYNQ掉电/未配置、反向上电顺序均为release实测项；未实测前`electrical_ready=false`。
- **UART**：只连TX、RX、GND，不连接两板正电源；拔下蓝牙模块，防止两路驱动冲突。
- **共地与供电**：PYNQ独立供电，小车动力电源不与PYNQ正极并联；非隔离信号必须单点共地。

## 冲突处理

- Codex旧基线写“红外不进第一版主线”，zcode新方案把两路红外放在Pmod A。当前RTL和安全协议已正式使用IR，采用Pmod A JA1/JA2方案。
- 旧PYNQ Base Overlay把HDMI Tx HPD当GPIO输出；R12第6张图显示`HDMI_TX_HPDN`经Q8/R158形成主动低输入。当前工程按输入处理。
- 首版只接左右前轮各一只编码器电机（QEI0=左前、QEI1=右前）。四轮扩展占用Pmod A的方案不进入本轮顶层，避免与首版验收范围混淆；同侧前后电机共用PWM，后轮无编码器与独立可观测性。

## Release条件

只有完成实物板卡修订版确认、Echo转换、Trig阈值、红外3.3V工作、编码器转换前后电平与上电顺序实测（10号文档第10节清单全部勾选）、UART电平/冲突和共地检查，才可将对应`electrical_ready`改为true。所有项都有照片或仪器日志后，才允许设置`hardware_revision_confirmed=true`和`release_ready=true`。编码器电气方案核定本身不解除release阻断。
