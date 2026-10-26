# 任务2结果：接口契约与可运行仿真底座

> 历史记录：9月18日复审已修CTRL WSTRB与BFM，并重跑101项通过；最新以acceptance_20260918/任务1-4验收与修改报告.md为准。本文件保留当晚原始记录。

> 日期：2026-09-18 凌晨。状态：**PASS**（100/100 检查通过，见"验证记录"）。

## 一、只读盘点结论

1. **任务1修复核实**：`stm32预备程序/pc/pynq_link.py` 的真实样本年龄与驾驶请求租约**已修复且在位**——`SAMPLE_MAX_AGE=0.20`/`CMD_MAX_AGE=0.50` 独立常量、`_cmd_ms`/`_sample_ms` 分离、`suppressed` 撤销态、`release_request()` 重新解锁流程、接收字节缓存 `_rxbuf`；`test_pynq_link.py` 9/9 通过（本夜实测重跑）。任务5可复用的 API：`CarLink(port, proto='pynq', ser=可注入串口)`、`drive(left,right,valid,mm,ir,sample_ts)`、`stop_request()`、`release_request()`、`.state`、`.dropped_tx`。
2. **工具链**：`C:\AMDDesignTools\2026.1\Vivado\bin\` 下 xvlog/xelab/xsim 可用（2026.1）。git 2.54 可用。cocotb/iverilog 未安装（按约束不新装，TB 采用 SystemVerilog 自检式）。
3. **pynq_fpga 起始状态**：仅 README.md，无既有 PL 工程，本任务新建 `fpga/rtl|tb|scripts`、`third_party/`、`nightly/`。

## 二、上游源码核实（对应 01 要求）

| 上游 | 核实结论（基于实际源码） |
|---|---|
| AMDC-Firmware `ip_repo/amdc_encoder_1.0/src/encoder.v` | **trigger/done 机制真实存在**（L246-273）：trigger 一拍锁存 counter/position 到 `*_synced`，done 在 trigger 拍清 0、锁存完成置 1，复位后 done=1 防上层挂死。本夜 car_snapshot 采纳该握手语义。注意：AMDC 的快照**不含**序号/有效性/错误计数，也不解决 trigger 与数据更新同拍的 seq 竞争（本夜 DEF-2-06 即此类缺陷）——这些是本项目补充 |
| verilog-axi `rtl/axil_reg_if.v + _rd + _wr` | 直接复用（MIT）。AW/W 独立寄存天然支持任意顺序到达（`assign awready=!awvalid_reg` + `if(!awvalid_reg) 锁存输入`）；`reg_wr_en_next = awvalid_next&&wvalid_next&&!bvalid_next` 的单拍完成脉冲语义、TIMEOUT=4 防挂死、resp 固定 OK（无 SLVERR）均已从源码核实并在契约记录 |
| 上游测试 | `tb/axil_reg_if/` cocotb 测试存在但本机无 cocotb 未运行；以本夜自检 TB 的 100 项检查替代覆盖（含 AW/W 错开、WSTRB、背压、复位场景） |

## 三、交付物

| 文件 | 内容 |
|---|---|
| `nightly/interface_contract.md` | 统一接口契约 v0.1：时钟/复位（同步高有效）、tick=10ns、64位回绕、单位转换（距离mm/速度mm-s/PWM/红外低有效→1=障碍）、样本 valid/age/seq 语义、QEI 接口占位（含 B-06 修正）、风险信号、**视频 SOF≠曝光时刻**、AXI4-Lite 寄存器映射 v0.1（13 个寄存器含 RW/RO/复位值/WSTRB/非法地址行为） |
| `fpga/rtl/car_time_counter.v` | 参数化自由计数器（WIDTH=64 生产/短位宽仿真） |
| `fpga/rtl/car_snapshot.v` | 原子快照：live_data/valid/sample_ts/seq 四字段同拍锁存、trigger/done 握手（AMDC 语义）、16 位饱和错误计数、seq_visible 同拍修正 |
| `fpga/rtl/car_axil_regs.v` | 顶层：axil_reg_if（复用）+ 寄存器译码 + 时间基准 + 快照实例；CTRL 写触发脉冲、TS 原子锁存对、SCRATCH RW |
| `fpga/third_party/` | verilog-axi（516bd5d）与 AMDC-Firmware（5cf9769d，sparse）快照 |
| `fpga/tb/tb_car_axil_regs.sv` | 自检 TB：T1 复位默认值、T2 时间戳锁存递增、T3 WSTRB 三种部分写、T4 AW/W 三种错开（AW先/W先/同拍）、T5 B/R 背压、T6 非法地址写忽略、T7 快照原子性 20 次随机交错（固定种子 $random 默认）、T8 复位吞事务+复位后功能、T9 短位宽回绕 |
| `fpga/scripts/run_sim.ps1` | XSim 入口：xvlog→xelab→xsim→日志聚合→按 console 断言判定退出码（0=PASS/1=断言失败/2=环境/3=无结论）；独立构建目录 `fpga/build/sim_task2/` |
| `OPEN_SOURCE_USAGE.md` | 上游采用登记（含不采用与原因） |

## 四、验证记录（实际命令与结果）

```
powershell -ExecutionPolicy Bypass -File fpga\scripts\run_sim.ps1
→ PASS: task2 simulation (100 checks)
日志：fpga/build/sim_task2/sim_run.log（含 xvlog/xelab/xsim 各步输出与全部断言行）
```

- xvlog：6 个 RTL/TB 文件编译 0 error；xelab：展开成功；xsim：200µs 仿真完成。
- 断言统计：**100 checks / 0 errors**（T1×5、T2×3、T3×3、T4×3、T5×2、T6×1、T7×60、T8×2、T9×1 等）。
- 本夜自修复 8 个缺陷（DEF-2-01…08），全部关闭，见 `self_repair_log.md`。

## 五、接口变化与后续任务依赖

- **任务3/4 必须遵守** `interface_contract.md`：传感器数据以 live 侧四字段+live_update 脉冲接入 car_snapshot；地址空间新增寄存器**只能追加**（当前用到 0x000-0x02C 与 0x100 起），版本号在 ID_VERSION 递增。
- **任务5** 可复用 pynq_link.py 的 API（盘点第一节）；其风险机的速度输入接口按契约 §5 修正后的 QEI 接口（双边沿时间戳或 Δ位置/Δ时间）。
- **不能依赖**：PYNQ 官方视频 Overlay 兼容性（未验证）；编码器实物 PPR（待核验）；PowerShell 脚本在无 Vivado 2026.1 的机器上运行（路径硬编码，可用 -WorkDir 外的参数化扩展）。

## 六、仍需人工确认/待实物

1. 契约 §5 的 QEI 速度接口形态（双边沿时间戳 vs Δ位置/Δ时间）任务4落地时二选一。
2. 第二项 PL 传感器处理的深度（审查 □16 弱覆盖项）。
3. 生产参数（100MHz、样本 200ms）待板卡与编码器实物核验。

## 七、自修复缺陷汇总

- 关闭：DEF-2-01（PS 解析）、02（路径）、03（日志同名）、04（RTL 编译×2）、05（TB AXI 握手协议 ★）、06（快照 seq 同拍 ★）、07（T8 测试时序）、08（构建清理）。
- 未关闭：无。
