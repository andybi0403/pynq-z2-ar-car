# ZCode第三轮只读对抗复审

你是本项目的独立安全审计员。工作目录是`C:\Users\39909\Desktop\FPGA`。开启最高思考，进行多轮、相互独立的复核。你的职责仅限发现问题、构造最小反例、核验证据并写审计报告；**严禁修改任何生产代码、测试、脚本、文档、manifest、XDC、bit/hwh、交付包和既有审计文件**。发现问题全部交给Codex修复。

唯一允许新写入的目录是：

`pynq_fpga/audit/zcode_round3_20260919/`

临时变异必须在系统临时目录或上述审计目录中的副本进行，不得覆盖回权威树。正常工具在既有构建目录产生的可再生文件允许存在。开始和结束分别生成权威源、测试、脚本、文档、manifest、XDC、LAB_ONLY文件夹和ZIP的SHA-256清单，并说明每个差异是否只是已知构建产物。不得以测试次数、token消耗或重复描述充当审计成果。

## 必读顺序

1. `pynq_fpga/audit/zcode_round2_20260919/FINAL_AUDIT_ROUND2.md`
2. `pynq_fpga/audit/zcode_round2_20260919/issue_ledger_round2.json`
3. `pynq_fpga/audit/codex_fix_round2_20260919/AUDIT_FIX_REPORT_ROUND2.md`
4. `pynq_fpga/audit/codex_fix_round2_20260919/issue_disposition_round2.json`
5. `pynq_fpga/nightly/interface_contract.md`
6. `pynq_fpga/nightly/主架构_v0.6.md`
7. `pynq_fpga/nightly/status.md`
8. `pynq_fpga/nightly/LAB_ONLY_台架包交接_20260919.md`
9. `pynq_fpga/fpga/board/no_motor_acceptance.md`
10. `pynq_fpga/preintegration/LAB_ONLY_README.md`

当前权威树优先于旧报告。不得直接采信Codex的结论；每个关闭项都必须从实现、真实调用点、反例、回归、打包产物和文档中独立取证。

## 第一轮：逐项复验第二轮修复

### R2-01 非零请求前提与源切换清零

- 确认C测试和真实DLL跨层测试在调用`safe_source_handover()`前，确实成功解析了有效生产`$P`帧，并明确断言`left_req=1200/right_req=-800`；不能只从测试源码看常量存在。
- 重跑D3/D4：分别删除`left_req=0`和`right_req=0`。C测试与主机`test_15`都必须KILLED；四个结果逐项记录退出码与首个断言。
- 增加副本变异：删除“切换前非零断言”、使非零帧校验失败、把非零帧放到handover之后、只给一侧非零。判断现有测试是否会因前提未建立而假PASS。
- 检查时间线没有因时间戳调整改变原安全语义：新源仍需至少300ms有效安全流、显式释放、释放后新驾驶意图；不得提前PREL或复用旧运动请求。
- 审查演示版未被误改、SafeControl ABI未漂移、两版构建仍选中正确源。

### R2-02 损坏HWH的错误边界

- 在解压包副本中分别测试：空文件、首字节损坏、尾部截断、非法XML、非UTF-8字节、根节点存在但关键节点缺失、结构合法但生产IP缺失、结构合法但地址错误。
- 语法解析失败必须以非零退出并给稳定的一行`LAB_CONTRACT_FAIL: hwh not well-formed...`，不得出现`Traceback`；语义契约失败也必须干净拒绝，但不能被错误归类成XML语法失败。
- 正常HWH必须继续通过。确认`except ET.ParseError`范围足够窄，没有吞掉文件不存在、哈希不一致、manifest损坏、地址不匹配或程序缺陷。
- 检查stderr/stdout、退出码和自动化调用者的行为，避免“打印FAIL但退出0”或重复输出。

### R2-03 风险寄存器位布局与证据真实性

- 从RTL赋值、生成寄存器表和Python解码三处独立推导位布局。正确布局是`reason_bits[31:16] / reserved[15:3] / level[2:1] / stop[0]`。
- **上一轮给出的`0xC0000002`是错误值，禁止继续引用。**只含command-invalid（reason bit1）、FAULT level=3和stop=1时应为`0x00020007`。首次快照可叠加US、IR、QEI或命令过期等其他原因，不能把所有首帧硬编码为该值。
- 对`decode_risk_state()`做位走查与变异：stop翻转、四个level、reason bit0/1/10/11/15、保留位污染、全零、全一。检查有无移位、符号或端序错误。
- 检查`safety-loop`的`baseline_pl_risk`来自真实首条时间线，`risk_reason_changes`只在原因位变化时产生，保留前后原始值与样本索引；不得用人工构造字段冒充寄存器证据。
- 构造原因位不变但stop变化、stop不变但原因位变化、多个原因同时出现和恢复的fake transport反例，检查证据不会漏报或误报。
- 核实当前LAB_ONLY循环确实没有写`RISK_CMD`；文档必须把恒stop基线与故障注入结果分开。生产写者和250ms续租仍是`HARDWARE_PENDING`，不得因为PC测试通过而关闭。

## 第二轮：台架包、生成链与漂移审查

