# 自修复日志（self_repair_log）

> 按共同约束"自修复闭环"格式记录。每个缺陷一个编号，供 Codex 复审。

## DEF-2-01｜PowerShell 脚本无 BOM 的 UTF-8 中文注释导致解析失败

- 任务：2。首次失败：`run_sim.ps1` 首次执行，PowerShell ParserError "意外的标记 ')'"（脚本首个 param 前的中文注释行）。
- 复现命令：`powershell -ExecutionPolicy Bypass -File run_sim.ps1`
- 根因：Windows PowerShell 5.1 对无 BOM 的 UTF-8 脚本按 ANSI 解码，中文注释字节流破坏了词法结构。
- 修改：`fpga/scripts/run_sim.ps1` 注释与输出改为纯 ASCII。
- 修复前：ParserError 退出非 0；修复后：脚本正常进入工具调用流程。
- 回归：后续全部轮次均通过该脚本运行。状态：已关闭。

## DEF-2-02｜run_sim.ps1 工作目录定位错误

- 首次失败：`ERROR: missing source ...\fpga\third_party\verilog-axi\rtl\axil_reg_if.v`
- 根因：`$Root = Resolve-Path "$PSScriptRoot\.."` 解析到 `fpga/`，而 `third_party/` 在 `pynq_fpga/` 根。
- 修改：`$Root` 上溯两级到项目根。
- 修复前：缺源文件退出 2；修复后：源文件全部定位成功。回归：后续轮次。状态：已关闭。

## DEF-2-03｜PowerShell 重定向文件与工具默认日志同名

- 首次失败：xvlog CRITICAL WARNING "Failed to open handle xvlog.log"，退出 1（UTF-16 日志可见）。
- 根因：`*> xvlog.log` 使 PowerShell 持有该文件句柄，xvlog 自身要在工作目录创建同名日志。
- 修改：重定向改为按步骤命名的 `<step>.psout`。
- 修复前：xvlog 直接失败；修复后：xvlog 正常。状态：已关闭。

## DEF-2-04｜RTL 编译错误（一次提交两处）

- `car_axil_regs.v`：① `ts_latch` wire 声明位于使用点之后（``default_nettype none`` 下报 used before declaration）；② `reg_rd_data` 为 wire 却在 always@(*) 内过程赋值。
- 根因：一次性书写两个 always 块与组合声明的相对位置失误；①另有 ts_latch_done 双驱动（两个 always 赋同一 reg，合并修复时消除）。
- 修改：wire 声明前移合并到锁存块；读译码改为 `reg_rd_data_r` + `assign`；删除重复的旧 ts 锁存 always。
- 修复前：xvlog 6 个 ERROR；修复后：编译通过。状态：已关闭。

## DEF-2-05｜TB AXI 握手协议错误（多轮，最终正确写法）★关键缺陷

- 首次失败：T2 写事务后看门狗超时（TB 的 while(!awready) / while(!bvalid) 永挂），DUT 侧经事务监控证实写脉冲发生在错误拍、携带上一事务的 data/strb（T3 位置写 data=00000002/strb=1111，即 T2 残留）。
- 根因（两层）：
  1. TB 在 negedge 注入 valid、在**同一 cycle 判定 ready 后立即撤销**——RTL 在下一个 posedge 的采样沿读不到 valid，事务丢失；
  2. 握手完成检测用 posedge 判定（awready=0 的完成拍不退出，晚一拍退出时 TB 的 valid 仍为 1）——上游在完成拍把 awvalid_reg/wvalid_reg 清 0 后 **awready/wready 下一拍回 1，TB 仍保持的 valid 被采样为新事务**，重放上一事务的 addr/data/strb。B 通道同理（bready 恒 1 时 bvalid 只高一拍，先撤 valid 再等 bvalid 会永久错过）。
- 依据：alexforencich/verilog-axi `axil_reg_if_wr.v` L88-114（awready=!awvalid_reg；`if(!awvalid_reg) 锁存输入`）与 L108-114（完成由 reg_wr_en_reg&&ack 触发并清 valid_reg）——完成拍后 ready 回 1 是上游既定行为，master 必须在该拍之前撤 valid。
- 修改（`tb_car_axil_regs.sv` 最终形态）：valid 在 negedge 注入；第一 posedge 为采样沿；**完成检测统一在 negedge 判定**（negedge 读到的 ready 是完成后的状态），**同一 negedge 撤销 valid**；B/R 应答后等 bvalid/rvalid 回落排空通道；AW/W 通道以 fork 独立驱动支持双向错开与 W 先于 AW。
- 修复前：11 项断言失败（含全部错开/背压/非法写场景）；修复后：0 失败。
- 回归：100 项检查含 T4 三种错开时序、T5 背压、T6 非法地址、T8 复位，全部通过。状态：已关闭。
- 遗留：该握手模式已固化为本项目 BFM 惯例，任务 3-7 复用。

## DEF-2-06｜car_snapshot 原子快照 seq 同拍缺陷 ★真实 RTL 缺陷

- 首次失败：T7 原子性测试 3 次错位：data 高 16 位=seq+1（如 data=0028c0de / seq=0027）。
- 根因：`trigger` 与 `live_update` 同拍到达时，`snap_data` 锁存的是更新后的新批数据，而 `snap_seq <= seq_cnt` 锁存的是自增前的旧值——四字段跨批，违反契约 §9"四字段来自同一批"。
- 修改：新增 `seq_visible = live_update ? seq_cnt+1 : seq_cnt`，trigger 锁存时使用 `seq_visible`（与 live_data 的同拍语义一致）。
- 修复前：20 次交错中 3 次错位；修复后：0 次错位。
- 回归：T7 全部 20 次迭代 + seq 单调检查通过。状态：已关闭。
- 教训记录：该缺陷由"生产者与快照触发竞争"的随机交错测试暴露，确定性单点测试不可替代。

