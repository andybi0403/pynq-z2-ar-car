# ZCode第四轮最终全流程只读审查

你是本项目交付前的独立安全审计员。这是PYNQ实板到货前的**最后一轮完整离线审查**。工作目录为`C:\Users\39909\Desktop\FPGA`，使用最高思考，持续执行到所有离线可验证层次均有证据。你的目标是尽最大可能发现剩余的真实问题，而不是重复前三轮结论或消耗额度。

你的职责只有读取、构造临时副本、运行测试、做变异、核对来源并提交审计证据。**严禁修改权威生产代码、测试、脚本、文档、寄存器表、manifest、XDC、bit/hwh、ZIP、固定开源快照及既有审计目录。所有发现交给Codex修复。**

唯一允许写入的新审计目录：

`pynq_fpga/audit/zcode_round4_final_20260919/`

工具正常生成的可再生构建产物可留在既有`build/`、`tests/out/`和时间戳门禁目录。任何破坏性实验、变异、损坏包、协议畸形输入和不同版本组合必须在系统临时目录或新审计目录的完整副本中进行。不得覆盖权威源，不得重新打包当前LAB_ONLY ZIP，不得清理历史证据。

## 一、审计纪律与判定标准

1. 开始前生成`hash_before.json`，覆盖源代码、测试、脚本、文档、寄存器机器源及生成物、manifest、XDC、开源快照的commit/许可证、LAB_ONLY文件夹和ZIP；结束时生成`hash_after.json`和逐项差异说明。
2. 结论必须来自实现、调用点、反例、回归、综合/实现产物、交付文档六条证据链。旧报告只能当线索，不能当证据。
3. 只报真问题：P0必须会造成安全事故、规则违规或核心功能失效；P1必须有边缘条件失效或工程硬伤；P2必须有可复现不一致、测试盲区、证据缺口或明确的交付风险。泛泛建议不登记。
4. 每个问题先最小化反例，固定输入、种子、工具版本、命令、退出码和首个失败点。测试工具自身出错时，只修新审计目录中的审计脚本并记录自修复过程，不能把工具错误算作产品问题。
5. 不得以代码行数、测试次数、token消耗、日志很长或“前三轮已通过”代替推理。PASS必须说明验证的性质和未覆盖边界。
6. 真实硬件未到的项目统一标`HARDWARE_PENDING`。离线仿真、综合、完全布线、生成bit/hwh均不能写成实物PASS。

## 二、权威基线与必读材料

按以下顺序阅读，当前文件优先于历史描述：

1. `pynq_fpga/nightly/主架构_v0.6.md`
2. `pynq_fpga/nightly/interface_contract.md`
3. `pynq_fpga/fpga/registers/register_map.json`及生成的Verilog、Python、Markdown
4. `pynq_fpga/nightly/status.md`
5. `pynq_fpga/nightly/night_20260918_A.md`至`night_20260918_E.md`
6. `pynq_fpga/nightly/task_7_result.md`、`task_8_result.md`
7. `pynq_fpga/nightly/LAB_ONLY_台架包交接_20260919.md`
8. `pynq_fpga/fpga/board/no_motor_acceptance.md`
9. `pynq_fpga/OPEN_SOURCE_USAGE.md`
10. 三轮ZCode最终报告、问题账本及三份Codex修复/收口报告
11. `pynq_fpga/audit/codex_fix_round3_20260919/AUDIT_FIX_REPORT_ROUND3.md`
12. 项目根目录中的07/08/09报告、AR一体方案、对接版说明、两份Codex硬件/摄像头基线文档和20260917状态PDF

冻结边界：统一生产候选ID为`0xC4251006`；一个64位时基、一个AXI-Lite从机、一个全局快照屏障；每组数据保留独立32位sample_ts/seq/valid；OSD为纯AXIS功能核；STM32是最终执行安全锁存。任何第二套顶层、地址表、风险核、OSD、Python安全状态机或时间基准都视为架构漂移。

## 三、先复核第三轮观察项收口

### 3.1 新鲜综合证据

- 核对`verification_20260919.json`的`software_rtl`与`synthesis`均指向`pynq_fpga/fpga/build/task7_8_tests/20260919_161107/`。
- 检查目录中的20项Python、312/34项RTL、工程创建、HWH契约和`synth.log`确属同一次运行；综合日志必须包含`PREINTEGRATION_FRAMEWORK_SYNTH_PASS`及WNS `+4.446ns`。
- 删除、篡改或改指向旧`synth.log`的临时manifest副本，现有测试必须失败。检查相对路径解析不会因当前工作目录变化而假通过。
- 分辨隔离预集成占位工程与生产集成工程，禁止用前者WNS或HWH证明生产核已接入。

