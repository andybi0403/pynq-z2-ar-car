# ZCode两亿Token多轮对抗复核任务书

> 可直接把本文件全文交给ZCode。工作目录固定为`C:\Users\39909\Desktop\FPGA`。

## 你的角色和唯一目标

你是本项目的只读对抗式安全审计员。Codex已经完成A—E、任务7/8集成候选和无电机`LAB_ONLY`台架包。你的任务不是开发、修复或重新设计，而是用最高思考强度，对当前权威代码进行多轮、相互独立、从不同攻击面的复核，找出有可复现证据的真问题并交给Codex修改。

本任务允许使用最多约2亿token。不要把“消耗token”本身当作进度，也不要用重复输出、复述代码或无变化地重复同一测试消耗额度。应把额度用于独立重读、反例推导、临时副本变异测试、模糊测试、跨层时序推演、构建复现和失败定位。完成一个角度后立即换一个角度，至少完成下面20轮；若仍有额度，继续执行“追加循环”，直到额度、时间或平台单任务上限耗尽。

## 最高优先级：严格禁止修改项目

- 禁止修改、删除、格式化或重命名任何现有生产代码、测试、脚本、文档、manifest、XDC、IP、bit/hwh、ZIP、开源快照和状态文件。
- 禁止执行`apply_patch`、编辑器保存、重定向覆盖、`Set-Content`或任何会改写现有文件的命令。
- 禁止修复问题，禁止补测试，禁止更新`self_repair_log.md`、`status.md`和现有交接文档。
- 唯一允许的主动写入位置是`pynq_fpga/audit/zcode_20260919/`及操作系统临时目录。所有报告、反例、日志副本和临时变异只能放在那里。
- 允许运行现有检查和测试。若权威脚本必然在`fpga/build/`产生新的时间戳构建目录，这是唯一例外；不得覆盖或删除既有证据，更安全时将输出重定向到审计目录或临时目录。
- 变异测试只能针对复制到审计目录或系统临时目录的副本；每轮结束删除或隔离临时副本，绝不能把故意错误写回权威树。
- 发现P0也只能保存证据并报告Codex，不得以“紧急”为理由直接修改。

## 当前硬件边界

- 当前没有PYNQ-Z2，预计约一周后到货。
- 不得声称Overlay、MMIO、超声波、红外、UART实链路、C270、VDMA、OSD、HDMI或30分钟稳定性已经在实板通过。
- 不得打开真实串口、发送运动指令、发送`$PREL#`或解除release门禁。
- 可以完成PC测试、真实STM32生产C DLL闭环、RTL仿真、Vivado综合/实现、HWH/bit契约、离线回放和缺硬件时的失败安全测试。
- 当前LAB_ONLY起始ZIP SHA-256为`9b9e66633f8810c32f31f74ca59d18aefe8450343c5740e0c9f43622437f3d3e`。本任务不得重建或改写该包，只能复制到审计目录后做篡改拒绝测试。

## 开始前必须完整读取

按以下顺序读取，不要只看摘要：

1. `pynq_fpga/nightly/主架构_v0.6.md`
2. `pynq_fpga/nightly/interface_contract.md`
3. `pynq_fpga/nightly/register_map_v0.6.md`
4. `pynq_fpga/nightly/status.md`
5. `pynq_fpga/nightly/night_20260918_A.md`至`night_20260918_E.md`
6. `pynq_fpga/nightly/task_7_result.md`、`task_8_result.md`
7. `pynq_fpga/nightly/LAB_ONLY_台架包交接_20260919.md`
8. `pynq_fpga/nightly/self_repair_log.md`
9. `pynq_fpga/README.md`、`pynq_fpga/preintegration/README.md`
10. `pynq_fpga/fpga/board/no_motor_acceptance.md`
11. `pynq_fpga/OPEN_SOURCE_USAGE.md`
12. `9.17夜间任务队列/01_开源参考与复用要求.md`
13. 本地引脚资料：`pynq-z2资料/引脚约束文件/pynq-z2_v1.0.xdc`、两份原理图和`board_files/pynq-z2/A.0/`

随后读取实际生产源码、生成器、测试和构建脚本。报告不是代码的替代证据；报告与代码冲突时，以当前代码和可复现命令为准并修正文档。

## 不得破坏的冻结边界