## DEF-2-07｜T8 复位测试预期与确定性时序

- 首次失败：T8 midreset 读回 55555555（事务实际在复位注入前一拍已完成）而非复位值。
- 根因：原测试在置 valid 后等 2 拍才拉 rst——写事务已在复位生效前正常完成，预期值错误（测试错误，非 RTL 错误；依据：axil_reg_if_wr 的同步复位优先级高于 en）。
- 修改：T8 改为确定性时序——先建立 rst，再在复位期间发起事务（采样沿上复位优先于 en，事务被吞），断言 SCRATCH 保持复位值、复位撤销后功能正常。
- 修复前：1 项失败；修复后：通过。状态：已关闭。

## DEF-2-08｜构建目录被占用导致清理失败

- 首次失败：`Remove-Item -Recurse -Force $WorkDir` IOException（外部解析进程占用 VCD）。
- 修改：清理失败时将旧目录改名让位（`_old_HHmmss`），不中断仿真。
- 状态：已关闭。


---

# 任务3 自修复记录

## DEF-3-01｜car_sensors_top 读译码赋值给 wire

- 首次失败：xvlog 10-1280 "procedural assignment to non-register rd_mux"。
- 根因：rd_mux 声明为 wire 却在 always@(*) 内赋值（与任务2 DEF-2-04 同类错误复发）。
- 修改：改 `reg rd_mux_r` + `assign`。
- 状态：已关闭。

## DEF-3-02｜us_samp_ts 多驱动

- 首次失败：xelab 10-9171 "mixed concurrent and procedural assignments on us_samp_ts"。
- 根因：car_ultrasonic 模块内对 samp_ts 的占位赋值与顶层锁存公共计数器的 always 冲突。
- 修改：模块完全移除 samp_ts 端口与赋值（时间戳由顶层唯一拥有）。
- 状态：已关闭。

## DEF-3-03｜TB rd2 未声明

- xvlog 10-2989。补声明。状态：已关闭。

## DEF-3-04｜任务3 TB 复制了任务2 的中间版 axil_write（握手缺陷复发）

- 首次失败：T0 后首个 axil_write 挂死（看门狗）；DUT 事务监控显示写脉冲/B 握手均正常发生，TB 未返回。
- 根因：sensors TB 的 axil_write 是任务2 中途缺陷版（非 fork/立即撤销版），复现了 DEF-2-05 的重放问题。
- 修改：整体替换为任务2 最终版 axil_write（fork 独立通道 + negedge 判定 + 通道排空）。
- 教训：跨任务复制 TB 任务时必须以"任务2 最终交接版"为准，不从历史快照复制。状态：已关闭。

## DEF-3-05/3-07｜TB 测量时序与期望值模型错误（测试错误，非 RTL）

- 首次失败：样本轮询超时；期望 1000mm 实得 985mm 等。
- 根因：①do_measure 中 hold_us*100 的单位混乱、87µs resp 与 trig 等待循环叠加导致宽度不对；②期望值模型用 RTL 的定点常数（照抄被测公式，违反共同约束 11）。
- 修改：do_measure 重构为"等 trig 高→等 trig 低→resp_us 后拉 echo→hold_us 后拉低"的明确时序；模型改为独立整数公式 `ticks*343/200000`；T4/T5 轮询周期适配 8ms 超时；T9 前重写滤波参数（T7 复位会清配置——本身就是被验证的行为）。
- 状态：已关闭。

## DEF-3-06｜S_WAIT_F 卡高判定 32 位无符号下溢 ★真实 RTL 缺陷

- 首次失败：trace 显示 echo 上升后一拍即回 IDLE（S_WAIT_F 一拍退出），T1 全部失败。
- 根因：`wait_cnt - pulse_start >= cfg_max_echo`——若 wait_cnt < pulse_start（计数被重置等异常时序），32 位无符号下溢为巨大值，恒判卡高超时。
- 修改：改绝对比较 `wait_cnt >= pulse_start + cfg_max_echo - 1`。
- 修复前：S_WAIT_F 一拍误出；修复后：脉宽窗口全程正确。回归：T1/T1b/T3 全过。状态：已关闭。

## DEF-3-08｜echo 上升沿清零 wait_cnt 导致脉宽截断 ★真实 RTL 缺陷

- 首次失败：T1 得 982mm（期望 999），EMIT 打印 ticks=572996 = 583000 - 10004（恰为 resp 段）。
- 根因：echo_rise 时 `wait_cnt <= 0` 重启计数，而 pulse_start 锁存的是重启前的绝对值；WAIT_F 的 `wait_cnt - pulse_start` 把两段不同基准的计数相减，脉宽短掉 resp 段。上游 yunkai1841 用单一自由计数器无此问题——移植时引入。
- 修改：rise 时保持 wait_cnt 连续计数（不清零），pulse_start 语义为"本轮测量开始以来的 tick 数"。
- 修复前：脉宽系统性短 resp 段；修复后：T1=999/985（TB 驱动精度内）、T1b、T3 全过。状态：已关闭。
- 教训：移植上游"自由计数器"结构时，拆分成状态机必须保持计数的连续性语义。

## DEF-3-09｜seq 未接出到寄存器（契约违背）

- 首次失败：T6 seq.inc 失败——0x038 高 16 位=err、低 16 位恒 0。
- 根因：car_ultrasonic 的 seq_cnt 未引出端口，top 读译码 `{err,16'b0}` 与契约 §8 "0x038 [15:0]=seq" 不符。
- 修改：加 samp_seq 输出端口，top 接 `{err_cnt, us_seq}`。
- 状态：已关闭。

