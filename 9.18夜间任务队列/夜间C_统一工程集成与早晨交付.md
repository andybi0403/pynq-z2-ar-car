# 夜间C_统一工程集成与早晨交付

> 迁移来源：9.17原任务7；2026-09-18重写，按最新验收基线执行。
> 2026-09-19 Codex接管夜间A后同步：总门禁已包含真实C DLL重建与A闭环。
> 2026-09-19起由Codex在B验收后连续执行，不再作为ZCode排队提示词。

## Codex后台执行任务书

Codex在夜间B完成并验收后连续执行夜间C，不重新执行历史任务3。先完整读取 `9.18夜间任务队列/00_今晚排队顺序与共同要求.md`、`9.18夜间任务队列/01_上次错误与防回退要求.md`、`pynq_fpga/nightly/主架构_v0.6.md`、`pynq_fpga/nightly/interface_contract.md`、生成的`pynq_fpga/nightly/register_map_v0.6.md`、`pynq_fpga/nightly/night_20260918_A.md`和Codex刚完成的`night_20260918_B.md`。v0.6与A冻结接口优先于旧队列和v0.5描述。

主架构已由Codex建立，任务C从集成验收继续，不得重新设计：`car_perception_top.v`已有单时基、单AXI和全局快照；`register_map.json`已生成Verilog/Python/Markdown；`car_architecture_v0_6.xpr`已真实生成；主机版本/epoch客户端和板级manifest也已落盘。当前统一顶层100MHz OOC WNS为+2.367ns。你负责合并A/B增量、补系统回归、核查工程可重建，并准确交接。

先核查而非重建独立顶层。确认`car_perception_top`仍只实例化功能核，全系统仍只有一个64位计数器、一个AXI从机和一次全局快照；确认A/B没有复制地址译码。总门禁`run_acceptance.ps1`现会先重建对接版真实C DLL，再运行17项链路单测、15项A跨层闭环及其余回归；不得删除、跳过或改回使用旧DLL。用`create_architecture_project.tcl`从零重建并检查xpr；未接PS/DDR/VDMA/HDMI就继续标PL候选工程。最后生成MORNING_HANDOFF_20260919.md，不覆盖历史交接。

开源参考要求：先读 `9.17夜间任务队列/01_开源参考与复用要求.md`，以官方Xilinx/PYNQ的PYNQ-Z2板级约束和base工程为集成参考，PYNQ_Composable_Pipeline仅参考确实需要的视频接口结构。核实选定版本和本机工具兼容性，不整包迁移旧工程或复制旧bit/hwh。检查前序任务的 `pynq_fpga/OPEN_SOURCE_USAGE.md` 与实际文件一致，并在早晨报告汇总复用模块、适配内容、许可证和未验证项。

自修复要求：必须执行共同约束中的“自修复闭环”。本任务有责任修复原任务2—7新增代码中的可复现集成缺陷；不要只汇总失败清单。按最小反例定位、最小修改、模块回归、受影响链路回归的顺序推进；最终从干净构建输出目录运行一次可复现完整回归。旧PASS在接口变更后先标待重验，不得通过stub、SKIP或降低DRC等级凑总PASS。达到通过条件或证据充分的真实阻塞后交接，将自修复清单纳入早晨报告。

你现在接续FPGA原任务7，执行夜间C。工作目录是 `C:\Users\39909\Desktop\FPGA`。先读共同要求、v0.6主架构、历史任务1修改记录、`pynq_fpga/nightly/status.md`及原任务2—6和夜间A/B结果。

目标：把今晚真实完成的模块整理成可复现候选工程，做一次集成回归，准确交接，避免留下“各模块声称通过，接口却对不上”的工程。优先整合和修复本夜新增代码，不继续扩展功能。

按顺序完成：

