# 夜间E_板级约束与无电机验收

> 新增任务；Codex已建立可打开Vivado工程、板级manifest与release门禁，ZCode补官方证据和安全上板准备。

## 可直接发送的提示词

你执行的是2026-09-18夜间队列的夜间E，是本轮最后一项。工作目录是`C:\Users\39909\Desktop\FPGA`。先完整读取共同要求、防回退要求、`pynq_fpga/nightly/主架构_v0.6.md`、接口契约、生成寄存器表、夜间A—D交接和`pynq_fpga/README.md`。

主架构已由Codex建立：`fpga/scripts/create_architecture_project.tcl`可重建`fpga/build/car_architecture_v0_6/car_architecture_v0_6.xpr`；`fpga/board/board_manifest.json`列出逻辑端口并故意不填未核实管脚；`validate_board_manifest.py --release`会在证据不完整时失败。这是安全门禁，不得为了生成bitstream而填猜测值、删除检查或批量降低DRC。

目标：把PL候选工程推进到可审查的PYNQ-Z2板级集成骨架，完成官方管脚/电气证据链、Zynq PS连接方案和无电机首轮验收程序。只有资料和工具链证据齐全才尝试实现或bitstream；不接线、不上电、不烧录、不驱动电机。

### 实现边界

1. 先读取本文件末尾列出的本地XDC、两份PDF和board_files，逐项交叉核对并确认板卡版本；缺失信息再从智谱已在`07_开源资源借鉴与优化分析报告.md`、`08_红外超声波接PYNQ连接方案.md`、B7两份Codex基线和原开源参考要求中列出的官方PYNQ-Z2/base工程来源核实板卡文件。记录仓库URL、commit/tag、文件路径、许可证和本机Vivado 2026.1兼容性；不能用论坛二手表格覆盖官方原理图/XDC。
2. 对manifest每个外部端口逐项填写逻辑连接器、Pmod针脚、FPGA package pin、bank、电压、IOSTANDARD、方向、外部上拉/下拉和证据位置。只有至少两类一致证据或官方XDC+原理图相互对应时才能设`verified=true`。
3. 电气审查单独列门禁：HC-SR04 Echo为5V风险，未经过核实的降压/电平转换严禁直连PL；Trig路径说明3.3V是否满足模块VIH，若用AHCT125说明供电、方向和使能；红外LM393/编码器必须核实推挽或开漏，开漏则补3.3V上拉及阻值/边沿预算。不能沿用“霍尔必为5V推挽”的假设。
4. Pmod分配以主架构和用户已有线束为约束，检查与Pmod B八线、Pmod A红外、UART、摄像头/HDMI及电源占用是否冲突。发现Codex旧基线与ZCode新方案冲突时写入共同确认项，不自行静默换针。
5. 建立可复现的板级工程脚本或在现有脚本上增加明确的board模式。Zynq PS至少规划FCLK 100MHz、同步复位和GP主口到统一AXI-Lite窗口；视频链只建已验证的接口骨架，未接VDMA/HDMI时不要放空壳IP冒充完成。保留`car_perception_top`单时基/单AXI架构。
6. 若本机安装了正确board files，可生成并验证Block Design、地址分配和wrapper；否则保存工具查询证据并交付脚本。不要下载不明版本后覆盖全局Vivado安装。
7. 只有manifest release检查通过、所有顶层端口有约束、时钟/复位和CDC检查明确后，才运行实现和bitstream。实现报告须检查WNS/TNS、未约束路径、DRC、利用率和CDC；任何关键warning不能靠降级消掉。
8. 写无电机验收程序：断开/悬空电机驱动，万用表确认3.3V/5V与地，逐路静态输入，再测Echo降压、IR、双QEI、UART STOP、全局快照、风险stop，最后才是视频。每步写预期、失败即停止条件和证据照片/日志位置；本夜只写程序，不执行实物操作。
9. 更新README中真实工程入口和状态。生成的bit/hwh若未达到release门禁，不得放入release目录或写可上板；可以保留在隔离build目录并标实验产物。

### 开源参考与合规

优先使用智谱自己已经找到并写入报告的官方PYNQ-Z2 XDC/base工程、PYNQ/AMD视频接口资料，以及已经固定快照的alexforencich通用AXI模块。AMDC、HC-SR04-FPGA、Project F、Derek-X-Wang仅在其真正相关的结构中参考，不把无关代码搬进板级工程。实际采用才进入`OPEN_SOURCE_USAGE.md`；仅参考要标“无源码复制”。逐文件保留BSD-3-Clause/MIT/CC0等原许可，不重写来源或声称官方兼容。

### 自修复

执行共同要求中的自修复闭环。XDC/BD/实现失败时保存Vivado版本、board_part查询、首个错误、DRC ID、端口/管脚和修改前文件；先缩到单端口或单连接反例，再最小修复并重跑结构校验、综合和受影响实现。禁止用`set_property SEVERITY Warning`、删除端口、虚构package pin、忽略IOSTANDARD或取消release门禁换取PASS。同一错误三轮无新证据时换为官方文件对照或Tcl查询，仍受阻就保持BLOCKED并继续完成文档与独立检查。

### 验收与交付

- 普通manifest校验必须通过；release校验只有证据真的齐全才允许通过。当前预期可能仍为BLOCKED，这是比伪bitstream更正确的结果。
- 从干净目录重建xpr并检查顶层；有BD则验证BD、wrapper和地址，不得破坏A—D全回归。
- 输出管脚/电气证据表、冲突清单、Vivado结果、未约束项和无电机验收步骤。
- 写`pynq_fpga/nightly/night_20260918_E.md`，追加`self_repair_log.md`、更新`status.md`并最终更新`MORNING_HANDOFF_20260919.md`。第一屏给工程入口、软件/RTL/综合/实现/实物四层状态、P0遗留和早晨三件事。

完成后结束，不自行上板或继续驱动电机。

## PYNQ-Z2本地引脚资料（编码前必读）

项目根目录新增 `pynq-z2资料/`，涉及外部端口、XDC、PS配置、UART、Pmod、时钟/复位或视频接口的代码修改前，必须交叉核对：

- `pynq-z2资料/引脚约束文件/pynq-z2_v1.0.xdc`
- `pynq-z2资料/原理图/PYNQ-Z2_PA_v3.pdf`
- `pynq-z2资料/原理图/TUL_PYNQ Schematic_R12.pdf`
- `pynq-z2资料/board_files/pynq-z2/A.0/` 下的 `board.xml`、`part0_pins.xml`、`preset.xml`

先确认实物板卡版本与资料适配性，区分连接器针脚编号、FPGA封装管脚和PS MIO/PL IO；记录文件路径、PDF页码/图号或XDC/XML行号。核对bank供电、IOSTANDARD、输入输出方向、有效电平、上拉与外部电平转换。不得把连接器针号当作PACKAGE_PIN，不得直接套用其他开发板、旧教程或开源工程管脚。

本地资料作为首要核对入口，但“文件存在”不等于引脚已核实。资料之间或既有线束分配存在冲突时，记录差异并保留未核实状态；不要猜值、静默换针或取消release门禁。只启用实际使用端口的XDC约束；board_files通过工程级仓库路径引用，先验证Vivado 2026.1兼容性，不覆盖全局安装。

纯算法和仿真任务不必引入物理管脚，但不能臆造板级参数；在交接中注明本次参考位置或“不涉及物理引脚”。实验指导书用于流程学习，其中EES-A7资料不是PYNQ-Z2引脚依据。原始资料保留原位，代码、工程与验证产物仍写入 `pynq_fpga/`。