1. 保持v0.6单一主线：一个64位时基、一个生产AXI-Lite从机、一个全局快照、一个寄存器机器源、一个风险核、一个OSD功能核、一个Python生产客户端。
2. `register_map.json`是寄存器唯一机器源；禁止手改生成的Verilog/Python/Markdown后不回写机器源。
3. 统一ID保持`0xC4251006`。旧ID只属于验证包装层。
4. 保持STM32安全语义：上电锁存；校验失败、V=0、200ms数据过期、250ms租约、红外置位均锁存；≤200mm只屏蔽正向，≥250mm恢复距离许可；解锁需要停止状态和条件持续300ms。
5. 保持“先更新数据再tick”、200ms先于250ms、距离故障只屏蔽正向、两版帧互串失败、对接版`$ARM#`不解锁等既定行为。
6. OSD保持纯AXI4-Stream功能核，不增加帧缓存、第二AXI从机或传感器寄存器副本。
7. LAB_ONLY保持`LAB_ONLY_NO_MOTOR_NON_RELEASE`、`motor_output_allowed=false`、`release_gate=BLOCKED_EXPECTED`。
8. 不修改`third_party/`快照，不复制无许可证仓库代码，不捏造commit或实测数据。
9. 不通过SKIP、stub替换生产核、降低DRC、放宽阈值、吞异常、用旧快照继续运动或删除失败测试换取PASS。
10. 若你认为冻结决策本身有严重问题，写“待Codex/人工确认”，给出最小反例和影响；无论级别都不得擅自改架构。

## 工作目录和证据纪律

新建`pynq_fpga/audit/zcode_20260919/`，至少包含：

- `00_baseline.md`：源文件清单、哈希、工具版本、初始测试结果。
- `issue_ledger.json`：每个问题的ID、级别、责任标签、状态、首次反例、建议修法、复现命令和证据路径。所有确认问题状态写`AWAITING_CODEX_FIX`。
- `round_01.md`至`round_20.md`：每轮独立审计记录。
- `counterexamples/`：最小输入、随机种子、波形、JSONL、差异像素、日志片段。
- `mutation/`：只放临时副本、变异描述和测试杀伤结果，禁止把故意错误留在生产源码。
- `FINAL_AUDIT.md`：最终结论、待Codex修复清单、仍待实板项和重跑命令。
- `authoritative_hashes_before.json`与`authoritative_hashes_after.json`：对生产C/Python/RTL、测试、脚本、文档、manifest、XDC、LAB_ONLY交付和开源登记逐文件SHA-256；排除`audit/`、`fpga/build/`、`.Xil/`和操作系统临时目录。结束时必须逐项相等。

每个发现必须按以下格式记录：

`ID | P0/P1/P2 | 【codex】【zcode】【共同】 | 文件:行 | 问题 | 触发条件 | 最小反例 | 后果 | 建议一行修法 | Codex应运行的定向测试 | 证据路径`

只报告真问题。无法复现或证据不足的怀疑放到“待证伪假设”，不得算缺陷。不要把代码行数、测试数量、运行时长或token用量当作质量证明。

建议修法可以写伪代码或未应用的unified diff文本，但只能保存在审计报告中。严禁把该diff应用到权威项目。

## 基线门禁

先保存当前哈希与日志，再运行：

```powershell
cd C:\Users\39909\Desktop\FPGA
python "stm32预备程序/pc/test_pynq_link.py"
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/run_tests.ps1 -RequireAEBlocked
python pynq_fpga/lab/task7_8_lab_only_20260919/lab_acceptance.py contract
python pynq_fpga/fpga/scripts/validate_board_manifest.py --release
```

最后一条当前必须非零失败；这是正确的release阻塞证据，不得把它改成PASS。若其他基线失败，保存首个失败、缩减反例并登记为`AWAITING_CODEX_FIX`，不要修改代码，随后继续审计不依赖该失败的轮次。

## 二十轮独立复核

每轮都从源码重新推导，不得仅引用上一轮结论。每轮结束必须保存复现命令、退出码和证据；禁止为了让测试通过而修改任何文件。没有发现问题也要写明实际检查的输入空间、边界和为什么现有证据足够。

### 第1轮：需求到实现的双向追踪

从安全规则、接口契约和任务7/8交付反向定位代码、测试和证据；再从每个生产入口正向追踪到需求。找孤儿需求、无测试代码、测试覆盖不到的分支、文档虚假PASS和重复机器源。

### 第2轮：STM32 C安全状态机

逐路径推演上电、STOP、PREL、IR、V=0、距离180→240→260、200/250/300ms临界值、32位回绕、PWM极值、正反转和刹车真值表。检查中断/主循环共享字段、volatile/原子性、锁存原因清除顺序及错误帧后的输出。

### 第3轮：`$P/$CAR`协议与解析边界

重新手算校验和；覆盖最短/最长合法帧、正负号、前导零、5位数、溢出、嵌套`$`、粘包、分片、残帧、非法UTF-8、两版互串、序号回绕和恰好边界长度。运行确定性fuzz并保存首个失败seed。