### 3.2 Vivado工作目录与工具产物

- 审查`run_acceptance.ps1`和`preintegration/run_tests.ps1`的Push/Pop路径及异常路径，确保Vivado成功、失败、中断时都恢复工作目录。
- 运行新鲜统一门禁后，`retry_open_fs.log`、`.Xil`、jou/log等辅助文件只能位于本次证据或Vivado构建目录，不得落在FPGA根目录。
- 在脚本副本中令Vivado返回非零，确认`finally`仍执行且失败不会打印总PASS。不得把预期的变异失败登记为产品问题。

## 四、STM32固件与协议全审查

同时审查`stm32_pynq对接版`和`stm32预备程序`，明确二者协议差异，禁止混为一版。

1. `pnum()`与帧解析：空字段、符号、负零、前导零、5位上限、INT边界、MMM≤9999、索引递增后每次读取的边界、13/15与27/29字符边界、恰好最短/最长帧、额外逗号、内嵌NUL、非ASCII和无终止符。
2. 校验和：C、`pynq_link.py`、文档示例三方范围必须一致；手算`$P,1200,1200,1,0888,0,0`并验证。校验失败只能进入安全方向，不能刷新样本、租约或解锁跟踪。
3. 两版互串：对接版拒绝无IR字段帧，演示版拒绝带IR字段帧；拒绝后FAULT、锁存和旧请求处理一致。
4. 时间语义：200ms数据时限、250ms租约、300ms连续解锁、1000ms USB空闲回切，逐项检查`==阈值`、阈值前后、32位回绕及多个事件同拍的优先级。
5. 源切换：USB首次接管和回切USART2都必须锁存、废弃valid/clear_tracking、清零左右RAW请求；非零前提D3/D4变异必须在C和真实DLL两层被杀死。
6. 解锁：上电锁存；只有真实有效、零速、IR清除、距离≥250mm的连续新流维持至少300ms后显式释放；提前PREL、重复PREL、旧运动帧、释放前意图均不能恢复运动。
7. 距离/IR：≤200mm只屏蔽正向、≥250mm恢复；反向脱困保留；180→240→260以及左右正反组合逐步推演。不得把既定“只屏蔽正向”误报为问题。
8. ISR竞争：列出`serial_irq()`和主循环对`rx_head/rx_tail/rx_error/rx_handover`及SafeControl字段的读写；检查原子宽度、volatile、环形缓冲满/空、溢出、半帧、切源时尾帧和ISR重入。
9. 电机输出：按TB6612真值表检查channel/brake，覆盖latched、distance_blocked、DRIVE_RAW、PWM饱和、左右异号、复位和异常模式；确认没有失控正转路径。
10. 启动文件：复核`safe_startup.c`、链接脚本、`build_safe.ps1`、向量表、TIM1/EXTI残留、真实芯片存储布局和构建源唯一性。

必须运行两版C测试、模糊测试、通信20项和真实生产DLL 16项闭环；对关键安全条件做删除/边界反转/旧值继承变异，记录KILLED/SURVIVED。不得为了杀变异改权威测试。

## 五、PL感知、风险、寄存器和时间架构

1. 单一机器源：运行寄存器生成器`--check`，核对地址区域、重叠/包含/空洞、访问属性、WSTRB、只读/只写、复位值、ID和Python/Verilog/Markdown完全一致。
2. AXI-Lite：AW/W乱序、独立背压、B/R保持、非法地址、超时、复位中事务、部分写、连续读写和主机取消；检查开源`axil_reg_if`适配没有违反上游握手语义。
3. 全局快照：一次屏障同时锁存US、IR、QEI0、QEI1和风险；epoch只表示屏障，不能替代独立sample_ts/seq/valid。覆盖同拍多生产者、读中更新、epoch撕裂/冻结、seq回绕、time bit31及32位回绕。
4. US/IR：Echo同步、10us Trig、上升/下降超时、卡高/无回波、最坏约120ms故障发布间隔、IR滤波/stable/mask和恢复。检查参数锁存不会中帧撕裂。
5. QEI：非法跃迁、滤波、方向、周期法、零速超时、乘除流水、符号、饱和、13PPR×4假设与真实CPR待标定边界。检查没有把电机轴PPR、减速后轮轴CPR混用。
6. 风险核：方向、距离、刹停距离、US/QEI年龄、IR valid/stable、command invalid/stale及原因位优先级。正确布局为`reason[31:16]/reserved[15:3]/level[2:1]/stop[0]`；只含command-invalid时为`0x00020007`。
7. 时间单位：100MHz下200/250/300ms换算、完整32位时间戳和无符号差值必须一致；搜索并解释所有不同形式的时间比较。
8. 架构唯一性：生产顶层只能有一个64位计数器、一个AXI从机、一个地址译码和一次全局快照。验证包装层可以保留，但不得进入生产综合。

