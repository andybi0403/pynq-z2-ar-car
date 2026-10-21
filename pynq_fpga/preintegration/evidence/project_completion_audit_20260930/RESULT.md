# 完整项目工程缺项核对（2026-09-30）

本轮只做需求对照、源码定位和补齐范围设计，没有修改 RTL、Python 运行代码、STM32 固件、寄存器表或已有上板包。以下是待用户审阅的补齐范围，不表示这些部分已经实现。

## 对照基准与已完成部分

需求以 [方向三报名方案](../../../../docs/01_竞赛与报名/06_东南大学PLD校赛报名撰写稿_小车方向三.md)、[主架构 v0.6](../../../nightly/主架构_v0.6.md)、[接口契约](../../../nightly/interface_contract.md)为主；历史任务及交接用于说明演变，不能用旧文档中的未完成描述推翻新构建证据。AR 网页方案作为扩展需求单独标注。

当前已有：超声波、红外、双 QEI、PL 测速、统一时基/全局快照、动态风险核、流式 OSD、PS/DDR/VDMA/HDMI/UART 的集成工程、真实 STM32 对接固件及协议适配、MMIO/记录回放、QEI SCALE 计算/写入工具、无电机分项验收脚本。

[9月30日构建记录](../drc_optimization_20260930/RESULT.md)证明默认生产参数下的完全布线候选 DRC 为 0 warning / 0 error / 0 critical warning，保留 1 条 VDMA advisory；WNS +0.745 ns、WHS +0.043 ns，6 项相关仿真 285 个检查通过。它证明当前候选可以构建，不证明下面的完整应用功能已经齐备，也不代表实板通过。本轮未重新运行全回归或操作硬件。

## 待补齐的 8 组工程

| 编号 | 工程部分 | 当前事实 | 补齐目标 | 顺序 |
|---|---|---|---|---|
| G1 | 共用 Overlay 的整机运行入口 | 视频、安全循环、标定分别启动；多个入口默认再次下载 bit | 一次加载、一个 MMIO 所有者、统一配置与退出；视频和控制独立调度；联合运行入口 | 第一批 |
| G2 | 驾驶意图与风险执行闭环 | `set_command()` 已有，但板端循环没有调用；现有 safety-loop 始终为零速台架模式 | 驾驶意图写 `RISK_CMD`，按独立租约失效；风险停止/黄色限幅/显式恢复；复用生产 `CarLink` 和 STM32 安全逻辑 | 第一批 |
| G3 | 摄像头帧与传感器时间关联 | 已有 PL 时间戳和快照；视频接口只传帧字节，统计提交间隔 | 帧编号、PS 接收/提交时间、PL 时基关联、快照 epoch/seq；输出可回放关联记录和偏差统计 | 第二批 |
| G4 | 物理里程与标定配置闭环 | 已有位置计数、速度与 SCALE 计算；缺累计物理里程发布和统一标定配置 | PL 物理里程、正反向/回绕/重置处理；左右实测 SCALE、方向、过滤参数的配置文件与读回；风险构建参数有来源和版本 | 第二批 |
| G5 | 完整状态显示与上位机入口 | HDMI 有速度/距离数字和风险颜色；未接风险原因、里程和真实 STM32 状态；没有 PYNQ 联合状态界面 | 补里程/方向/风险原因显示、区分 PL STOP 与 STM32 LOCK；提供有线状态查看、参数配置、日志导出与演示入口 | 第二批 |
| G6 | 长时视频运行与异常收尾 | 现有 FFmpeg 整帧读可能阻塞；stderr 管道未持续消费；独立视频 main 异常路径未统一 stop | 有界读帧/超时、错误日志消费、DMA/HDMI/进程回收；摄像头失联明确标失效；视频背压不阻塞控制 | 第一批 |
| G7 | 联合验收、故障证据及发布核验 | 分项验收和旧门禁存在；缺同一会话的联合压力测试与完整实物证据汇总核验 | 自动故障场景、命令租约基线变化、视频并发/控制时延测试、30分钟联合运行工具；证据绑定包和配置、缺项继续阻塞 | 第三批 |
| G8 | 统一重建、部署和最新工程导航 | 9月30日包存在；默认打包路径仍为9月19日，重建脚本固定9月27日，多个 README 指旧工程 | 可指定/自动独立版本目录的一键回归→构建→打包；板端依赖检查、启动说明、最新导航、源码/脚本/bit/HWH 同版校验 | 第三批 |

### G1：共用运行会话是优先修复项

源码定位：