## 测试时序修正（非缺陷，记录备查）

- T5 轮询首拍撞上 T4 遗留 fault=1 样本 → 改为等 fault==2 的样本（唯本轮卡高可产生）。
- T6 ts.stable 对比跨测量周期 → 改为同一测量后立即连读（后续自动测量的无效样本合法更新时间戳，契约 §8a 允许）。
- T6 快照检查原期望抓 US 批，实际抓 IR 批（契约允许"最近一批"）→ 改为校验快照数据有效性，同批核对由 T10 承担。

## 2026-09-18 Codex验收补修

详细编号R01—R16见[验收报告](acceptance_20260918/任务1-4验收与修改报告.md)，包含来源归属、触发条件、修改与回归。原DEF记录保留历史，原BFM“不可改动”和“无符号减法一律禁止”的结论不作为规则；需按当前计数器是否连续、位宽和握手沿判断。

- task4半成品的乘移位M法、悬空if与语法残留已被周期法候选和严格TB替换；未声称旧整套TB曾通过。
- 首轮新QEI TB失败3项是刺激相位假设错误；改为翻转当前电平再还原后通过，未放宽断言。日志sim_tb_car_qei/20260918_115310_348保留。
- 首次周期法综合WNS -0.766ns；标定乘积拆分/流水后+2.367ns，重新验证数值与综合。旧日志acceptance_synth.log保留，最终完整证据在acceptance_20260918/run_20260918_120732。
- 原传感器TB使用80ms超时并等待valid=1，超量程新反例因此等不到结束且整体watchdog失败；改为等待新seq（无效批也完成测量），模拟等待缩至8ms仍覆盖5.83ms回波，生产值39ms独立断言/契约保留。旧失败sim_tb_car_sensors/20260918_115633_227保留。
- C校验位置反例先修长度与版本，再做变异对照：正式两版拒绝，单独撤销绑定检查的构建副本接受，证据见解析器变异验证.md。
- 最终两版C测试、18项Python、287项RTL检查及三个模块综合通过；USB临界区为静态审查和ARM构建证据。剩余传输时间闭环与实物验证明确交给今晚任务，不冒充已测。

---

# 夜间A接管与自修复记录（2026-09-19 Codex）

## DEF-A-01｜跨层夹具以10ms发帧，违背100ms生产调度

- 首次反例：IR场景只得到 `reason=8`，且夹具每个10ms C tick都调用 `_decide()`；9600bps传输模型又允许多帧并行完成。
- 根因：测试台把C主循环节拍误当Python发送节拍，形成非真实积压，测试结果不能代表生产链路。
- 修复：独立100ms发送调度与10ms C tick；传输增加 `tx_busy_until`，所有字节在同一9600bps线路串行发送。
- 回归：真实C闭环15项、总回归和综合全过。状态：已关闭。

## DEF-A-02｜释放前驾驶更新可被误认作释放后的新意图

- 反例：抑制态中 `update_command()` 直接置 `_new_intent`；故障清除后可能在没有PREL时退出本端抑制。
- 根因：单布尔量没有表达事件先后关系。
- 修复：增加 `_await_new_intent`，只有成功发出PREL后才接受后续新意图；STOP、超龄、V无效和IR重新清除此阶段。
- 回归：新增“释放前命令不能绕过”“PREL不重放缓存运动”“PREL后新命令才恢复”。状态：已关闭。

## DEF-A-03｜注入时钟未贯穿兼容drive接口

- 反例：构造 `clock_fn=lambda:123` 后调用 `drive()`，命令时间仍来自系统 `time.monotonic()`。
- 修复：`drive()`统一使用 `self._clock()`；新增精确断言。状态：已关闭。

## DEF-A-04｜IR被V=0撤销帧覆盖为传感器故障

- 反例：有效IR=3时 `_decide()`返回通用idle，真实C只记录 `FAULT_SENSOR`，丢失 `FAULT_IR`。
- 修复：发送零速、V=1、真实距离与IR位；STM32仍立即锁存且保留故障来源。
- 回归：跨层IR场景检查 `FAULT_IR`。状态：已关闭。

## DEF-A-05｜DLL构建源不确定且脚本中文路径被PowerShell 5误码

- 反例：递归选择首个 `safe_control.c`；改为中文固定路径后Windows PowerShell按ANSI解码并找不到目录。
- 修复：只允许唯一 `stm32_pynq*` 目录，固定 `Source/APP/safe_control.c/.h`，复制后校验SHA并输出源路径。脚本保持ASCII。
- 回归：构建退出0；生产C SHA256为 `6835C7E22FE093E2779ADCBD8078B92F4D8C6EE0D94945AD4D35FF7F862F3C7E`。状态：已关闭。

## DEF-A-06｜时间回绕测试先人为制造时间戳失效

- 反例：只把C当前时间跳到 `0xfffffff0`，历史 `sample_ms`仍约1秒，真实C按无符号年龄立即锁车。
- 修复：新C实例用有效零速帧跨零刷新，验证跨回绕300ms解锁、后续运动和200ms超龄。
- 回归：15项闭环测试PASS。状态：已关闭。

---

# 夜间B接管与自修复记录（2026-09-19 Codex）

## DEF-B-01｜输出采集器生成0字节文件

- 首次现场：`osd_rtl_f1.rgb`为0字节，且无B交接。
- 根因：旧TB在输入握手后立即读取尚未完成NBA更新的输出，并把输入握手等同于输出握手；随机背压下采集条件不成立。
- 修复：生产者与消费者独立运行，只在`m_axis_tvalid&&m_axis_tready`时写文件，同时按输出序号检查SOF/EOL。
- 回归：128×64七帧114695项、640×480一帧614400项通过。状态：已关闭。

