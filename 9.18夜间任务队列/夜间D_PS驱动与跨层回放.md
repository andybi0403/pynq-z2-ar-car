# 夜间D_PS驱动与跨层回放

> 新增任务；Codex已建立主机访问骨架，并继续完成适配、回放和跨层闭环。
> 2026-09-19 Codex接管夜间A后同步：D必须复用A已验收的生产链路和真实C夹具。
> 2026-09-19起由Codex在C验收后连续执行，不再交给ZCode。

## Codex后台执行任务书

Codex在夜间C完成并验收后连续执行夜间D。工作目录是`C:\Users\39909\Desktop\FPGA`。先完整读取：

- `9.18夜间任务队列/00_今晚排队顺序与共同要求.md`
- `9.18夜间任务队列/01_上次错误与防回退要求.md`
- `pynq_fpga/nightly/主架构_v0.6.md`
- `pynq_fpga/nightly/interface_contract.md`
- `pynq_fpga/nightly/register_map_v0.6.md`
- `pynq_fpga/nightly/night_20260918_A.md`（必须先读，接口已冻结）
- 夜间B—C实际交接及`pynq_fpga/nightly/status.md`

主架构已经存在，不要重建第二套驱动。`pynq_fpga/host/perception_client.py`已经提供`read32/write32`抽象、ID版本门控、基于`SNAP_EPOCH`的全局一致快照、有符号Q16.16解析、命令写入和32位回绕年龄函数；`host/car_regs.py`由`register_map.json`自动生成。现有4项单测通过。你应在这条主线上增量开发，发现真实反例再做最小修复。

夜间A也已经建立唯一跨层证据链：`host/c_build/build_car_c_dll.ps1`固定编译`stm32_pynq*`对接版生产C并校验SHA，`host/tests/test_night_a_loop.py`按100ms Python发送、10ms C tick和串行9600bps传输运行15项闭环，`stm32预备程序/pc/pynq_link.py`的17项链路单测通过。D只能调用或扩展这些入口，禁止复制`CSafe` ABI、另建DLL脚本、另写Python安全状态机或把发送决策改成每10ms调用。

目标：建立可在PYNQ上替换传输层的MMIO适配、确定性记录/回放和“PL快照→PS策略/协议→实际STM32 safe_control”的软件闭环。没有板卡时完成软件与模型证据，不把回放写成实物结果，不打开真实串口发送运动帧。

### 实现边界

1. 为`RegisterIO`提供PYNQ MMIO适配，构造时显式传基地址/长度；导入PYNQ失败时给清楚错误，不在开发机伪装硬件。业务层不得直接散落`mmio.read(offset)`，所有地址只从生成的`car_regs.py`读取。
2. 每次启动先验证`INTEGRATED_ID=0xC4251006`。版本错、epoch不变化、快照读取中epoch变化、valid失败、样本达到年龄阈值、方向原因位或风险stop出现时，输出保持STOP/无效，不回退到旧缓存。
3. 补完整的PL时基读取：用CTRL时间锁存或同等原子机制读取64位tick；年龄计算在PL自己的32位低位域完成。PS monotonic只用于调度和测量软件延迟，禁止直接减PL sample_ts。
4. 定义小而稳定的JSONL回放格式：文件头含schema、寄存器契约版本、100MHz tick、来源和是否硬件；每条记录含采集顺序、原始寄存器值、epoch、主机接收时间和预期安全输出。保留原始值，派生字段可重算。
5. 写record/replay工具。回放必须使用同一个`PerceptionClient`解析路径或等价的只读transport，不能复制一套简化解析器。加入正常、冻结US、冻结驾驶请求、无效QEI、IR触发、时间回绕、epoch撕裂、版本错误和坏记录反例。
6. 直接复用夜间A的`pynq_link.py`、`build_car_c_dll.ps1`和`test_night_a_loop.py`。生产路径分别调用采样更新与驾驶请求更新；传感器更新不能续驾驶租约，驾驶心跳不能刷新样本时间。`drive()`与`update_command()`必须继续使用注入时钟。9600bps传输按同一线路串行排队，不能让多个write并行完成。
7. 解锁序列保持STM32既定语义：先用真实有效、零速、IR清除且距离≥250mm的帧连续维持至少300ms，再显式调用`release_request()`；PREL只进入“等待释放后新意图”状态，之后到达的新驾驶请求才可恢复。不得在开始安全保持时立即发PREL、自动重试PREL、把释放前命令标成新意图或重放旧运动。有效IR必须以`V=1/L=R=0/IR!=0`送到C以保留`FAULT_IR`，不能统一改成V=0。
8. 给CLI提供`--transport replay`和可选`--transport pynq`。默认使用回放/只读模式；没有用户明确授权不得打开COM口或写运动帧。异常返回非零，日志打印输入文件、schema、契约ID和首个失败事件。