运行全部104/43/31/124/31/33项RTL门禁及六模块OOC综合。针对原因位、阈值比较、seq发布、snapshot原子性和地址译码做有意义的单点变异。

## 六、OSD、摄像头、VDMA与HDMI链路

1. AXIS契约：RGB888字节序、TUSER=SOF、TLAST=EOL、有效握手推进坐标；TREADY阻塞时data/TUSER/TLAST稳定；TVALID空洞不推进。
2. SOF提交：风险、速度、距离和无效状态只能在成功接受SOF时统一提交；连续帧、帧中复位、短行/长行、缺SOF、重复SOF和尺寸异常后必须重新同步。
3. 字模与流水：数字、负号、无效显示、矩形边框、ROM延迟、坐标和sideband对齐；字体来源/许可与自制声明一致。
4. 逐像素证据：1326、114695、614400、7×8192和640×480共307200像素必须来自实际RTL输出；PNG不能只由参考渲染生成。随机背压种子和首差异坐标应可复现。
5. 完整链路：PS/C270取流→DDR三缓冲→VDMA MM2S→32/24适配→PL OSD→VTC/video out→rgb2dvi/HDMI。检查缓存所有权、partial read、色序、帧新鲜度、VDMA地址/stride、HP0带宽和中断。
6. 带宽核算：640×480@30 RGB888约27.65MB/s十进制有效像素数据，明确每次DDR写/读及可能的格式扩展，不能把同一搬运重复或漏算；与Zynq-7020 HP/DDR能力和软件拷贝预算比较。
7. C270：只认VID:PID `046D:0825`及实枚举能力；缺设备/PYNQ包时必须非零退出，不能fake成硬件结果。≥25fps、P95≤50ms、估算掉帧≤5%仍需实板执行。
8. 隔离工程与生产集成工程必须明确区分；检查生产HWH包含`car_system@0x43C00000`且不含两个stub，OSD处于真实视频路径。

## 七、PS驱动、回放与跨层安全闭环

1. `PerceptionClient`只通过生成的`car_regs.py`访问地址；启动先验证`0xC4251006`；版本错、epoch不动/撕裂、valid失败、样本超龄、风险stop一律输出STOP，不回退旧缓存。
2. PL 64位时基必须原子读取；年龄在PL低32位域计算，PS monotonic只用于调度/延迟，不能直接与PL sample_ts相减。
3. JSONL保存原始寄存器、epoch、接收时刻、schema和硬件标志；损坏记录、字段缺失、重复序号、回绕、负速度和错误契约必须干净失败。
4. record/replay必须使用同一个生产解析路径，不能复制简化安全状态机。检查正常→超龄/失联→安全恢复完整时间线。
5. `pynq_link.py`发送频率100ms、C tick 10ms、9600bps串行占用必须符合真实链路；传感器更新不能续驾驶租约，驾驶心跳不能刷新传感器样本。
6. IR有效故障必须以`V=1/L=R=0/IR!=0`送入真实C以保留FAULT_IR，不能统一改成V=0。
7. LAB_ONLY `safety-loop`不写`RISK_CMD`，因此command-invalid stop基线是预期；证据必须使用`baseline_pl_risk`和`risk_reason_changes`，不能以恒stop冒充注入生效。
8. UART STOP只能接受请求后新到达的`$CAR`，不得使用缓存状态假通过；实物≤300ms仍为HARDWARE_PENDING。

## 八、Vivado工程、板级约束和电气安全