## DEF-B-02｜比较脚本路径指向不存在目录

- 根因：硬编码路径多了一层`host`，且修复后会遗留旧diff图。
- 修复：增加`--rtl-dir/--out-dir`，默认选择最新时间戳仿真目录，成功场景主动删除陈旧diff。
- 回归：总门禁自动定位本轮dump并执行两种尺寸比较。状态：已关闭。

## DEF-B-03｜double-dabble锁存旧拍并截错BCD位 ★真实RTL缺陷

- 保存反例：`acceptance_20260919/night_B_first_failure/compare.log`；f1首差异`(83,16)`，RTL=`ffffff`、参考=`112233`。生产/消费随机种子为`0x20260919/0x0BADF00D`。
- 根因：计数到第15拍时锁存旧`cdc_shift`，且从包含10k位的错误切片取数。
- 修复：显式计算第16次移位`cdc_next`并锁存`cdc_next[31:16]`。
- 回归：原反例、连续帧、负速度、无效值、随机空洞/背压和默认640×480全通过。状态：已关闭。

## DEF-B-04｜RTL内联字模与MEM/Python字模分叉 ★真实RTL缺陷

- 现象：BCD修复后字符轮廓仍逐像素不一致。
- 根因：RTL保留一份内联case，Python读取另一份`.mem`，两个来源已不一致。
- 修复：删除内联case，RTL与Python只读取自制`font_8x8_minimal.mem`；仿真、综合和工程生成脚本都显式携带该文件。
- 回归：七场景与640×480逐像素一致；Vivado报告`$readmemh`成功。状态：已关闭。

## DEF-B-05｜US与QEI有效性被合并 ★接口结构缺陷

- 触发：QEI失效但US有效，或US失效但QEI有效；单valid会让两行同时显示无效或让失效值冒充有效。
- 修复：OSD输入拆为`state_distance_valid/state_speed_valid`，SOF分别提交；f6/f7分别覆盖单路失效。
- 回归：f6/f7各8192像素逐点一致。状态：已关闭。

## DEF-B-06｜异常恢复扩展TB未消费早EOL输出

- 首次失败：`sim_tb_car_axis_osd/20260919_015207_730`看门狗。
- 根因：新测试在早EOL后把`m_axis_tready`拉低且未先消费已注册输出，随后等待`s_axis_tready`形成测试台自锁，非RTL错误。
- 修复：异常事务后显式完成一次输出握手，再发送意外SOF。
- 回归：短行、意外SOF、帧中复位和恢复后新帧共1326项通过。状态：已关闭。

---

# 夜间D接管与自修复记录（2026-09-19 Codex）

## DEF-D-01｜IR变化时间被误作周期样本年龄 ★真实RTL安全功能缺陷

- 最小反例：IR保持`stable=1/无障碍`且状态不变，`IR_TS`按契约不刷新；运行200ms后风险核原逻辑置reason bit6并FAULT停车。
- 根因：`car_sensors_core`把`IR_TS`定义为状态/稳定标志变化时间，`car_risk_core`却套用US/QEI的`DATA_MAX_AGE_TICKS`。这与`interface_contract.md`“静态输入不更新，不得直接作连续采样新鲜度”冲突。
- 修复：删除IR变化时间的周期过期判断；继续检查`ir_valid`、`ir_status.stable`与障碍位。reason bit6保留。没有伪造心跳更新时间。
- 局限：断线固定高仍无法与真实静态无障碍区分，交给硬件偏置和实物测试。
- 回归：`tb_car_risk_core`新增“static IR does not false-expire”，22项通过；A—D全门禁与六模块综合通过。状态：已关闭。

## DEF-D-02｜开发机不得伪装PYNQ MMIO

- 反例：PC环境执行`--transport pynq`，本机没有`pynq`包。
- 修复：PYNQ导入延迟到`PynqMMIO`构造；缺包给明确错误并退出1，不创建输出、不回退到FakeIO。
- 证据：`acceptance_20260919/night_D_pynq_unavailable.log`。状态：已关闭；真实板上MMIO仍待验证。

## DEF-D-03｜整体停车判定错误覆盖了P帧的IR故障来源 ★跨层安全诊断缺陷

- 最小反例：PL快照为有效、稳定的左红外障碍；旧D夹具把`SafetyDecision.permit=false`直接传给`CarLink.update_sample(valid=...)`，并把IR固定为0。真实C最终收到`V=0/IR=0`，记录`FAULT_SENSOR`而不是`FAULT_IR`。
- 根因：驾驶许可、距离/IR样本有效性和协议故障来源是三个不同语义，旧夹具错误地把整体许可折叠成传感器V位。
- 修复：在`perception_client.py`增加纯映射`snapshot_to_link_sample()`；它只依据US新鲜度/故障和IR valid/stable生成`valid/distance_mm/infrared_mask`，不更新驾驶请求。QEI、风险和命令故障继续由`SafetyDecision`停车，但不篡改有效IR样本。
- 反例回归：有效左IR障碍现在形成`V=1/L=R=0/IR=1`，送入生产`build_p()`和真实`safe_control.dll`后置`FAULT_IR`且不置`FAULT_SENSOR`。链路20项、夜间A闭环15项和全门禁通过。状态：已关闭。

## DEF-D-04｜JSONL缺字段可静默回落为零，MMIO适配未限制窗口