- [lab_acceptance.py:82](../../host/lab_acceptance.py#L82)：`_load_overlay()` 固定使用 `download=True`。
- [lab_acceptance.py:190](../../host/lab_acceptance.py#L190)：`qei-config` 重新加载后写入 SCALE。
- [lab_acceptance.py:92](../../host/lab_acceptance.py#L92)、[lab_acceptance.py:377](../../host/lab_acceptance.py#L377)：MMIO 和 safety-loop 再次重新加载。
- [board_runtime.py:72](../../host/board_runtime.py#L72)：视频默认重新加载 Overlay。
- [car_perception_top.v](../../../fpga/rtl/car_perception_top.v)：复位时 QEI SCALE、命令有效位和时基归零。

因此按现有 CLI 先执行 qei-config，再执行 mmio/safety-loop，会触发重新配置，刚写好的 SCALE 无法按这个流程保留。同时启动独立视频命令也会干扰已有控制会话。这是源码流程中的连接缺陷，尚未在实板复现。

拟复用 `Task78BoardRuntime` 和 `PerceptionClient`，补会话管理和共享运行入口。附着到已经加载的 Overlay 时须核验同一 bit/HWH/契约，不能仅设置 no-download 就假定板上内容正确；一个进程负责全局快照与时基锁存，显示和日志消费其发布的数据。

验收：模拟 Overlay 加载计数证明同一会话只加载一次；标定后做 MMIO/视频/安全检查不丢配置；退出、视频异常和重启不重放旧运动意图。

### G2：补连接逻辑，保留既有安全规则

源码定位：

- [perception_client.py:258](../../../host/perception_client.py#L258)：`set_command()` 写命令方向/有效位接口已经存在。
- 板端 `host/` 与 `preintegration/host/` 的调用检索未发现运行循环调用这个接口。
- [lab_acceptance.py:377](../../host/lab_acceptance.py#L377)：safety-loop 仅 `update_command(0,0)`，不写 PL 的 `RISK_CMD`；README 明确 command-invalid 为预期基线。
- [car_risk_core.v](../../../fpga/rtl/car_risk_core.v)：已有 GREEN/YELLOW/RED/FAULT 输出；当前 host 决策只有许可/停止，尚无黄色风险到驱动限幅的完整应用路径。

拟补一个板端控制协调层，复用权威 `stm32预备程序/pc/pynq_link.py`，不另写第二套 STM32 安全状态机。区分上游驾驶意图年龄、PL 样本年龄和 UART 心跳；采样/显示更新不能自动续旧驾驶请求。明确前进、后退、转向在 `command_forward` 中的映射及限制。

STOP 后必须维持有效零速安全条件至少300ms，再接受显式释放；释放后的新意图才可恢复。黄色限幅只能降低请求，红色/FAULT 撤销运动许可；实际 PWM 到物理速度关系仍需标定，不能声称构成速度 PID。

当前 LAB_ONLY 包仍禁止 PREL/非零输出。本轮后续可在 fake transport、真实生产 C 闭环和无电机模式验证控制协调层；生成代码不代表已批准连接电机运行。

### G3：需要补时间关联，现有帧间隔不等于端到端延迟

源码定位：[frame_pipeline.py](../../host/frame_pipeline.py)、[board_runtime.py:171](../../host/board_runtime.py#L171)、[lab_acceptance.py:554](../../host/lab_acceptance.py#L554)、[perception_replay.py](../../../host/perception_replay.py)。

现有摄像头循环在提交帧后调用 `metrics.observe(time.monotonic_ns())`，可以测提交节奏；没有逐帧 PL 时基/快照关联，也不能据此知道摄像头曝光或屏幕显示时刻。FFmpeg fps 滤镜可能重复/丢弃输入帧，输出帧数不能直接当作摄像头原始采集帧数。

拟补帧元数据和关联日志，保留原始传感器值、样本时间、seq 和 epoch；用采样前后成对读取建立 PS/PL 时间关联及不确定度，不能把两个独立时钟直接相减。现阶段能自动记录接收→提交软件时延及样本偏差；曝光→屏幕延迟需要额外设备/画面实测。若要 HDMI 精确显示历史帧对应的传感器组，需要增加帧状态提交机制；实时风险控制继续使用最新数据，不能等待视频历史帧。

### G4：已有 QEI 工具不等于里程功能已完成

已有：[qei_calibration.py](../../../host/qei_calibration.py)、`QEI0/1_POS` 和 `QEI0/1_SCALE` 寄存器、`configure_qei_scales()` 与 qei-config 的写后读回。

缺项：双轮计数到物理里程的 PL 发布、累计路程与有符号位移的语义、回绕/重置/重新标定处理、校准数据文件与构建配置绑定。当前反应时间/减速度/安全余量是 `car_risk_core` 的编译参数，不能通过现有寄存器在线修改。

拟先保留编译期风险参数，增加可复现构建配置与参数合法性检查；实测数据不足时保留未标定状态。若补里程寄存器或显示状态写回，必须先更新唯一 `register_map.json`，同步生成 RTL/Python/文档，并升级契约及 HWH/包/回放验收，禁止偷偷在 v0.6 地址空间添加不兼容含义。

### G5：显示信息和上位机需要补齐

源码定位：[car_axis_osd.v](../../../fpga/rtl/car_axis_osd.v)、[car_board_video_wrapper.v:73](../../../fpga/rtl/car_board_video_wrapper.v#L73)。

现在数字字模主要显示速度和障碍距离，状态颜色已有。`state_locked` 接的是 `risk_stop`；文件头明确它是 PL 停车代理，不是 STM32 锁存实况。`risk_reasons` 和 `osd_frame_errors` 在包装层未提供给软件或显示。

拟补里程、方向、风险原因、显示链路诊断；若显示 STM32 LOCK，须使用新鲜 `$CAR` 回传并标示失联，不能沿用代理冒充实际状态。上位机基础交付采用有线网络的状态/参数/日志入口（Jupyter 或轻量页面均可），使用同一运行会话提供的数据。已有 Tkinter 控制台针对 STM32 USB 演示路径，不能直接当作 PYNQ 完整控制界面。

网页 MJPEG/无线一体化属于另一份 AR 扩展方案。可另批补 PS 软件叠加页面；当前 HDMI 的 PL OSD 不回写 DDR，网页取原帧时不得标作 PL 叠加帧。

### G6：视频异常与资源管理

源码定位：[frame_pipeline.py:198](../../host/frame_pipeline.py#L198)、[frame_pipeline.py:203](../../host/frame_pipeline.py#L203)、[board_runtime.py:140](../../host/board_runtime.py#L140)。

源码显示：FFmpeg stderr 被设为 PIPE 但未持续消费；整帧读取缺显式超时；独立 `board_runtime.main()` 正常末尾调用 stop，但相机提前 EOF/异常后会跳过该调用。`lab_acceptance.run_video()` 已有 finally，不能将这一缺陷扩大描述为所有视频入口均未清理。

拟补有界阻塞、持续错误日志处理、异常清理和失联状态。VDMA 继续复用 PYNQ 官方驱动的缓冲所有权机制；已有 `TripleBufferQueue` 是模型，不需要再强行叠一套独立 DMA 缓冲管理。相机/HDMI 失效是否撤销驾驶须形成明确策略，视频读取和背压必须与安全调度隔离。

验收：短帧、EOF、读帧无响应、大量stderr、HDMI/写帧异常、用户中止时不遗留子进程/缓冲区；视频阻塞时控制租约仍按期失效。静态代码判断不作为这些场景已经在板上发生的证据。

### G7：把验收脚本补成可以核验的联合证据

已有分项验收、接口检查、板级 manifest、A—E交接门禁；[check_ae_gate.py](../../host/check_ae_gate.py)主要检查历史交接中的 PASS 标记，[validate_board_manifest.py](../../../fpga/scripts/validate_board_manifest.py)检查字段和电气完成标记。它们不能单独证明所有实物数据来自当前包。

拟补联合验收入口与证据汇总器：绑定 bit/HWH、源码/运行脚本、寄存器契约、标定配置、会话起点和场景；核验真实采样覆盖、预期风险原因变化、持续收到的新 `$CAR`、控制停止时间、视频指标和实际联合时长。允许补人工照片/CSV测量入口，但不自动填硬件 PASS。

30分钟联合压力测试需要复用 G1 的一次加载会话，避免按旧说明同时开两个重新下载 Overlay 的命令。部分危险电气/机械场景仍须人工执行，软件只能收集和核验其证据。

### G8：让交付与当前代码一致

源码定位：[build_lab_only.ps1:9](../../build_lab_only.ps1#L9)、[rebuild_video_reliability.ps1](../../rebuild_video_reliability.ps1)、项目 README 和到板验收工作流。

默认输出路径仍为9月19日，视频重建包装脚本固定9月27日；9月30日干净DRC工程通过指定独立目录生成。历史目录可以保留，正式入口应明确当前候选并默认生成新目录，避免把新运行软件配到旧 bit。

拟补参数化重建、完整回归与包构建入口、依赖版本/板端检查、一次启动说明、最新入口导航以及源码/依赖/脚本的哈希记录。PYNQ Overlay 包与 SD 系统镜像继续分别说明。基础软件依赖部署可完成，板端系统兼容性仍要实测。

## 补齐顺序和完成标准

1. 第一批 G1/G2/G6：先解决共享会话、命令闭环和视频异常，相关软件反例及生产 C 闭环通过。
2. 第二批 G3/G4/G5：补时间关联、里程/配置、显示和上位机；发生接口改变后重跑完整生成器/协议/RTL/像素验证，并重新综合实现。
3. 第三批 G7/G8：补联合验收、证据核验、部署与最新交付；从独立目录完成完整回归、完全布线、时序/DRC/HWH/包一致性检查。

代码补齐完成标准是上述基础功能有实现、可复现测试和匹配候选包。实板完成标准另需 Overlay/MMIO、电气、QEI/轮径/制动标定、UART停止时延、HDMI色序、C270性能及30分钟联合运行的真实记录。当前这些不能由编程补成已通过。

可选扩展单独排期：无线AP/MJPEG一体控制、PL叠加帧回采、IMU融合/轨迹、车道/目标识别、PID。它们不作为本轮基础工程缺项；本轮继续沿用既有 PL 实时处理、PS管理、STM32执行架构。
