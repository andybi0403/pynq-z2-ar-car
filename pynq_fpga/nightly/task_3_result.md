# 任务3结果：超声波与红外 PL 模块

> 历史记录：9月18日修订US快照、时间戳、4m范围、错误计数与39ms默认值，41项复验通过；以interface_contract.md和验收报告为准。以下是修订前原始记录。

> 日期：2026-09-18。状态：**PASS**（31/31 断言通过；任务2 回归 100/100 仍通过）。

## 一、上游核实（01 要求）

- **yunkai1841/HC-SR04-FPGA**（commit `f4df022`，快照在 `third_party/HC-SR04-FPGA/`）：实际阅读 `sonic.v`（仅 30 行：外部自由计数器 + trig 在 counter 1-50 拉高≈10µs + echo 沿锁存脉宽）、`sonic_test.v`（板级测试，非自检 TB）、`spec.md`（5MHz 时钟、WIDTH=30）、`LICENSE`（**CC0-1.0 确认**）。
- **采用方式：参考结构独立实现**。上游核心过于简陋（无同步器/无超时/无上电卡高防护/测量周期隐含在 WIDTH/无故障码），按 01 要求"缺失安全功能补齐"逐项补齐；未复制任何上游代码行。
- **红外**：上游仓库无红外模块（已确认）；car_ir 为按 08 接线方案硬件需求独立实现。

## 二、交付物

| 文件 | 内容 |
|---|---|
| `fpga/rtl/car_ultrasonic.v` | 单时钟测量状态机：两级同步（ASYNC_REG）、参数化 trig 宽度/测量周期/Echo 超时、**上电 echo 已高防护**（同步器复位值 0 + rise 检测 + saw_high）、无回波/卡高/零宽/超量程四类故障码（1/2/3）、enable=0 停止触发并发布无效、脉宽→mm 固定点换算（`ticks*7366720>>32`，48 位中间量无溢出，截断<1mm）、温度留接口（默认 20℃ 343m/s） |
| `fpga/rtl/car_ir.v` | 双路两级同步→低有效转"1=障碍"→**参数化稳定窗口滤波**（clk 数，复位 5000=50µs，非"三次采样"）→障碍位图+stable 标志+状态时间；只采集不锁存 |
| `fpga/rtl/car_sensors_top.v` | 集成：复用任务2 的 car_time_counter/car_snapshot/axil_reg_if；US/IR 样本挂快照 live 侧（US 批=[11:0]mm+[15:12]故障+[19:16]IR，IR 批同域）；契约 v0.2 寄存器（0x030-0x04C、0x110-0x118）；ID_VERSION=0xC425**0002** |
| `fpga/tb/tb_car_sensors.sv` | 独立期望值模型（整数公式 `ticks*343/200000`，不用 RTL 定点常数）+ 全场景 |
| 契约更新 | `interface_contract.md` v0.1→**v0.2**：新增 §8a 传感器语义（样本时间戳=Echo 下降沿拍/seq 仅真实测量递增/故障码定义/截断误差声明/IR 滤波窗口单位/断线待测）+ 11 个寄存器 |

## 三、测量周期自洽性（任务书要求2）

生产配置：**测量周期 100ms**（任务1 已验证的选择）+ 200ms 真实样本有效期。预算：
- Trig 10µs + 最大回波等待（量程 4m→23.3ms，超时窗 390ms 富余）+ PS 组帧调度 + UART 100ms 帧传输
- 最坏链路：测量完成→PS 读→$P 发出 ≤ 100ms 周期 + 少量调度 → 样本年龄最大 ≈100ms+ε < 200ms ✓
- 250ms 周期与 200ms 有效期**不可同时配置**（契约 §8a 已写明）；US_CFG_PERIOD 寄存器可配但软件不得写 ≥200ms。

## 四、验证记录（实际命令与结果）

```
powershell -ExecutionPolicy Bypass -File fpga\scripts\run_sim.ps1 -Top tb_car_sensors -TbFile tb_car_sensors.sv
→ PASS: tb_car_sensors simulation (31 checks)
powershell -ExecutionPolicy Bypass -File fpga\scripts\run_sim.ps1     （任务2 回归）
→ PASS: tb_car_axil_regs simulation (100 checks)
日志：fpga/build/sim_tb_car_sensors/sim_run.log、fpga/build/sim_tb_car_axil_regs/sim_run.log
```

断言覆盖（31 项）：T0 版本/复位配置×6；T1/T1b 已知距离（999mm/171mm，独立模型）；T3 短回波；T4 无回波超时（故障1，状态机不阻塞）；T5 卡高（故障2，含上电已高语义）；T6 连续测量 seq 递增+读/快照不更新样本时间；T7 测量中复位（配置恢复复位值+复测可用）；T8 生产周期 100ms<200ms 换算检查；T9 IR 极性/毛刺滤除/双侧/释放/时间戳×6；T10 快照同批；T11 模型常数。

## 五、自修复缺陷汇总（详见 self_repair_log.md）

- **真实 RTL 缺陷 3 个**：DEF-3-06（WAIT_F 无符号下溢一拍误判卡高）、DEF-3-08（rise 清 wait_cnt 致脉宽短 resp 段——移植上游自由计数器结构时引入）、DEF-3-09（seq 未接寄存器违背契约）。全部关闭并补回归。
- **环境/脚本**：DEF-3-01（wire 过程赋值）、02（us_samp_ts 多驱动）、03（rd2 未声明）、04（复制了任务2 缺陷版 write 任务——教训：跨任务 TB 复用必须用最终交接版）。
- **测试错误**：DEF-3-05/07（TB 时序与模型照抄被测公式）——已按"独立期望值"重写。
- 未关闭：无。

## 六、待实物核验 / 需人工

1. Echo 电平转换（SN74LVC245）后实际脉宽与理论一致性、模块盲区行为（RTL 不伪造物理盲区过滤）。
2. IR 断线偏置（RTL 不可证明，08 方案已列为硬件待测）。
3. 温度补偿接口默认关闭；是否启用由任务5 风险机决定（需拍板）。

## 七、后续任务依赖

- 任务4（QEI）：复用 car_sensors_top 的集成模式（axil_reg_if+live 侧+契约追加区 0x120 起）；**注意 DEF-3-08 教训——计数连续性**。
- 任务5（风险机）：消费 0x030/0x03C 样本（valid/fault/seq 语义见契约 §8a）；pynq_link 需按 0x034 的样本时间检查真实年龄。
- **不能依赖**：实物精度（声速/模块未测）；温度补偿（未实现，仅留参数）。