- 最小反例：删除事件0的`US_TS`后，旧加载器仍接受文件，回放transport把缺失寄存器读成0；header中的`contract_version`也未校验。`PynqMMIO`允许非对齐或超出构造长度的offset下传。
- 根因：JSONL只检查`type/registers`外形，未把原始快照字段完整性作为稳定schema；MMIO薄适配没有在业务边界验证32位访问范围。
- 修复：加载时校验schema、契约ID/版本、100MHz tick、source/hardware、连续index、epoch、64位PL tick、主机时间、完整寄存器集合、uint32值和expected结构；错误包含文件、行号和首个事件。MMIO增加4字节对齐与`offset+4<=length`检查。
- 回归：缺`US_TS`的事件0由CLI明确退出1并打印schema/契约/首个事件；fake PYNQ MMIO验证基址、长度、读写屏蔽和越界拒绝。定向D测试16项及全量主机35项通过。状态：已关闭。

---

# 任务7/8独立预集成自修复记录（2026-09-19 Codex）

## DEF-78-01｜DDR带宽按RGB888和三次搬运低估

- 首次问题：旧文档按3字节像素和约3次搬运估算，未反映PS/VDMA实际使用的32位对齐缓冲。
- 根因：把AXIS侧RGB888格式直接套到DDR，漏计主机帧到DMA缓冲区的复制。
- 修复：DDR契约固定为little-endian `BGR0`、4字节/像素；按解码写、复制读、DMA缓冲写、VDMA读四次计算，640×480@30保守预算为147.456 MB/s。
- 回归：Python契约测试检查stride、帧大小和搬运预算。状态：已关闭；板上吞吐仍未验证。

## DEF-78-02｜固定PYNQ快照缺少TMDS接口定义

- 首次失败：创建HDMI Block Design时，`rgb2dvi`所需的接口定义无法解析。
- 根因：最初稀疏快照只取IP目录，没有取同一仓库的`boards/ip/if`。
- 修复：只扩展已固定的PYNQ commit `e054c09c52db3244ef35c8ae08a2e62c1e4955fd`稀疏范围，加入`axi_dynclk_v1_0`、`rgb2dvi_v1_2`和`boards/ip/if`，没有引入另一来源或旧bit/hwh。
- 回归：工程从空目录重建，Block Design验证、HWH生成、综合和实现通过。状态：已关闭。

## DEF-78-03｜上游RGB2DVI时钟约束与外部dynclk模式冲突

- 首次失败：实现报告`Timing 38-249`，上游XDC从PixelClk创建SerialClk，但本工程`kGenerateSerialClk=false`，两路时钟实际都来自`axi_dynclk`；旧门禁只看setup WNS，可能漏掉hold和断链时钟。
- 修复：对该实例禁用不适用的上游`rgb2dvi_clocks.xdc`，让dynclk产生的真实时钟传播；实现门禁同时检查WNS、WHS、阻断DRC及已知错误模式。
- 回归：最终完全布线，WNS `+1.317ns`、WHS `+0.026ns`、TNS/THS 0；无`Timing 38-249`、`Designutils 20-1307`或`Common 17-55`。状态：已关闭。

## DEF-78-04｜VDMA和HPD事件没有进入PS

- 首次结构审计：VDMA MM2S与HPD GPIO存在，但中断未接到PS，板端只能轮询，三缓冲所有权和热插拔无法按设计工作。
- 修复：用现代`xilinx.com:inline_hdl:ilconcat:1.0`汇合`video_vdma/mm2s_introut`与`hdmi_hpd_gpio/ip2intc_irpt`，接入PS `IRQ_F2P`。
- 回归：HWH契约验证两路中断路径和PS端点。状态：已关闭；Linux中断发现仍待实板。

## DEF-78-05｜旧Base Overlay的HPD方向不符合本地R12原理图

- 首次冲突：开源Base Overlay把HPD配置为输出；本地`TUL_PYNQ Schematic_R12.pdf`第6张图显示HDMI pin 19经Q8 2N7002进入`HDMI_TX_HPDN`，并由R158上拉，实际是主动低FPGA输入。
- 修复：本工程以本地板卡资料为准，用AXI GPIO输入读取HPDN，不复制旧方向。
- 回归：生成HWH显示GPIO输入；实现IO报告显示R19为`INPUT/LVCMOS33`。状态：已关闭；实物修订版仍需上板确认。

## DEF-78-06｜HPDN改为标量后XDC仍使用总线下标

- 首次失败：约束写成`hdmi_tx_hpdn[0]`，Vivado报`Common 17-55`，R19实际未约束。
- 修复：XDC改为标量端口`hdmi_tx_hpdn`，并把`Common 17-55`纳入回归拒绝模式。
- 回归：最终运行0 error、0 critical warning；IO报告确认R19、方向和IOSTANDARD。状态：已关闭。

## DEF-78-07｜Vivado运行文件混入上一次失败告警

- 首次复核：自动生成的`.vdi`仍含HPDN修复前的`Common 17-55`，直接把它当最终日志会与正确的最终IO/时序报告矛盾。
- 修复：从`impl_final.log`按最后一次会话标记提取`impl_final_session_20260919_094906.log`，机器证据只引用该会话；旧失败日志继续保留作自修复证据。
- 回归：新增Python反回退测试，要求最终日志不存在critical warning、error及三个已知坏约束模式，并检查时序/DRC/IO证据文件存在。Python现为17项通过。状态：已关闭。

---

# 夜间E与任务7/8集成自修复记录（2026-09-19 Codex）

## DEF-E-01｜板级manifest混淆内部时钟与物理连接器端口