### 开源参考

只使用智谱已在`07_开源资源借鉴与优化分析报告.md`、`09_编码器与正交解码器选型报告.md`以及`9.17夜间任务队列/01_开源参考与复用要求.md`列出的候选。实际阅读AMDC-Firmware的数据交换/测试组织和本项目已固定的alexforencich `axil_reg_if`接口，再决定是仅参考还是复用；不要再泛搜一批新框架。若直接复制代码，固定commit、保留原许可和文件头，并更新`OPEN_SOURCE_USAGE.md`；仅借鉴结构就写清本项目重写内容。不得把AMDC的电机控制策略当作本车安全策略。

### 自修复

执行共同要求中的自修复闭环。失败时保存最小JSONL片段、epoch前后值、原始寄存器、主机调度时间、实际协议字节、C状态和退出码。先判断是生成寄存器表、transport、快照算法、时基换算、UART适配、测试夹具还是真实C违反契约，再做最小修复。不得通过改变A测试调用顺序、缩短100ms发送周期、取消串口串行占用或提前PREL来通过。修复后依次重跑该反例、17项链路单测、15项夜间A闭环和完整`run_acceptance.ps1 -Synthesis`。禁止吞异常、用旧快照继续运动、放宽年龄阈值或用Python状态机替代真实C。

### 验收与交付

- 单测覆盖版本错误、epoch不动/变化、序号与32位回绕、有符号速度、年龄等于阈值、JSONL损坏和故障保持STOP。
- 回放至少包含一次从正常到超龄/失联再到显式安全恢复的完整时间线，并核对真实C输出。
- PYNQ包/硬件缺失时，MMIO适配只做导入隔离与fake transport测试，状态写PARTIAL，不宣称板上通过。
- 写`pynq_fpga/nightly/night_20260918_D.md`，追加`self_repair_log.md`并更新`status.md`。列出命令、退出码、日志、回放文件schema、修改文件、未测硬件和夜间E可依赖的接口。

达到以上验收后写D交接并做一次A—D独立复审；随后按后台总任务继续任务7、8，不等待用户再次发送提示词。不要扩展网页、数据库、PID或自动驾驶。

## PYNQ-Z2本地引脚资料（编码前必读）

项目根目录新增 `pynq-z2资料/`，涉及外部端口、XDC、PS配置、UART、Pmod、时钟/复位或视频接口的代码修改前，必须交叉核对：

- `pynq-z2资料/引脚约束文件/pynq-z2_v1.0.xdc`
- `pynq-z2资料/原理图/PYNQ-Z2_PA_v3.pdf`
- `pynq-z2资料/原理图/TUL_PYNQ Schematic_R12.pdf`
- `pynq-z2资料/board_files/pynq-z2/A.0/` 下的 `board.xml`、`part0_pins.xml`、`preset.xml`

先确认实物板卡版本与资料适配性，区分连接器针脚编号、FPGA封装管脚和PS MIO/PL IO；记录文件路径、PDF页码/图号或XDC/XML行号。核对bank供电、IOSTANDARD、输入输出方向、有效电平、上拉与外部电平转换。不得把连接器针号当作PACKAGE_PIN，不得直接套用其他开发板、旧教程或开源工程管脚。

本地资料作为首要核对入口，但“文件存在”不等于引脚已核实。资料之间或既有线束分配存在冲突时，记录差异并保留未核实状态；不要猜值、静默换针或取消release门禁。只启用实际使用端口的XDC约束；board_files通过工程级仓库路径引用，先验证Vivado 2026.1兼容性，不覆盖全局安装。

纯算法和仿真任务不必引入物理管脚，但不能臆造板级参数；在交接中注明本次参考位置或“不涉及物理引脚”。实验指导书用于流程学习，其中EES-A7资料不是PYNQ-Z2引脚依据。原始资料保留原位，代码、工程与验证产物仍写入 `pynq_fpga/`。
