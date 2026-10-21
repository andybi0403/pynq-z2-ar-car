# DSP 流水线优化与调试结果（2026-09-30）

PYNQ-Z2 完整工程已完成综合、布局、布线和 bitstream 生成。默认生产参数下，17 条 DRC warning 全部消除；没有修改规则严重级别或使用 waiver。

| 指标 | 2026-09-27 基线 | 本次最终构建 |
|---|---:|---:|
| DRC warning | 17 | 0 |
| DRC error / critical warning | 0 | 0 |
| DRC advisory | 1 | 1 |
| WNS | +0.081 ns | +0.745 ns |
| WHS | +0.020 ns | +0.043 ns |
| Setup / Hold 失败端点 | 0 / 0 | 0 / 0 |
| Slice LUT | 6706 | 6575 |
| Slice Register | 9914 | 9880 |
| DSP48E1 | 9 | 9 |

## 改动

- `car_qei_velocity.v`：加入标定操作数与乘积流水级；把 100 MHz 常数等价分解为 `390625 << 8`，使每个 16 位标定分量的乘法适合单个 DSP48E1；其他时钟参数保留精确计算的回退。相应延长配置稳定等待，64 拍除法保持原算法。
- `car_ultrasonic.v`：距离乘法增加两级寄存器及等待状态，发布使用已经完成的乘积；样本时间戳仍锁存于 Echo 下降沿。
- `car_risk_core.v`：为乘法和取整计算补充流水线，故障位、距离、命令状态、签名及时间戳同步传递。反应项根据 13 位速度上界收窄到 21 位，较大 REACTION_MS 参数保留 32 位。第二段乘法放入三拍小模块，并保留其层级边界，防止输入寄存器被吸收到前一个 DSP。流水线增加延迟，连续输入的吞吐与批次配对已经仿真验证。
- `tb_car_risk_core.sv`：保留原有功能检查，调整等待时间，并增加四组逐拍输入的结果/时间戳配对检查。
- 实现与 LAB_ONLY bitstream 脚本现在拒绝任何 Warning、Critical Warning 或 Error；Advisory 仍完整保留在报告中。

流水线映射依据 AMD [DSP Block Implementation](https://docs.amd.com/r/en-US/ug901-vivado-synthesis/DSP-Block-Implementation) 与 [KEEP_HIERARCHY](https://docs.amd.com/r/en-US/ug901-vivado-synthesis/KEEP_HIERARCHY)。独立综合确认第二段反应项乘法 AREG=1、MREG=1、PREG=1；最终完整布线报告确认全部 DSP 流水线 warning 消失。

## 验证证据

6 项相关仿真通过，共 285 个检查：

| 仿真 | 检查数 | 日志目录（fpga/build 下） |
|---|---:|---|
| tb_car_velocity | 124 | sim_tb_car_velocity/20260930_124229_154 |
| tb_car_qei | 31 | sim_tb_car_qei/20260930_124229_154 |
| tb_car_sensors | 43 | sim_tb_car_sensors/20260930_122943_084 |
| tb_car_risk_core | 36 | sim_tb_car_risk_core/20260930_155751_403 |
| tb_car_perception_arch | 33 | sim_tb_car_perception_arch/20260930_155958_345 |
| tb_car_board_video_wrapper | 18 | sim_tb_car_board_video_wrapper/20260930_160252_172 |

最终工程与报告位于 [task7_8_drc_clean_0930](../../../fpga/build/task7_8_drc_clean_0930/)。

- [完整布线 DRC](../../../fpga/build/task7_8_drc_clean_0930/drc_integrated_impl.rpt)
- [时序报告](../../../fpga/build/task7_8_drc_clean_0930/timing_integrated_impl.rpt)
- [资源报告](../../../fpga/build/task7_8_drc_clean_0930/utilization_integrated_impl.rpt)
- [生成与打包日志](../../../fpga/build/task7_8_drc_clean_0930/package.psout)

打包时再次运行板级封装仿真并通过。HWH 生产契约、SmartConnect/时钟/复位审计和包内契约通过；总线偏斜 slack 为 +8.353、+9.057、+8.896 ns。ZIP 内 bit/HWH 的长度与 SHA-256 与 manifest 一致，ZIP 内 DRC 只有 REQP-181 Advisory。

## 上板候选包

[task7_8_lab_only_20260930_drc_clean.zip](../../../lab/task7_8_lab_only_20260930_drc_clean.zip)

SHA-256：`ad1f261053f3170c72f14c441a0a1c3e15ddaa546792e1883c4fd8b30992d0c4`

源码哈希见 [source_hashes.json](source_hashes.json)。包分类为 `LAB_ONLY_NO_MOTOR_NON_RELEASE`，包含同名 `.bit` / `.hwh` 及测试脚本；它是 PYNQ overlay 测试包，不是整张 SD 卡系统镜像。本次验证覆盖仿真与 FPGA 构建，尚未进行实板加载和传感器/HDMI 实测。

剩余 REQP-181 位于 AMD VDMA 内部 FIFO，提示 WRITE_FIRST 模式下应避免同地址读写冲突。它的严重级别为 Advisory，未隐藏，也不代表已经发生数据损坏。