- 反例：旧manifest把纯PL内部`clk/rst`与外接Pmod/HDMI信号放在同一核验语义下，无法准确表达“板载管脚已核对，但外设电平未核实”。
- 修复：升级schema v2，区分internal/physical、board pin证据与external electrical readiness；普通校验和`--release`门禁使用不同判定。
- 回归：普通校验通过21个逻辑端口；release准确列出十个外接电气未确认信号和板卡修订版未确认。状态：已关闭。

## DEF-E-02｜集成工程漏加入生成寄存器头文件

- 首次失败：`car_perception_top`加入Block Design后，OOC综合找不到`car_reg_defs.vh`，生产控制核不能生成DCP。
- 根因：原纯RTL脚本通过include目录间接可见；新的BD module reference只显式加入`.v`和字体文件。
- 修复：`create_integrated_candidate.tcl`显式加入机器生成的`.vh`，继续以`register_map.json`为唯一机器源。
- 回归：生产`car_system` OOC综合通过，HWH显示`car_board_video_wrapper`，集成实现完全布线。状态：已关闭。

## DEF-E-03｜UART1 EMIO外部端口名与XDC不一致

- 首次反例：初版XDC使用`uart_tx/uart_rx`，Vivado生成包装层实际端口为`uart_txd/uart_rxd`，会导致约束失配。
- 修复：以生成wrapper和PS7 EMIO接口为准统一为`uart_txd/uart_rxd`，manifest、XDC与HWH审计同步。
- 回归：HWH集成模式确认UART EMIO存在；最终IO报告包含V12/W13约束。状态：已关闭。

## DEF-E-04｜板端运行器仍接受控制占位核

- 反例：生产核完成集成后，`board_runtime.py`仍要求`control_slot_stub`，真实集成HWH会被拒绝，旧隔离HWH反而可能进入板端启动路径。
- 修复：板端运行器固定要求`car_system@0x43C00000/4KiB`，显式拒绝`control_slot_stub/osd_slot_stub`，并以HWH集成模式审计。
- 回归：Python契约测试覆盖正确生产地址、错误地址和旧占位overlay拒绝。状态：已关闭。

## DEF-E-05｜包装层背压反例的测试时序错误

- 首次失败：`sim_tb_car_board_video_wrapper/20260919_102326_954`报告四次valid未保持。
- 根因：TB在输出已经以`m_ready=1`被消费后才拉低ready，检查的是不存在的事务，不是RTL缺陷。
- 修复：输入前先拉低`m_ready`，等输出valid后记录payload，再连续四拍检查valid/data/TUSER/TLAST稳定，最后恢复ready消费。
- 回归：同一包装层12项通过，AXI生产ID和AXIS背压路径均被覆盖。状态：已关闭。

---

# LAB_ONLY无电机台架包自修复记录（2026-09-19 Codex）

## DEF-LAB-01｜发布门禁阻止生成上板验收载荷

- 首次问题：任务7/8必须先在无电机状态验证MMIO、传感器、UART STOP和视频链路，但release门禁在实物证据齐全前按设计拒绝发布，形成“没有载荷就不能取证”的闭环依赖。
- 修复：新增独立分类`LAB_ONLY_NO_MOTOR_NON_RELEASE`；构建脚本要求普通manifest校验通过且release校验必须失败，只生成带哈希、禁运动声明和物理状态全false的台架bit/hwh，不改变发布门禁。
- 回归：Vivado bitgen 0 error，HWH生产核契约通过；包内契约确认`motor_output_allowed=false`、`release_gate=BLOCKED_EXPECTED`。状态：已关闭；物理项目仍待PYNQ到货。

## DEF-LAB-02｜PowerShell中文路径导致权威通信模块未入包

- 首次失败：构建脚本用中文目录字面量定位`stm32预备程序/pc/pynq_link.py`时，在Windows PowerShell环境中路径被错误解码，打包中止。
- 根因：脚本依赖宿主对非ASCII源码文本的解释方式。
- 修复：在限定的项目树内按`pc/pynq_link.py`文件身份发现唯一权威源，再复制并校验存在性；没有建立第二份协议实现。
- 回归：LAB_ONLY目录和ZIP均成功生成，解压后的`lab_acceptance.py contract`独立通过。状态：已关闭。

## DEF-LAB-03｜板端命令可能在开发机制造伪硬件结果

- 反例：当前没有PYNQ；若板端脚本静默改用fake transport，会把PC结果误记成MMIO、HDMI或UART实测。
- 修复：PYNQ导入采用延迟加载且缺包立即非零退出；UART STOP必须显式给出`--motor-disconnected`，并禁止PREL和非零运动请求。
- 回归：开发机执行`mmio`因缺少PYNQ包安全失败；未声明电机断开时`uart-stop`安全失败，均未生成硬件PASS证据。状态：已关闭。

## DEF-LAB-04｜manifest带UTF-8 BOM导致严格JSON工具拒绝

- 首次失败：Windows PowerShell的`Set-Content -Encoding utf8`给`lab_manifest.json`写入BOM，运行`python -m json.tool`时在首字符失败。
- 修复：打包脚本改用`.NET UTF8Encoding(false)`写标准无BOM UTF-8；运行器仍兼容旧的`utf-8-sig`输入。
- 回归：三个机器清单均通过严格JSON解析，LAB_ONLY契约和17项Python测试通过。状态：已关闭。

## DEF-LAB-05｜包级自检把Python缓存带入交付ZIP

- 首次问题：打包前运行契约自检会在交付目录生成`__pycache__`，造成无关且平台相关的二进制缓存进入ZIP。
- 修复：压缩前只在核验后的LAB_ONLY输出目录内安全删除该缓存；不递归操作其他路径。
- 回归：最终ZIP解压后共15个文件、无`__pycache__`，解压目录中的契约检查通过。状态：已关闭。