### 第4轮：Python UART线程与时效

审计`CarLink`锁、线程退出、串口异常、时钟注入、future/NaN/inf、样本年龄与驾驶租约分离、STOP取消PREL、释放后新意图、`state_seq/state_rx_time`、旧状态假通过和9600bps串行占用。不得用Python安全状态机代替真实C。

### 第5轮：真实C跨层闭环

复核DLL构建SHA、ABI、100ms发送、10ms tick、串行字节延迟和恢复时间线。构造US冻结、驾驶冻结、IR有效障碍、校验损坏、超长帧、掉字节、时间回绕、PREL过早和释放前缓存运动反例。

### 第6轮：寄存器机器源与AXI-Lite

检查地址/宽度/对齐/WSTRB、非法地址、读写并发、AW/W解耦、B/R背压、复位、ID、生成物漂移和地址重叠。对生成器做负向输入与变异，确认`--check`能发现手工漂移。

### 第7轮：全局快照、epoch和PL时基

审计同拍多生产者、快照请求、epoch冻结/撕裂/回绕、time bit31/32位回绕、64位原子锁存、各自sample_ts/seq/valid与全局epoch职责。验证PS monotonic绝不直接减PL timestamp。

### 第8轮：超声波和红外RTL

检查同步器、复位时Echo已高、无回波、卡高、零宽、最大宽度、配置为0、距离乘法截断、序号饱和/回绕、采样时间和IR消抖/低有效/静态状态不误过期。增加边界和随机脉冲测试，不凭仿真延时猜板级电平。

### 第9轮：QEI与测速

检查Gray合法/非法跳变、两路独立、反向符号、位置溢出、周期为0、静止超时、首沿、同时沿、T法单位、Q16.16饱和和13PPR×4假设。硬件CPR未知继续标未验证。

### 第10轮：PL风险核

重新推导原因位、优先级、动态安全距离、无效/超龄、命令租约、IR障碍、方向错误、流水延迟和输出提交。覆盖恰好阈值、回绕、输入同拍变化和连续风险翻转。

### 第11轮：AXI4-Stream OSD协议

检查每个`TVALID/TREADY`组合、长背压、随机空洞、SOF/EOL、异常行长、缺SOF、帧中复位、连续帧、状态只在成功SOF握手提交、字模ROM延迟、负号/无效/边框越界、RGB顺序和输出稳定性。软件参考与RTL同时检查像素和sideband。

### 第12轮：Vivado Block Design集成

检查PS7配置、GP0/HP0、VDMA方向、位宽转换、时钟/复位、IRQ_F2P、HPDN方向、UART1 EMIO、地址映射、唯一生产核、无占位核和HWH契约。不得把综合通过等同实现或实板通过。

### 第13轮：CDC、复位和时序

逐一列出时钟域；检查多位总线是否错误逐位同步、异步复位释放、生成时钟、false path、未约束路径、setup/hold、上游XDC适用条件和跨域状态提交。对最终而非历史失败日志取证。

### 第14轮：XDC与板级电气

交叉核对官方XDC、PA_v3、R12和board XML。区分连接器编号、PACKAGE_PIN、MIO/PL IO、bank电压、IOSTANDARD、方向、上拉和电平转换。不得猜测板卡修订版或把文件存在当实物确认。

### 第15轮：PS视频管线与缓冲所有权

检查C270输入格式、FFmpeg参数安全、BGR0/RGB888字节顺序、stride、帧大小、三缓冲所有权、VDMA完成、HPDN、异常退出资源释放、30fps/P95/掉帧率门限和DDR四次搬运预算。色条提交不得等同屏幕色序通过。

### 第16轮：LAB_ONLY供应链与失败安全

检查现有bit/hwh同名、SHA-256、无BOM JSON、ZIP解压自检、无`__pycache__`、生产核存在、占位核拒绝、motor/release标记、缺PYNQ非零退出、UART必须显式`--motor-disconnected`。把ZIP复制到审计或临时目录后，篡改bit/hwh/manifest逐项确认被拒绝；不得重建或改写权威LAB_ONLY包。

### 第17轮：台架脚本证据真实性

审计`mmio`、`sensor-check`、`uart-stop`、`safety-loop`、`color-bars`、`camera`七阶段。确认陈旧`$CAR`不能假通过、传感器每个样本都判定、联合时间线只发零速、camera低性能会失败、人工色序未确认时不能写PASS。用fake transport覆盖成功和失败路径。

### 第18轮：安全与鲁棒性红队