1. 核对公共接口、单位、寄存器地址、快照机制、reset极性、时间戳起点／位宽、样本有效期及风险优先级。v0.6继续以完整32位样本时间与独立metadata为硬边界；禁止恢复`valid+31位时间`。修复本夜新增模块之间的机械接口差异；涉及既定安全策略和未批准架构决策则记录，不自行放宽规则。
2. 审计现有无AXI功能核和`car_perception_top`。地址分区由`register_map.json`固定；冲突只能在机器源中修复并重新生成，不能套三个AXI包装层。OSD保持清晰的视频输入输出边界。扩展端到端仿真时禁止用stub覆盖已经存在的真实核；若A/B模块失败，只能隔离故障并明确降级证据。
3. 保持当前一键回归入口，依次运行两版STM32测试、原任务1通信测试、对接版C DLL重建、A真实C闭环、公共AXI/快照、传感器、QEI、风险与OSD比对。不要另写一份精简总脚本。依赖工具缺失时报告SKIP及原因，安全关键SKIP不得转换为总PASS。任何失败返回非零退出码，保存完整日志。
4. 用本地Vivado对候选PL顶层做综合与基础约束检查；确认板卡目标器件资料后设置part。可行时做候选实现及时序报告，但不伪造PYNQ Base Overlay兼容性。读官方板卡XDC并逐脚映射外部端口，只约束实际存在端口，检查重复管脚、IOSTANDARD和电源／地误用；禁止为了消警告批量降级DRC。
5. 输出实际LUT/FF/BRAM/DSP、综合／实现阶段、时钟约束、WNS/TNS（有实际报告才填）、未约束路径与CDC待查项。综合通过不等于布局布线或板上稳定。
6. 核查新增第三方代码及资源许可，生成最小来源表；对未直接复用的参考资料写“仅参考”，不能捏造提交号或重许可。无需重写旧项目全部许可证体系。
7. 写板到货后的首轮验收步骤：电机断开或可靠悬空、先检查电平／供电、传感器独立测量、确认轮轴CPR、串口安全注入、最后再视频与低速整车。此处只编写步骤，不执行任何硬件操作。
8. 生成 `pynq_fpga/nightly/MORNING_HANDOFF_20260919.md`：第一屏只写已完成成果、P0遗留、如何重跑和早晨最该做的三件事；后附工单逐项证据与待人工确认项。同步更新 `pynq_fpga/nightly/status.md`，给出每个任务PASS/PARTIAL/BLOCKED。

9. 使用现有`create_architecture_project.tcl`从干净输出重建并打开`car_architecture_v0_6.xpr`，检查源文件解析、顶层和约束；若需修改脚本，只做可复现的最小修复。工程仍是PL候选，不得把它写成完整PYNQ Overlay。

10. 运行现有寄存器生成器`--check`，验证Verilog、Python和Markdown未漂移，并扩展缺失的负向测试；禁止建立第二份机器源。旧模块包装层可以保留回归，但README继续标为verification wrapper。
11. 全局快照一次锁存US、IR、QEI0、QEI1和风险输出，每组保留自己的sample_ts/seq/valid；全局epoch只表示同一次读取屏障，不得替代各自采样时间。测试同拍多生产者更新、未提交总线变化、time bit31和32位回绕。
12. 回归脚本采用“定向反例→受影响模块→全量→统一顶层OOC综合”的顺序；完整命令固定为`powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1 -Synthesis`。当前基线WNS：`car_risk_core` +2.644ns、`car_perception_top` +2.367ns、`car_axis_osd` +3.677ns。只有XDC、Block Design和外设接口齐全时才进入完整实现。

交付必须区分四层证据：代码存在、自动测试通过、综合／实现通过、实物验证通过。最后一层本夜不能凭仿真填“通过”。不要把测试种子数量、代码行数、token消耗当成项目进度。

不要因某一模块失败重启整个项目或重写已通过模块；保留失败反例和可复现命令。终止本任务启动的测试／构建进程后写交接，并立即继续夜间D。阶段报告只记录工程入口、回归结果、关键阻塞和交接文件路径，最终由Codex自己统一复审。

交接文件固定为 `pynq_fpga/nightly/night_20260918_C.md`。开始与结束都更新status.md；满足验收后立即继续夜间D，不等待用户再次发送提示词。

## PYNQ-Z2本地引脚资料（编码前必读）

项目根目录新增 `pynq-z2资料/`，涉及外部端口、XDC、PS配置、UART、Pmod、时钟/复位或视频接口的代码修改前，必须交叉核对：

- `pynq-z2资料/引脚约束文件/pynq-z2_v1.0.xdc`
- `pynq-z2资料/原理图/PYNQ-Z2_PA_v3.pdf`
- `pynq-z2资料/原理图/TUL_PYNQ Schematic_R12.pdf`
- `pynq-z2资料/board_files/pynq-z2/A.0/` 下的 `board.xml`、`part0_pins.xml`、`preset.xml`

先确认实物板卡版本与资料适配性，区分连接器针脚编号、FPGA封装管脚和PS MIO/PL IO；记录文件路径、PDF页码/图号或XDC/XML行号。核对bank供电、IOSTANDARD、输入输出方向、有效电平、上拉与外部电平转换。不得把连接器针号当作PACKAGE_PIN，不得直接套用其他开发板、旧教程或开源工程管脚。

本地资料作为首要核对入口，但“文件存在”不等于引脚已核实。资料之间或既有线束分配存在冲突时，记录差异并保留未核实状态；不要猜值、静默换针或取消release门禁。只启用实际使用端口的XDC约束；board_files通过工程级仓库路径引用，先验证Vivado 2026.1兼容性，不覆盖全局安装。

纯算法和仿真任务不必引入物理管脚，但不能臆造板级参数；在交接中注明本次参考位置或“不涉及物理引脚”。实验指导书用于流程学习，其中EES-A7资料不是PYNQ-Z2引脚依据。原始资料保留原位，代码、工程与验证产物仍写入 `pynq_fpga/`。