## DEF-LAB-06｜UART STOP可能用请求前缓存状态假通过

- 首次问题：旧台架脚本只检查`CarLink.state`中是否出现锁存零输出；若请求前已经缓存相同的`$CAR`，即使STOP后没有收到任何新状态也可能通过。
- 修复：权威`pynq_link.py`为每个合法`$CAR`维护`state_seq/state_rx_time`；台架脚本在STOP前记录基线，只接受序号推进后的状态，并记录第一条锁存零输出的响应时延，默认门限300ms。
- 回归：新增“新状态通过、陈旧状态拒绝”反例；17项链路测试、35项主机测试、十套RTL/逐像素全量门禁均通过。状态：已关闭；300ms实测仍待PYNQ与STM32接入。

## DEF-LAB-07｜传感器台架步骤只有原始快照，没有机器判定

- 首次问题：旧`mmio`阶段会保存寄存器，但正常距离、无回波、Echo卡高和IR 0/1/2/3场景仍依赖人工逐字段阅读，容易漏掉valid、stable或故障码错误。
- 修复：新增`sensor-check`阶段，逐样本检查US valid/fault/距离范围、IR valid/stable/mask和可选risk_stop；任何样本不符即保存首个差异及原始寄存器后非零退出。
- 回归：正常样本和IR/risk反例的纯函数测试通过，参数边界与安全标签受CLI限制。状态：软件闭环已关闭；物理场景仍待PYNQ到货执行。

## DEF-LAB-08｜摄像头读满900帧即可假通过性能验收

- 首次问题：旧camera阶段只要求读取指定帧数；低帧率、长尾卡顿或严重推算掉帧仍会打印视频PASS。
- 修复：camera阶段默认要求实测≥25fps、P95帧间隔≤50ms、估算掉帧率≤5%，将门限、实测值和差异写入JSON后决定退出码；色条阶段改为“已提交、等待人工确认”，不再使用PASS措辞冒充物理画面验证。
- 回归：构造低性能与29.8fps正常摘要分别验证拒绝/通过，参数非法时拒绝。状态：软件判定已关闭；C270和HDMI实测仍待PYNQ。

## DEF-LAB-09｜PL与STM32证据分离，不能证明同一时间线安全闭环

- 首次问题：独立`mmio`和`uart-stop`可以各自通过，却不能证明PL快照/风险判断、Python桥接与真实STM32状态在同一次运行中保持零输出。
- 修复：新增`safety-loop`阶段，使用生产`PerceptionClient`和`CarLink`，只更新真实传感器样本与零速命令；记录epoch、原始寄存器、风险原因、链路样本和STOP后新`$CAR`，拒绝非零L/R、epoch冻结、无锁存响应或响应超过300ms。代码路径不调用PREL且不生成非零请求。
- 回归：注入fake MMIO客户端和新鲜锁存`$CAR`完成联合时间线测试，并验证输出证据中全部命令为零、release=false。状态：软件编排已关闭；真实联合链路与30分钟稳定性仍待PYNQ。

---

# ZCode只读审计后自修复（2026-09-19 Codex）

## DEF-AUD-01｜控制源切换继承旧快照，可被兼容STOP帧解锁

- 反例：USB接管仅调用`safe_fault(FAULT_START)`，仍保留`valid/clear_tracking`；最后一帧`$P`尚未达到200ms年龄时，兼容STOP帧可清除锁存。
- 修复：新增纯逻辑接口`safe_source_handover()`，在锁车之外废弃`valid/clear_tracking`并清空左右RAW请求；USB接管和回切USART2都使用该接口。
- 回归：对接版C测试通过；真实生产DLL跨层16项通过，新增反例确认源切换后99ms到达的兼容STOP帧仍保持锁存。状态：已关闭。

## DEF-AUD-02｜风险核QEI过期与IR stable检查缺少可杀死变异的断言

- 反例：删除QEI0 stale判断的M4和删除IR stable判断的M6在旧22项TB中存活。
- 修复：TB增加QEI0/QEI1年龄恰等于阈值、恢复新鲜、IR valid但stable=0及恢复场景；主机测试补`qei0_stale/qei1_stale/ir_invalid`断言。
- 回归：风险核31项通过；M4与M6均KILLED；六模块OOC综合通过，风险核100MHz WNS +3.217ns。状态：已关闭。

## DEF-AUD-03｜寄存器分区重叠与台架空采样缺少底层门禁

- 修复：寄存器生成器拒绝重复分区名、反向范围及相邻重叠；`run_mmio()`和`run_sensor_check()`直接调用时也要求至少2个样本，以证明epoch推进。
- 回归：重叠分区负向测试、直接调用0/1样本负向测试通过；CLI原有`count<2`门禁未改。LAB_ONLY以既有bitstream重打包，包内无`__pycache__`，新ZIP SHA-256为`ae1bd4e61234bebf638658e0bd4f6730c6e40c296b768eaf441b9b8b27af3bf9`。状态：已关闭。

---

# ZCode第二轮只读审计后自修复（2026-09-19 Codex）

## DEF-AUD2-01｜源切换请求清零断言使用零值前提

- 首次反例：删除`safe_source_handover()`中的`left_req=0`或`right_req=0`后，旧C测试和主机`test_15`都通过；两套测试在切换前的请求本来就是零。
- 修复：C测试与真实DLL跨层测试都先接受`L=1200/R=-800`的有效生产`$P`帧，确认请求字段非零，再执行源切换并断言二者清零。
- 回归：D3/D4两个单点删除变异在C测试和主机测试中共4/4 KILLED；生产DLL 16项闭环通过。状态：已关闭。