1. 从脚本重建隔离工程、v0.6 PL工程和生产集成候选；检查part/board part、IP版本、顶层、源集合、地址、时钟、复位和约束，没有手工GUI状态依赖。
2. 交叉核对本地`pynq-z2资料/`中的官方XDC、两份原理图及board_files。区分连接器针号、PACKAGE_PIN和PS MIO/PL IO，注明页码/图号/行号。
3. 核对Pmod A/B、UART1 EMIO、HDMI HPDN、US Trig/Echo、IR、QEI的方向、IOSTANDARD、bank电压、有效电平、上拉和电平转换。Echo 5V不得直连PL；LM393/霍尔输出类型不确定时必须保留未确认。
4. 只约束实际端口；检查重复管脚、电源/地误用、未约束IO、错误板卡修订版和批量降级DRC。
5. 区分OOC综合、完整综合、完全布线、bit生成、实物启动五层证据。现有集成实现WNS/WHS、DRC、资源报告与manifest必须逐项匹配。
6. `validate_board_manifest.py --release`必须因10个外接信号电气确认和实物板卡修订版缺失而退出1。任何绕过、SKIP或把预期阻塞变成PASS均为P0。

## 九、LAB_ONLY交付包与证据供应链

1. ZIP、sidecar和交接文档SHA-256必须都是`fd813fdb509d252d703e3bb5741ffbbf5683eac594679a866f35a05d54c0a29e`。
2. ZIP应只有预期15项，无`__pycache__`、`.pyc`、绝对路径、临时证据或运动授权；包内脚本与权威源逐字节一致。
3. manifest中的bit/hwh字节数和哈希、classification、motor_output_allowed、release_gate、integrated_id、schema、生产IP和地址必须与实物文件一致。
4. 正常contract通过；空/截断/非UTF8 HWH、缺IP、错地址、坏JSON、缺bit、篡改哈希、错ID等必须单行干净拒绝，无Traceback且退出非零。
5. 板端`mmio/sensor-check/uart-stop/safety-loop/color-bars/camera`七阶段默认不得发送非零运动、PREL或伪造硬件。`--motor-disconnected`只是操作员声明，文档仍需物理确认。
6. 检查历史ZIP哈希只出现在带日期的历史记录中，当前入口不能指向旧包或旧脚本。

## 十、开源许可、来源真实性与竞赛合规

1. 对`OPEN_SOURCE_USAGE.md`逐行核对本地固定commit、实际文件、许可证正文、采用方式和验证结论。直接复用、结构参考和未采用必须区分。
2. verilog-axi MIT、AMDC BSD-3-Clause、PYNQ BSD-3-Clause、HC-SR04 CC0和projf RTL/字体许可必须与本地文件一致；无LICENSE的Sobel仓库只能参考，禁止代码/bit/hwh进入交付。
3. 检查NOTICE、文件头、许可证随交付情况，不得把结构重写虚称上游测试通过，也不得给第三方代码重新许可。
4. 可联网时只核实固定URL/commit/许可证和仓库存在性，不升级依赖、不改快照；无法联网写明“未联网核实”，以本地快照为证。
5. 核查“检测在PS、叠加在PL”是否会被判FPGA仅搬运。列出PL不可替代实时任务：传感器采集/滤波、QEI/周期测速、时间戳/快照、风险融合、AXIS OSD/背压/帧同步，并检查代码和演示文档确实能证明。
6. 对方向三基础5条、拓展5条和100分评分项逐条给出已覆盖/弱覆盖/未覆盖及证据。检测类DPU明确不做，不得重新扩大范围。
7. 复核排期、演示流程、成员分工、文件命名和交付清单，避免把未上板候选写成完成产品。

## 十一、文档与代码全局一致性

全树搜索并逐项处理：

- 200/250mm、200/250/300/1000ms、100MHz tick换算；
- `$P`两版格式、最长长度、校验范围、PREL/ARM语义；
- ID `0xC4251006`与旧验证ID边界；
- 20项通信、38项主机、31项风险核及OSD计数；
- 最新门禁`run_20260919_161918`、预集成`20260919_161107`和当前ZIP哈希；
- “第一版有线/WiFi一体”“红外不进主线/Pmod A接入”等历史方案冲突是否已有当前决策标识；
- PASS、PARTIAL、BLOCKED、HARDWARE_PENDING、NOT RUN的使用是否准确。

历史文档可以保留旧事实，但必须标明时间和已被哪个当前文档替代。发现没有上下文的陈旧当前性声明才登记问题。