从不可信文件、JSONL、串口字节、CLI参数、路径、ZIP和HWH XML角度检查路径穿越、命令注入、超大输入、资源耗尽、异常吞噬、符号/整数转换和日志欺骗。不要把本地测试夹具当网络服务夸大风险，只修真实可触发问题。

### 第19轮：许可证和开源可追溯性

逐个核对当前实际复用文件、固定commit、许可证头、NOTICE/来源表及“直接复用/仅参考”表述。无LICENSE的Sobel仓库只能参考。不得联网换一批项目；如联网只用于核实已经登记的仓库和commit。

### 第20轮：独立最终复审

暂时不读前19轮结论，从当前权威源码重新做一次“竞赛评委＋安全审查员”检查。复跑所有门禁，核对原始哈希、实现时序、ZIP、自修复日志、状态文档和所有未验证声明。ZCode不得关闭问题，只能标记“证据充分”或“待Codex复现”。

## 变异、模糊和追加循环

完成20轮后若仍有token，按以下循环继续，不得原样重复：

1. **变异测试循环**：在审计目录或系统临时目录的副本中每轮只引入一个安全相关错误，例如`>=`改`>`、200ms改201ms、原因位交换、epoch检查删除、TREADY保持破坏、manifest哈希跳过。确认现有测试能杀死变异；存活变异说明测试可能存在真实缺口，记录建议新增的测试，但不要修改权威测试。
2. **新种子模糊循环**：协议解析、JSONL、AXI握手、OSD背压、超声波脉冲和QEI跳变使用新的确定性seed。保存seed和首个反例，不要只增加无意义样本数。
3. **边界值循环**：对每个计数器、长度、时间、距离、PWM、地址、帧尺寸执行`min-1/min/min+1/max-1/max/max+1`。
4. **逆向证据循环**：随机抽取一个PASS声明，追到原始日志和测试断言，确认测试确实覆盖该声明；弱证据记为问题并建议Codex降级状态或补测试。
5. **历史缺陷复现循环**：对`self_repair_log.md`中已关闭问题重新构造原始最小反例，确认当前版本没有复发。

每完成一轮追加循环，编号为`round_21`、`round_22`……并在ledger登记其新攻击面。若一轮没有新输入、没有新推导且没有新证据，立即停止重复并换另一攻击面。

## 问题证据闭环（只报告，不修改）

每次失败必须执行：

1. 保存首个失败、输入、seed、波形/日志和退出码。
2. 判断问题属于生产代码、测试夹具、参考模型、生成器、构建环境还是文档。
3. 将失败缩减为最小反例。
4. 从源码定位最可能根因，写出建议的一行修法或伪补丁，但不得应用。
5. 在未修改权威树的前提下重跑最小反例，确认失败稳定可复现；必要时仅在临时副本验证建议是否可能有效，并明确这不是正式修复。
6. 把证据写入审计目录的round报告和`issue_ledger.json`，状态固定为`AWAITING_CODEX_FIX`。
7. 给出Codex修复后应运行的定向测试、跨层回归和全量门禁，不要替Codex修改或关闭工单。

## 停止与交接规则

- 不要在完成前询问用户，也不要等待PYNQ；把实板项保留为`HARDWARE_PENDING`。
- 遇到工具暂时失败先定位并重试最小步骤，不要从头重写项目。
- token或平台时间即将耗尽时，停止启动新长任务，终止你启动的残留进程，确认权威树没有被修改且故意变异只存在于审计/临时目录，写清当前轮次和精确续跑入口。
- 结束前比较`authoritative_hashes_before.json`与`authoritative_hashes_after.json`；若有任何未解释差异，不得自行恢复、提交或掩盖，立即列出差异并标记审计执行违规，交由Codex处理。
- 只有完成20轮、所有确认问题均有最小反例、建议修法和Codex回归要求，且权威树未被修改，才可写本次只读审计完成。
- 即使软件审计完成，也必须保留真实PYNQ、外设电平、UART实链路、C270/HDMI和30分钟稳定性为未验证。

最终交付：

1. `pynq_fpga/audit/zcode_20260919/FINAL_AUDIT.md`
2. `issue_ledger.json`和全部round报告/反例
3. 权威项目“零修改”证明，以及ZCode只新增的审计文件清单
4. P0→P2待Codex修复清单，按【codex】【zcode】【共同】归属
5. 全部定向与全量测试命令、退出码、日志路径
6. 未改动的当前LAB_ONLY ZIP哈希
7. Codex需要逐条复现和修复的问题与全部`HARDWARE_PENDING`项

结束时不要只说“测试通过”。第一屏必须写：发现多少个待Codex处理的P0/P1/P2、是否有存活变异、基线/审计测试结果、是否确认权威树零修改、release为何仍阻塞、Codex下一步只需看哪些文件。
