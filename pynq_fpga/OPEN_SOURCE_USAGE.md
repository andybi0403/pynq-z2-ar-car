# 开源参考与复用登记（OPEN_SOURCE_USAGE）

## 2026-10-01 中央前方描边

先研究 [erendn/sobel-pipeline-fpga](https://github.com/erendn/sobel-pipeline-fpga)，固定提交 `c765b9d058ce489f9b262e9c5e83a99599a91e4a`。实际阅读 `src/sobel_channel_filter.sv`、`sobel_operator.sv`、`sobel_pipeline.sv`、`ram_1r1w_sync.sv` 与 LICENSE。MIT，Copyright 2023 Eren Dogan；原样参考快照和许可保存在 `audit/front_overlay_20261001/references/`。算子文件另注明来自第三方网站，因此不复制代码，只借鉴两行缓存、3×3窗口和绝对梯度和的架构。

另阅读 [Microchip官方Sobel教程](https://github.com/MicrochipTech/fpga-hls-examples/blob/main/sobel_tutorial/trainingdoc.md) 对照算法与行缓存流水；没有引入其代码、字体或SmartHLS生成核。生产 `car_axis_front_overlay.v` 为本工程独立实现的同步RAM、AXI4-Stream握手、中央ROI、同帧历史状态、风险色和厘米标注。O、N、T、~ 四个8×8字形为本项目自制，未复制第三方字体。

本次验证包括生产RTL逐像素独立矩阵卷积对照、4096种距离换算、停顿/复位/连续帧、包装层过期重放及停顿跨越200ms的反例，证据见 `audit/front_overlay_20261001/`。没有声称运行上游测试。无LICENSE的 PYNQ-Z2_sobel_filter_HDMI 仍只作行为参考，源码及二进制不并入交付。

> 登记规则见 `9.17夜间任务队列/01_开源参考与复用要求.md`。每行含：智谱原报告章节、上游仓库/版本、实际阅读的文件、采用方式、修改点、验证。

| 本项目模块/文件 | 智谱原报告章节 | 上游仓库与固定版本 | 实际阅读的上游文件 | 许可证 | 采用方式 | 修改点 | 验证 | 未核实事项 |
|---|---|---|---|---|---|---|---|---|
| `fpga/rtl/` AXI-Lite 前端（`axil_reg_if.v`/`axil_reg_if_rd.v`/`axil_reg_if_wr.v`） | 07 第三部分C；09 第三部分 | alexforencich/verilog-axi，commit `516bd5dadc3365b7f9e225d2af8fe0b8d804fe53`（shallow clone 快照存 `third_party/verilog-axi/`） | `rtl/axil_reg_if.v`（全文）、`rtl/axil_reg_if_wr.v`（握手/超时逻辑）、`rtl/axil_reg_if_rd.v`（rvalid/超时逻辑）、`tb/axil_reg_if/`（上游测试存在） | MIT（文件头版权声明） | **直接复用＋外围适配**：上游文件原样编译，本项目在 `car_axil_regs.v` 中实例化并实现 reg_wr/reg_rd 后端译码 | 无修改（原样引用）；本项目适配点仅限实例化参数与后端 | 本夜 XSim 100 项检查含其 AW/W 错开、WSTRB、背压、复位场景全部通过 | 上游 `tb/axil_reg_if/` 的 cocotb 测试未运行（本机无 cocotb，已记录） |
| `fpga/rtl/car_snapshot.v` 原子快照握手 | 09 第三、四部分 | Severson-Group/AMDC-Firmware，commit `5cf9769d33cc821fd55b4268ab80e285e3d4a607`（sparse 快照存 `third_party/AMDC-Firmware/`，仅 ip_repo+targets） | `ip_repo/amdc_encoder_1.0/src/encoder.v`（全文，重点 L246-273 trigger/done）、`hdl/amdc_encoder_v1_0_S00_AXI.v`（寄存器模板结构） | BSD-3-Clause（仓库 LICENSE） | **参考结构独立实现**：借鉴 trigger→同拍锁存→done 状态机的握手语义；位宽、序号、错误计数、seq_visible 同拍修正均为本项目需求重写 | 无上游代码复制；done 复位后=1 的防挂死约定保留 | 本夜 XSim 原子性 20 次交错竞争测试通过（修复 seq 同拍缺陷后） | AMDC 完整板级工程/软件环境未采用（与 PYNQ-Z2 不匹配） |
| `fpga/rtl/car_time_counter.v` | —（常规自由计数器，无上游） | — | — | 本项目原创 | 独立实现 | — | 回绕测试（短位宽实例递增越过 0xFF） | — |
| `fpga/rtl/car_axil_regs.v` 寄存器译码/ID_VERSION/SCRATCH | 09（AMDC S00_AXI 的地址映射结构仅作对照，未复制其地址表） | 同上 AMDC | 同上 S00_AXI（核实其用户寄存器从 0x00 起的布局思想） | — | 独立实现（地址映射见 `nightly/interface_contract.md` §8） | — | XSim 读写/WSTRB/非法地址测试 | — |
| `preintegration/vivado/create_framework.tcl`、`create_integrated_candidate.tcl`、`write_lab_only_bitstream.tcl`、`host/board_runtime.py`、任务8视频拓扑 | 07 视频链路建议；任务7/8预集成与生产核集成 | Xilinx/PYNQ，commit `e054c09c52db3244ef35c8ae08a2e62c1e4955fd`（sparse 快照存 `third_party/PYNQ/`） | `boards/Pynq-Z2/base/base.tcl`、`boards/ip/axi_dynclk_v1_0/`、`boards/ip/rgb2dvi_v1_2/`、`boards/ip/if/`、`pynq/lib/video/dma.py`、`dvi.py`、`LICENSE` | BSD-3-Clause | **直接复用IP＋调用驱动＋本项目适配**：固定快照中的`axi_dynclk`、`rgb2dvi`和TMDS接口随工程编译；板端脚本调用PYNQ AxiVDMA与`_display`，未复制官方Block Design二进制或旧bit/hwh | 按Vivado 2026.1和本地board preset重写Tcl；增加32→24位适配、生产感知核/OSD、MM2S/HPDN中断和UART1 EMIO。旧Base把HPDN作输出，与本地原理图第6页Q8开漏反相检测冲突，故本项目按原理图改为主动低输入 | Python/RTL/HWH/工程重建/综合/实现门禁；集成工程fully routed，WNS +0.079ns、WHS +0.027ns；另生成明确禁运动且非发布的LAB_ONLY bit/hwh | LAB_ONLY载荷已生成但发布bitstream仍未生成；PYNQ驱动、C270、HPDN与物理HDMI未实板验证 |
| 任务8 USB摄像头到HDMI用例对照 | 07 摄像头/视频推荐；任务8预集成 | aclich/PYNQ-Z2_sobel_filter_HDMI，commit `71a4409d76470fac7daed6552b9b3188ffe69d8f`（快照存 `third_party/PYNQ-Z2_sobel_filter_HDMI/`） | `README.md`、`USB to HDMI Sobel video streaming.ipynb`、`HW_rebuild/`目录结构 | **仓库未见LICENSE** | **仅作行为与目录参考**；没有复制源码、notebook单元、bit或hwh | 本项目自行实现UVC探测、视频契约、AXIS适配器和可复现Vivado Tcl | 摄像头枚举/能力解析测试、3秒只读烟测、RTL仿真和综合通过 | 许可不明，禁止把该仓库代码或产物并入交付 |
| `car_axis_osd.v`字符寻址与字形ROM组织 | 07 第三部分B | projf/projf-explore，commit `dd212c2e5e0e0d8bdcf93ba077630dbfd49ae708`（本地快照） | `lib/graphics/draw_char.sv`、`get_glyph_line.sv`、根`LICENSE`及字体文件头 | RTL为MIT；上游Unifont另有OFL/GPL例外 | **参考结构独立实现**：参考字符槽、行地址和MSB像素约定；没有复制其状态机或字体 | 本项目改为逐输入像素的AXI4-Stream合成、SOF状态提交、背压保持；16个8x8字形为本项目自制，单一`.mem`源 | `tb_car_osd_text` 114695项；7帧各8192像素逐点一致；640×480共307200像素一致；基础OSD 1326项 | Derek-X-Wang与verilog-axis本地快照未取得，本次未采用；Project F字体未复制 |

## 不采用与原因（承接智谱报告候选的闭环记录）

| 候选 | 原报告位置 | 结论与原因 |
|---|---|---|
| OmarAlchikha 相关仓库 | 09 第三部分 | 原报告无精确 URL；本夜未获取到具体仓库源码，按 01 要求"不凭作者名采用"，标注**未核实、待确认**。其"参数化滤波+err 脉冲"思想在 car_snapshot/car_snapshot 后续任务中以自身参数化方式实现 |
| PYNQ_Composable_Pipeline | 07 第一、三部分A | 官方仓库的工具链基线为Vivado/Vitis 2020.2；仅作为可组合视频流水架构参考，未复制或接入当前Vivado 2026.1工程 |
| fpga4fun QuadratureDecoder | 07 第三部分C | 教程无正式许可；XOR 式无毛刺防护，09 已定 FSM 路线（任务4采用） |
| 其余（Derek-X-Wang/verilog-axis/2cc2ic） | 对应任务 6/7 | 本地未取得Derek-X-Wang与verilog-axis固定快照，本次OSD没有直接复用；2cc2ic检测不在范围 |

## 证据位置

- 上游快照：`pynq_fpga/third_party/verilog-axi/`（commit 516bd5d）、`pynq_fpga/third_party/AMDC-Firmware/`（commit 5cf9769d，sparse：ip_repo + targets）
- 任务7/8上游快照：`pynq_fpga/third_party/PYNQ/`（commit e054c09，BSD-3-Clause）、`pynq_fpga/third_party/PYNQ-Z2_sobel_filter_HDMI/`（commit 71a4409，无LICENSE，仅参考）
- 本夜仿真日志：`pynq_fpga/fpga/build/sim_task2/sim_run.log`（100 checks PASSED）
- 许可证正文：verilog-axi 各 `.v` 文件头 MIT 声明（随快照保留）；AMDC 仓库 LICENSE（随快照保留）

## 2026-09-18验收增补（当前采用情况）

| 模块 | 智谱报告来源 | 固定上游 | 本地采用 | 本次验证 |
|---|---|---|---|---|
| car_qei / car_qei_top | 09第三、四部分 | AMDC 5cf9769d33cc821fd55b4268ab80e285e3d4a607，ip_repo/amdc_encoder_1.0/src/encoder.v及两份TB | 参考状态跃迁与trigger/done结构；项目独立同步/滤波/周期/影子适配，未搬入整板工程 | tb_car_qei 31检查；许可正文实际文件为third_party/AMDC-Firmware/LICENSE.md（BSD-3-Clause） |
| car_qei_velocity | 09测速接口需求 | AMDC模块未提供该速度算法实现 | 本项目PL周期法64拍除法、标定流水、符号饱和；无新增第三方代码 | tb_car_velocity 114检查、模块综合；不是AMDC上游测试结果 |
| car_ultrasonic | 07第三部分D | yunkai1841/HC-SR04-FPGA f4df022d27349fbf1dd71fb0aa99834365dfe0a9，sonic.v/sonic_test.v | 结构参考，补同步/超时/有效期接口；CC0原文在third_party/HC-SR04-FPGA/LICENSE | tb_car_sensors 41检查；未声称上游TB已运行 |
| AXI-Lite前端 | 07第三部分C/09第三部分 | verilog-axi 516bd5dadc3365b7f9e225d2af8fe0b8d804fe53 | 原样引用3个axil_reg_if*.v，MIT文件头保留 | 已修本地posedge BFM及后端WSTRB，101检查；原cocotb未运行 |

本次以已有固定本地快照核验，不重新联网核实最新仓库状态。历史表中的100项/任务2范围为当时记录，以本增补为当前范围。上游TB存在不等于当前版本接口匹配或已通过；不把本项目重写TB当上游测试。


## 2026-10-07 中文 OSD 字模

Noto Sans SC 固定 16×16 单色子集，由本机 NotoSansSC-VF.ttf 生成。原字体 SHA256、字符表与来源见 fpga/rtl/font_16x16_hud.json。字模遵循 SIL OFL 1.1，许可证在 fpga/rtl/font_16x16_hud_OFL.txt，并随部署包保留，字体许可独立于代码许可。