## 十二、必须重新执行的门禁

至少执行并保存完整输出：

```powershell
python pynq_fpga/fpga/registers/generate_register_map.py --check
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/run_tests.ps1 -Vivado -Synthesis -RequireAEBlocked
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1 -Synthesis
python -B pynq_fpga/lab/task7_8_lab_only_20260919/lab_acceptance.py contract
python pynq_fpga/fpga/scripts/validate_board_manifest.py --release
```

前四项预期退出0；release预期退出1。核对每一项真实执行的测试数量、源码SHA、日志时间、完成标志和失败传播。严禁用旧日志、stub、SKIP、过滤测试、吞异常或降低DRC等级凑PASS。包内contract必须使用`python -B`，避免在权威交付目录产生`__pycache__`。

## 十三、强制对抗与变异计划

在副本中至少覆盖以下类别，每个变异写明预期杀手测试：

- 固件：删数据超龄/租约/IR/距离/源切换清理/显式释放条件，`>=`与`>`互换，时间改有符号；
- 协议：错误校验范围、帧长±1、字段遗漏、互串接受、坏帧刷新时间；
- RTL：删US/QEI过期、删IR stable、交换reason位、快照漏一组、epoch提前、坐标在非握手时推进、背压下输出变化；
- 主机：版本检查移除、epoch复核移除、旧快照回退、PS时间减PL时间、IR改V=0、并行UART写；
- 工程/包：旧HWH+新bit、错地址、stub混入、manifest旧日志、release布尔翻转、哈希和字节数篡改；
- 文档：自动脚本检查当前阈值、ID、哈希、状态和测试数，避免只人工浏览。

存活变异不能自动等于产品缺陷：先证明该行为可观察且会产生实际后果；无法观察的测试缺口可按P2登记。

## 十四、保留决策与硬件待办

复核但不要擅自实现：

- `OBS-18-01`：`$CAR` V0.7校验迁移必须STM32/Python双端同时设计，当前V2.1不单边修改。
- `R1-F1`：生产`RISK_CMD`唯一写者、首次写入和250ms续租，等待实板联调；LAB_ONLY当前不写是既定安全基线。
- `R1-F2`：OSD平均轮速与风险核最大轮速口径不同，属于UI/演示决策，不改风险物理模型。
- `R1-F4`：快照读取造成age保守膨胀，实板测量前不放宽200ms。
- 真实Overlay/MMIO、Pmod电气、UART≤300ms、C270性能、HDMI色序、编码器CPR/相序/标定、30分钟稳定性继续`HARDWARE_PENDING`。

## 十五、输出与停止条件

在`pynq_fpga/audit/zcode_round4_final_20260919/`至少生成：

- `FINAL_AUDIT_ROUND4.md`
- `issue_ledger_round4.json`
- `full_traceability_matrix.md`：从竞赛要求→架构→代码→测试→综合/实现→实物待办
- `release_readiness_offline.md`：按代码存在、自动测试、综合、实现、bit/hwh、实物六层列状态
- `open_source_compliance_final.md`
- `document_consistency_final.md`
- `hash_before.json`、`hash_after.json`、`zero_modification_check.md`
- `counterexamples/`、`mutation/`、`logs/`中的全部脚本、固定种子和原始输出

每个问题必须含：ID、P0/P1/P2、责任【codex】【zcode】【共同】、准确文件和行号、触发条件、最小反例、实际/期望、影响、一行修法、Codex应补的定向测试、证据路径、状态`AWAITING_CODEX_FIX`。同一根因只登记一次，列出全部受影响位置。

最终报告第一屏必须明确：

1. 新发现P0/P1/P2数量；
2. 前三轮所有问题和第三轮观察项是否独立复验关闭；
3. 存活变异及其可观察性；
4. 五条门禁的真实退出码和最新证据目录；
5. LAB_ONLY ZIP真实哈希与包一致性；
6. 权威树是否零修改；
7. release为何仍阻塞；
8. 离线交付结论：`OFFLINE_READY_FOR_HARDWARE`、`NEEDS_CODEX_FIX`或`BLOCKED`；
9. 到板后按先后顺序必须完成的人工/实物项目。

即使没有新问题，也必须交付完整追踪矩阵、反例/变异结果和证据差异；不得只写“全部通过”。完成后停止，不修改任何权威文件，也不要自行解除release门禁。