## DEF-AUD2-02｜损坏HWH产生原始XML堆栈

- 首次反例：包内HWH被截断后，`contract`虽以非零退出安全拒绝，但向操作员打印`ElementTree.ParseError`堆栈。
- 修复：包级验证入口捕获`ET.ParseError`并转换成稳定的`LAB_CONTRACT_FAIL: hwh not well-formed`；没有吞掉其他契约失败。
- 回归：真实LAB_ONLY副本中的截断HWH以退出码1和单行错误拒绝，正常包契约继续通过；框架20项测试通过。状态：已关闭。

## DEF-AUD2-03｜未写RISK_CMD时的PL风险基线未纳入台架证据

- 首次问题：当前LAB_ONLY循环不写`RISK_CMD`，因此stop保持1；旧文档只看stop会把故障注入误判为已生效。ZCode建议值`0xC0000002`也与RTL位拼接不符。
- 修复：按RTL真实布局`reason_bits[31:16] / reserved[15:3] / level[2:1] / stop[0]`统一文档和解码；仅command-invalid时为`0x00020007`，首次快照可叠加其他无效原因。联合证据新增`baseline_pl_risk`与`risk_reason_changes`。
- 回归：解码与联合时间线定向测试通过；README和无电机验收均要求按原因位变化判断注入效果。生产`RISK_CMD`写者和250ms续租仍为`HARDWARE_PENDING`，没有伪装成已上板解决。状态：软件与文档缺口已关闭。

## 第二轮修复后的统一证据

- 完整命令：`powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1 -Synthesis`
- 结果：`ARCHITECTURE_SOFTWARE_RTL_PASS (not hardware acceptance)`；证据目录`nightly/acceptance_20260918/run_20260919_152456/`。
- LAB_ONLY包契约通过；ZIP无`__pycache__`/`.pyc`，新SHA-256为`fd813fdb509d252d703e3bb5741ffbbf5683eac594679a866f35a05d54c0a29e`。
- release门禁仍按设计以退出码1阻塞10个外接信号电气检查和实物板卡修订版确认。

---

# ZCode第三轮只读审计观察项收口（2026-09-19 Codex）

## DEF-AUD3-01｜隔离预集成清单复用旧综合日志

- 观察：`verification_20260919.json`的软件/RTL证据已更新到15:24，但综合日志仍指向03:43；RTL未变化时结果可复用，却增加最终交付时辨认源码与证据对应关系的成本。
- 修复：重新执行`run_tests.ps1 -Vivado -Synthesis -RequireAEBlocked`，将软件/RTL和综合日志统一指向`task7_8_tests/20260919_161107/`；清单测试新增同目录、完成标志和已知坏时钟诊断检查。
- 回归：20项Python、312/34项RTL、HWH契约和Vivado综合通过，框架WNS `+4.446ns`。状态：已关闭。

## DEF-AUD3-02｜Vivado辅助日志落在项目根目录

- 观察：统一门禁从工作区根目录调用Vivado时产生`retry_open_fs.log`，虽是无害工具日志，但会干扰只读审计的权威树哈希差异。
- 修复：统一门禁把Vivado工作目录改为本次时间戳证据目录；预集成创建、检查、综合和实现也分别在`LogDir`内运行。删除已确认内容与本轮Vivado调用一致的根目录孤立日志。
- 回归：预集成综合通过；完整`run_acceptance.ps1 -Synthesis`再次通过，最新证据为`run_20260919_161918/`，根目录不再出现`retry_open_fs.log`。状态：已关闭。

---

# 双前轮编码器复审收口（2026-09-20 Codex）

## DEF-ENC-01｜SCALE配置失败后寄存器半配置

- 首次反例：QEI0写入成功、QEI1抛出I/O错误时，原实现直接退出，QEI0仍保留新值；读回不一致和命令行二次稳定读回失败也不清理。
- 修复：配置与稳定性检查的所有故障路径都尝试把QEI0/QEI1 SCALE清零并逐路读回；清理无法确认时返回`cleanup incomplete`并要求重载bitstream，不恢复可能已经不可信的旧值。
- 回归：第二写失败、读回错误、清理失败、显式双路清零四类反例通过；host 61项与preintegration 21项通过。状态：已关闭。

## DEF-ENC-02｜电平转换使能未落入硬件工程

- 首次问题：文档只给“跳线/GPIO二选一”，RTL、Block Design、XDC和bitstream没有`/OE`控制，实际焊接仍可能硬接GND或上电悬空。
- 修复：外部10k上拉到3.3V，JA9/W18连接`qei_oe_n`；PL未配置时由电阻禁用，复位期间RTL输出高，复位释放后输出低。同步更新manifest、接线文档、无电机验收和LAB_ONLY说明。
- 回归：wrapper 18项通过；集成工程从零重建并完成布局布线，WNS +0.383ns、WHS +0.039ns、阻塞DRC 0；新bit/hwh及ZIP已生成。状态：软件/实现已关闭，实物电平仍HARDWARE_PENDING。

## DEF-ENC-03｜Pmod 5V来源表述错误

- 首次问题：交接把“Pmod B的3.3V/5V脚”作为待选，可能诱导从Pmod取5V；TUL R12第3页明确Pmod A/B电源脚都是VCC3V3。
- 修复：编码器板5V固定使用Arduino POWER头J7 pin 4的VCC5V0，只供两块霍尔板；电机动力继续由TB6612提供。文档强调上板先测电压、纹波与电流。
- 证据：TUL R12第3页Pmod网络与第4页Arduino POWER头网络。状态：文档决策已关闭，实物测量仍HARDWARE_PENDING。
