# 编码器电机资料与双前轮QEI实现：Codex独立复审（2026-09-20）

## 结论

ZCode关于1:48、13线、x4=2496计数/输出轮圈以及临时SCALE=5362的机械计算成立。Codex复审发现并修复2个真实问题，补齐1个原本未落地的板级安全控制；未发现需要改变双前轮QEI/同侧前后轮共享驱动的架构问题。

当前状态为：软件、RTL仿真、综合、布局布线与LAB_ONLY包通过；真实电平、计数、带载周长和同侧前后轮机械匹配仍为HARDWARE_PENDING。

## 修复项

### P1：QEI SCALE写入失败会留下半配置状态

- 位置：`pynq_fpga/host/perception_client.py`、`pynq_fpga/preintegration/host/lab_acceptance.py`
- 原问题：先写QEI0再写QEI1；第二次写入、首次读回或二次稳定读回失败时只抛异常，寄存器可能留下“一路新值、一路旧值”。
- 修复：所有写入/读回异常均尝试把两路SCALE清零并分别读回；清零无法确认时明确报告状态不确定并要求重载bitstream。没有恢复旧值，因为旧值在总线故障后不再可信。
- 证据：新增第二通道写失败、读回错误、清理失败和显式清零测试。

### P1：编码器5V来源描述含糊，可能误用Pmod电源脚

- 位置：10号硬件文档、LAB_ONLY README、交接报告
- 原问题：交接把“Pmod B的3.3V/5V脚”列为待选，但TUL R12第3页显示Pmod A/B的电源脚均为VCC3V3。
- 修复：两块霍尔编码器板固定从Arduino POWER头J7 pin 4的VCC5V0取电；Pmod只走信号与地，电机仍由TB6612供电。上板前仍须测量5V电压、纹波和实际电流。
- 本地证据：`TUL_PYNQ Schematic_R12.pdf`第3页Pmod电源网络、第4页J7 pin 4网络。

### P1：SN74LVC245A /OE方案未进入RTL和XDC

- 位置：`car_board_video_wrapper.v`、集成Tcl、XDC、board manifest与TB
- 修复：外部10k将/OE上拉到3.3V，控制线使用Pmod A JA9/W18。PL未配置时由电阻保持禁用；同步复位时RTL输出高；复位释放后才输出低。禁止硬接GND。
- 证据：板级TB对复位前后/OE做18项总检查；HWH、IO报告均包含qei_oe_n/W18。

### P2：计算器可生成寄存器范围外结果

- 位置：`pynq_fpga/host/qei_calibration.py`
- 原问题：极小正数可舍入成0，极大输入可超过0xFFFFFFFF。
- 修复：计算结果必须落在1..0xFFFFFFFF，否则拒绝；补过小与溢出反例。

## 五个交接问题的最终处理

1. /OE：已采用10k上拉+JA9/W18，代码和约束已落地。
2. 编码器5V：已采用Arduino POWER头J7 pin 4/VCC5V0；仍待实物测量。
3. 左右映射：QEI0=左前、QEI1=右前；接反时只换线。
4. SCALE失败状态：已改为双通道清零；清零无法确认时要求重载。
5. 65mm轮径：继续只作为临时值；最终按左右轮各自带载滚动周长计算。

## 验收证据

- Host单测：61项，PASS。
- Preintegration单测：21项，PASS。
- 统一门禁：`run_acceptance.ps1 -Synthesis`退出0。
- 板级wrapper：18项，PASS。
- 集成工程从零重建，route完成；WNS +0.383ns，WHS +0.039ns，阻塞DRC为0。
- 新bit/hwh已生成；HWH包含`qei_oe_n`，IO报告映射W18。
- LAB_ONLY ZIP SHA-256：`26134ff30a8886afdecd86d684078836ff39aaa116c04fc3eacd1928c2bb4ba2`。
- release门禁仍按设计阻塞：板卡修订版和11个外接电气项未做实物确认。

## 到板/到件后必须完成

先断开电机动力，核对J7 5V、JA9 /OE和LVC245两侧电平；再手转左右前轮各10圈确认约24960计数与方向；随后测左右带载滚动周长并替换5362；最后比较同侧前后轮悬空转速、电流和落地直行。未完成这些步骤前不得把electrical_ready或release_ready改为true。

