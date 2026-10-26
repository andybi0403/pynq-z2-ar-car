# 夜间A—E主架构预置与ZCode交接

日期：2026-09-18  
结论：Codex已先建立A—C主架构，并为新增D/E建立可测试骨架；五份提示词已改为沿主线增量开发。

## 已完成的主架构

| 夜间任务 | Codex已预置 | ZCode今晚重点 |
|---|---|---|
| A 安全闭环 | 四级流水`car_risk_core`、原因位、反向轮速故障、命令续租参与输出批次、统一顶层接入、20项TB | 真实Python→协议字节→STM32 C闭环、9600bps时限预算、恢复/解锁反例 |
| B 流式OSD | 纯AXIS RGB888核、握手坐标、背压保持、SOF状态提交、风险边框/状态块、1292项TB | 数字/负号/无效显示、逐像素软件参考、仿真输出PNG、异常恢复 |
| C 统一集成 | `car_perception_top`单时基/单AXI/全局快照、生成式寄存器表、可打开xpr、重建/检查Tcl | 合并A/B增量、系统回归、工程重建、准确早晨交接 |
| D PS驱动/回放 | `PerceptionClient`、版本门控、epoch快照、有符号解析、回绕年龄、fake transport 4项测试 | PYNQ MMIO适配、JSONL记录/回放、真实UART/C软件闭环 |
| E 板级验收 | board manifest、结构校验、release失败门禁、PL工程和时钟XDC骨架 | 官方XDC/原理图证据、Pmod/电气核验、PS BD骨架、无电机验收程序 |

## 关键优化

1. 风险停止距离不再形成约30ns长组合路径。乘法、定点倒数、距离和与策略比较分成四级，同一批metadata随流水移动。统一顶层100MHz OOC综合WNS为+2.367ns。
2. 风险发布签名包含四路seq以及命令时间/有效/方向/使能。即使命令方向不变，续租写入也会形成新评估批，避免风险时间戳停留在旧值。
3. 寄存器只维护`register_map.json`，自动生成Verilog、Python和Markdown，版本为`0xC4251006`。主机发现版本不一致立即失败。
4. 全局快照用epoch建立读取屏障；各源自己的sample_ts/seq/valid仍保留。PS客户端不把全局快照时间冒充采样时间。
5. 板级管脚未核实时保持空值。普通manifest结构检查通过，`--release`明确返回1并列出10个未核实端口及三类缺失证据。

## 验证结果

- 两版STM32 C测试通过。
- 原PC通信18项通过；统一主机客户端4项通过。
- 寄存器生成器一致性检查通过；板级manifest普通模式通过。
- RTL共1634项检查通过：AXI 104、传感器43、QEI 31、速度124、风险20、统一顶层20、OSD 1292。
- 五个OOC综合门槛通过；统一顶层使用2983 LUT、3745寄存器、9 DSP，WNS +2.367ns；OSD WNS +3.677ns。
- Vivado 2026.1已重建并重新打开检查`car_architecture_v0_6.xpr`，顶层为`car_perception_top`。

以上是软件、RTL和OOC综合证据。PS/DDR/VDMA/HDMI、完整板级XDC、实现、bit/hwh、上板和实物停止时间均未通过，不能在夜间报告中升级表述。

## 文件入口

- 架构：`pynq_fpga/nightly/主架构_v0.6.md`
- 接口：`pynq_fpga/nightly/interface_contract.md`
- 工程：`pynq_fpga/fpga/build/car_architecture_v0_6/car_architecture_v0_6.xpr`
- 回归：`pynq_fpga/fpga/scripts/run_acceptance.ps1`
- 队列：`9.18夜间任务队列/00_今晚排队顺序与共同要求.md`
- 预算：`9.18夜间任务队列/02_两亿Token工作量估算.md`
- 提示词：同目录`夜间A_...md`至`夜间E_...md`

ZCode每项必须读取前项交接，按A→B→C→D→E排队。不得覆盖历史交接，不得另建平行架构，不得为获得PASS放宽安全阈值、删除断言或填猜测管脚。
