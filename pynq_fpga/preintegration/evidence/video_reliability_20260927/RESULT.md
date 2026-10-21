# 视频路径 warning 修复结果

日期：2026-09-27。工具：Vivado 2026.1。范围：视频读取 DDR 路径的实现警告及首次 SD 启动资料核对。

## 改动与原因

`create_integrated_candidate.tcl` 将 `video_hp0_ic` 从旧版 AXI Interconnect 换为 AMD SmartConnect 1.0，保持一进一出、单时钟、64-bit DDR 读通路。VDMA、SmartConnect 和 PS HP0 仍使用同一 100 MHz FCLK0；VDMA 与 SmartConnect 共用 `rst_100m/peripheral_aresetn`。

旧网表的 `REQP-1839` 指向 AXI4→AXI3 burst-split FIFO 的异步复位寄存器对 VDMA BRAM 写控制的驱动；`PDCN-1569` 也位于这段 FIFO 的 `user_valid` LUT。替换的是这一段供应商 IP 连接，没有修改供应商 HDL，也没有更改 DRC 严重性或添加豁免。

原工程及 20260919 测试包保留。新版工程：
`pynq_fpga/fpga/build/task7_8_video_reliability_20260927/task7_8_integrated.xpr`。

## 构建后证据

| 检查 | 旧版 | 新版 |
|---|---:|---:|
| REQP-1839 RAM 异步控制 warning | 8 | 0 |
| PDCN-1569 LUT 表达式 warning | 1 | 0 |
| RTSTAT-10 无负载网络 warning | 1 | 0 |
| DRC warning 总数 | 27 | 17 |
| DRC advisory | 1 | 1 |
| WNS / WHS | +0.383 / +0.039 ns | +0.081 / +0.020 ns |

新版建立/保持/脉宽失败端点均为 0。三个 bus-skew 检查通过，裕量分别为 8.643、8.808、9.076 ns。原工程不是本次重新构建的对象，旧版值取自其现存报告。

验证：21 项 preintegration 单元/契约测试通过；`tb_car_board_video_wrapper` 仿真 18 项检查通过（日志 `fpga/build/sim_tb_car_board_video_wrapper/20260927_215037_366/sim_run.log`）；新 HWH 的地址、端口、时钟与复位检查通过。新增审计对旧 DRC、旧 interconnect、错误时钟、错误复位与负 bus skew 均会拒绝；`negative_checks.json` 记录其中四个自动反例，旧 interconnect 另已检查。

打包入口新增审计，出现目标可靠性警告时中止打包，不依靠 warning 数量变少判定成功。`audit.json` 为新布线结果证据，测试包内还有对应的 `video_reliability.json`。

## 保留项及结论边界

- 17 条 DRC warning 全部是 DSP 输入/输出流水线建议（DPIP-1 / DPOP-1 / DPOP-2）。
- REQP-181 是 VDMA 供应商 XPM FIFO 的 WRITE_FIRST 条件性提示，仍保留。所用 `xpm_fifo_sync` 包含满/空及复位忙保护：本机 `data/ip/xilinx/axi_datamover_v5_1/hdl/axi_datamover_v5_1_rfs.vhd` 第 1449 行附近实例化该 FIFO；`data/ip/xpm/xpm_fifo/hdl/xpm_fifo.sv` 第 481 行附近保留读写保护逻辑。没有为消除提示而直接修改 RAM 模式。此项不等于实测已发生地址碰撞，也不构成全场景无碰撞的实板证明。
- GP 控制互连的可选端口、ARPROT/AWPROT 位宽警告未纳入本次修改。
- 创建工程时仍有原板卡 preset 的负 DDR DQS-to-clock 参数提示（PSU-1 至 PSU-4）。未擅改板级 DDR 参数。本项目仍用官方 PYNQ 镜像初始化 PS/DDR，不将本工程导出的初始化文件替换官方启动文件。不能把“布线 DRC 无 Error”扩展成所有 IP 创建消息都无 Critical Warning。
- 本次没有重写 SD 卡，没有加载真实板卡，也没有验证 HDMI 画面、相机性能或 30 分钟稳定性。产物仍为 LAB_ONLY_NO_MOTOR_NON_RELEASE。

## 交付与重建

新版测试包：`pynq_fpga/lab/task7_8_lab_only_20260927_video_fix.zip`。
完整重建并打包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/rebuild_video_reliability.ps1
```

本次实际分开执行了同一 Tcl 构建入口和打包脚本；包装仿真已单独通过，所以打包时使用 `-SkipRegression` 避免重复运行。
首次拿到板子的流程见 `pynq_fpga/preintegration/FIRST_BOOT_PYNQ_Z2.md`。

## 外部依据

- AMD SmartConnect 约束与复位要求：https://docs.amd.com/r/en-US/pg247-smartconnect/AXI-SmartConnect-Core-Limitations
- 官方 PYNQ-Z2 v3.1.1 镜像入口：https://www.pynq.io/boards.html
- 官方 Windows 写卡说明：https://pynq.readthedocs.io/en/v3.1/appendix/sdcard.html
- 官方 Z2 上电/跳线/网络说明：https://pynq.readthedocs.io/en/v3.1/getting_started/pynq_z2_setup.html
