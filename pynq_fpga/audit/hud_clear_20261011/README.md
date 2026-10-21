# HUD 去黑底与字形清晰度修改

左上角速度及六行状态信息采用透明底；距离读数与前方测距标注保留深色底。右上角状态灯区域及“安全、注意、紧急”文字透明底。左上角与测距使用原生 24px Noto Sans SC SemiBold 字形，右上角使用原生 32px；每个字形采用一像素轮廓描边，改善明暗背景下的可读性。

原生成器把字符串与字体内部字节串变体名称比较，未选中 SemiBold；本次修正。保留原 16px 文件并新增 24px/32px 字库。仅修改显示和对应验证，无传感器、判定阈值、运动控制或标定改动。

## 验证与边界

- 真实 RTL 仿真：大字、测距、右上角圆圈、帧边界、停顿握手。独立像素比较用于检查透明区域与字形位置。首次圆圈测试发现尾部空白字符区域遮挡圆圈，修复后重新通过；首次失败证据保留。
- `before.png`、`after.png`、`comparison.png` 是历史摄像头原始图像输入实际 RTL 链得到的仿真结果；详情见 `preview_input_scope.json`。不是当前板子输出，画面中的无效数据不构成传感器或安全判定验收。
- 使用 ROSS 的 RTL lint / XSim 技能与 AMD 官方文档核对检查方式。当前 ROSS MCP 没有可用 Vivado 会话启动接口，执行采用本地 Vivado 2026.1。
- lint 已完成，但有警告；最终计数与报告版本见 `lint_summary_final.json`。报告文件虽用 `.csv` 后缀，工具实际写入 ASCII 表格；按其真实格式提取，没有豁免，不能称为零告警。前方测距使用黑底，因此未使用该模块字库中的描边平面。
- 坐标截断用于有界字形区域（24px 单元、32px 灯文字）；圆圈局部 8bit 坐标为既有模运算设计。十进制转换函数已完整默认赋值；灰度加和受像素范围约束并按既有设计舍弃低两位。未使用端口/寄存器警告保留，未添加 lint 豁免。质量/时序仍以完整综合实现结果为准。
- 首次完整构建在 car_axis_osd OOC setup slack = -0.062ns 时拒绝继续，失败记录保留。加入可停顿的字体级，将 ROM/位选择与颜色叠加分开；吞吐仍为每时钟一个像素，增加一级延时（100MHz 时 10ns）。新的三个显示模块 OOC 时序检查结果：car_axis_osd +0.132ns、car_axis_front_overlay +0.445ns、car_axis_status_osd +2.764ns。状态行初版常数除法的 -1.177ns 问题，通过并行字符区域译码解决；独立像素比较仍为零差异。
- 第二次整板构建实际布线 setup WNS = -0.280ns、hold WHS = +0.051ns，流水线拒绝继续，未生成可用候选包。失败路径是前方测距标注与主叠字的字符坐标除法，使用与状态行相同的有界并行译码修复。更新后主叠字 OOC 余量 +1.642ns、前方测距 +1.555ns；独立像素比较保持零差异。原失败的 routed DCP 和时序报告保留。
- 新的完整候选构建：`preintegration/evidence/complete_v09_hud_clear_20261011_r3/pipeline.json`，初始上板状态 PENDING；构建过程绑定全部权威源码哈希。最新预览取自 `hud_preview_20261011_after_r4`，`preview_source_identity.json` 核对其源码与候选捕获完全相同，前一版输出未覆盖。
- ROSS 时序 methodology 检查在失败的 routed DCP 上实际执行。报告存在 TIMING-18 的 10 条外部 I/O 延时警告，以及 rgb2dvi IP XDC 查询效率 XDCB-5 的 1 条警告；这些不是字体除法造成的 setup 失败。未推测外设延时值，未修改时钟约束，未添加 false path 或豁免。对应端口属性、时钟与路径报告保存在原失败实现目录的 `results/` 中。最终布线后需保留同样检查结果，不称为全局零告警。
- 当前未检测到板子调试串口，未执行烧录或上板验收；本次没有切换电脑 Wi-Fi、修改路由或网络适配器。

最终构建结果以流水线记录为准；构建 PASS 也不等于硬件 PASS。

## 最终结果

`v09_hud_clear_20261011_r3` 完整流水线全部阶段 PASS，状态为 LAB_ONLY_CANDIDATE。18 项 RTL 仿真、独立像素比较、10 个模块综合、整板布线、DRC 门槛、源码一致性与便携包检查通过；最终 setup WNS +0.280ns、hold WHS +0.011ns。

最终 methodology 仍为 TIMING-18 10 条与 XDCB-5 1 条，与修复前一致，没有豁免或约束源码修改。详细报告位于新实现目录的 `METHODOLOGY_RESOLUTION_REPORT.md`，汇总与包身份核对见本目录 `final_validation.json`。

候选包：`pynq_fpga/lab/task7_8_lab_only_v09_hud_clear_20261011_r3.zip`；SHA256 `a6f8d02f4a98bbaf12026a634554548b6104bca27326305d15fbb0e1cfc0e8d2`。包生成后未修改其内容。

当前上板状态仍为 PENDING，没有烧录或物理摄像头验收；预览为历史原始摄像头帧经过最终 RTL 的仿真结果。