- 当前ZIP SHA-256必须精确为`fd813fdb509d252d703e3bb5741ffbbf5683eac594679a866f35a05d54c0a29e`，sidecar、交接文档和实际文件三者一致。
- ZIP内不得含`__pycache__`、`.pyc`、临时证据或绝对路径。解压后`lab_acceptance.py`、README、manifest与权威源一致，bit/hwh哈希和字节数与manifest一致。
- 正常`contract`必须通过；对bit、hwh、manifest哈希、classification、motor_output_allowed、release_gate、integrated ID、生产IP名与地址逐项篡改，必须全部安全拒绝。
- 审查`build_lab_only.ps1 -SkipRegression -ReuseBitstream`：只能复用已有bit/hwh，必须重拷贝当前脚本和README、重新生成manifest和ZIP、删除限定目录内缓存，不能绕过release仍应阻塞的事实。
- 比对`status.md`、LAB交接、manifest、ZIP sidecar与实际最新证据目录`run_20260919_152456`，寻找旧哈希、旧测试数、旧日志路径或把离线PASS写成硬件PASS的漂移。

## 第三轮：完整门禁与测试真实性

- 从干净的可再生输出执行：`powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1 -Synthesis`。核对真实生产C DLL在测试前重建并校验SHA，没有使用旧DLL、stub或错误固件目录。
- 核对两版C、20项通信、38项主机、风险核31项、OSD三组检查、逐像素比较和六模块OOC综合都真实执行。任何SKIP、被过滤的测试、零字节输出、旧日志复用或降低失败等级均登记。
- 对新增测试做反向检查：删掉R2-01修复应失败；移除ParseError捕获应由定向测试发现；打乱风险位解码应失败；删除`baseline_pl_risk`或`risk_reason_changes`应失败。
- 检查测试是否只验证自己构造的期望值、是否共享同一错误实现、是否未断言调用次数/顺序、是否存在未初始化值、四态比较漏洞、异常被吞或“有输出即PASS”。
- 运行`validate_board_manifest.py --release`，它必须因10个外接信号电气检查和实物板卡修订版未确认而非零退出。预期阻塞不是代码缺陷，也不得被修改或跳过。

## 第四轮：跨层攻击面

从不同角度继续找新的真问题，但先做最小反例再登记：

1. 源切换与串口接收交错：帧解析中途切换、切换后缓冲尾帧、USB空闲1000ms回切、200ms数据时限、250ms租约和32位时间回绕的组合。
2. 快照一致性：epoch撕裂、epoch冻结、sample seq不前进、bit31和32位回绕、多生产者同拍更新、PL时间与PS monotonic误混。
3. 风险状态：command invalid/stale、US/QEI过期、IR valid/stable、距离回差与方向位的优先级；重点检查原因位和stop/level是否可能互相矛盾。
4. 包与运行器：缺文件、路径包含空格/中文、只读目录、异常编码、损坏JSON、错误Overlay、旧HWH、新脚本与旧bit/hwh混装。
5. 证据链：日志能否证明调用了真实C与真实RTL，失败是否非零，旧PASS在源码变化后是否被错误沿用，硬件未到的项目是否被伪写为PASS。
6. 安全恢复：任何故障后是否都保持STOP；恢复是否要求真实新鲜样本、至少300ms安全条件、显式释放和释放后新意图；不得重放旧运动。

不得泛报“建议多测试”“可优化性能”等问题。P0/P1必须有可复现功能或安全后果；P2也必须有具体反例、真实不一致或可执行性缺口。

## 第五轮：既有deferred项，仅复核不修改

- `OBS-18-01`：复核`$CAR`无校验和的V0.7双端迁移方案，检查向后兼容窗口、证据序号和失败策略；禁止单边修改当前V2.1。
- `R1-F1`：给出生产`RISK_CMD`唯一写者、250ms续租、首次有效写和停止续租的最小接线路径与上板验收；当前无PYNQ，只能维持`HARDWARE_PENDING`。
- `R1-F2`：检查OSD速度口径是否与演示文档一致；不改风险核物理口径。
- `R1-F4`：复核快照读取造成的age保守膨胀和到板测量法；没有实测不得放宽200ms。

## 输出要求

在`pynq_fpga/audit/zcode_round3_20260919/`至少生成：

- `FINAL_AUDIT_ROUND3.md`
- `issue_ledger_round3.json`
- `round2_fix_verification_matrix.md`
- `hash_before.json`、`hash_after.json`、`zero_modification_check.md`
- `counterexamples/`和`mutation/`中的脚本、固定种子、命令、退出码与完整日志

每个问题必须包含：ID、P0/P1/P2、责任【codex】【zcode】【共同】、文件与准确行号、触发条件、最小反例、实际结果、期望结果、影响、建议的一行修法、Codex应补的定向测试、证据路径、状态`AWAITING_CODEX_FIX`。旧问题分别标`CLOSED_VERIFIED`、`NOT_REPRODUCED`、`OPEN_DEFERRED`或`HARDWARE_PENDING`，不得删除历史记录。

最终报告第一屏必须写清：R2-01/02/03复验结果、新问题数量及级别、存活变异、完整门禁结果、ZIP真实哈希、权威树是否零修改、release为何仍阻塞。完成后停止，不得修复任何发现的问题。
