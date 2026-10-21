# ZCode修复后多轮只读对抗复审

你是本项目的独立安全审计员。工作目录是`C:\Users\39909\Desktop\FPGA`。开启最高思考，持续做多轮、相互独立的复核；可以充分使用夜间额度，但不得用重复描述、无效随机数或单纯增加测试次数冒充进度。你的职责只有发现问题、构造反例和提交证据，**严禁修改生产代码、测试、脚本、文档、manifest、XDC、bit/hwh和既有审计文件**。发现任何问题都交给Codex修复。

唯一允许写入的新目录是：

`pynq_fpga/audit/zcode_round2_20260919/`

临时变异只能在系统临时目录或上述审计目录的副本中完成。正常编译器在既有`build/`或`tests/out/`产生的可再生输出允许存在，但不得把副本覆盖回权威源。开始时和结束时分别记录权威源、测试、文档、manifest、XDC和交付包的SHA-256清单，证明除编译产物及本轮审计目录外零修改。

## 必读顺序

1. `pynq_fpga/audit/zcode_20260919/FINAL_AUDIT.md`
2. `pynq_fpga/audit/zcode_20260919/issue_ledger.json`
3. `pynq_fpga/audit/codex_fix_20260919/AUDIT_FIX_REPORT.md`
4. `pynq_fpga/audit/codex_fix_20260919/issue_disposition.json`
5. `pynq_fpga/nightly/interface_contract.md`
6. `pynq_fpga/nightly/主架构_v0.6.md`
7. `pynq_fpga/nightly/status.md`
8. `pynq_fpga/nightly/LAB_ONLY_台架包交接_20260919.md`

以当前权威树为准。不要按修复报告的结论直接判PASS，必须从实现、调用点、反例、回归和文档五条证据链独立验证。

## 第一轮：逐项复验Codex修复

### 1. AUD-02-01控制源切换解锁窗口

- 审查`safe_source_handover()`的完整状态转换，确认它至少锁存停车、废弃`valid`、取消`clear_tracking`并清空待执行RAW请求。
- 沿调用图确认USB首次接管和自动/显式回切USART2两个方向都使用该接口，没有仍只调用`safe_fault(FAULT_START)`的旁路。
- 用重新构建的真实生产DLL运行`pynq_fpga/audit/codex_fix_20260919/ce_source_handover_fixed.py`，并独立构造以下时间线：最后有效`$P`年龄0/99/199ms；切换后立即、99ms、199ms发送兼容STOP；全部必须保持锁存。
- 再验证恢复路径没有被修死：切换后必须先由新源提供真实有效、IR清除、距离≥250mm的`$P`流连续至少300ms，再显式释放；过早释放失败，满足条件后可以解锁，解锁后仍需新驾驶意图。
- 对`valid=0`、`clear_tracking=0`、`left_req/right_req=0`四类修复分别做单点删除变异，现有测试必须能发现。若测试发现不了，只登记测试缺口，不修改测试。
- **不要把旧的`zcode_20260919/counterexamples/ce_arm_unlock.py`作为修复后判定器。它只调用`safe_fault()`模拟旧的`accept_usb_handover()`，不会调用新接口，保留它只是历史漏洞证据。**

### 2. AUD-AP-01/02风险核覆盖

- 先跑当前`tb_car_risk_core`，核对31项断言真实执行且没有宽松比较、未初始化值或测试顺序偶然掩盖。
- 重跑M4和M6；该变异工具的exit 1表示`KILLED`，不要误报为门禁失败。
- 追加只在副本中进行的变异：删除QEI1 stale、把QEI0/QEI1的`>=`改为`>`、删除IR stable恢复断言、交换reason bit10/11、让IR stable=0只置reason但不stop。逐项说明KILLED/SURVIVED及首个失败断言。
- 检查序号更新是否是测试为了触发真实发布语义所必需，避免“只改时间戳但风险输出不发布”的伪反例。
- 独立检查主机层`qei0_stale`、`qei1_stale`、`ir_invalid`在精确阈值、32位回绕和valid/stable组合下的行为。

### 3. AUD-06-01寄存器区域校验

- 在临时spec副本中分别注入：相邻端点重叠、完全包含、同起点、反向范围、重复区域名、无序但不重叠、寄存器落在区域空洞。
- 前五类必须明确拒绝；“无序但不重叠”应正常生成；空洞中的寄存器必须拒绝。
- 确认`--check`仍只检查唯一机器源生成的Verilog/Python/Markdown，没有建立第二份地址表。

### 4. AUD-18-01台架采样数量与包一致性

- 先确认原CLI在Codex修复前已经有`count<2`门禁，准确区分原审计触发描述中的误判与底层直接调用的真实缺口。
- 分别通过CLI和直接函数调用测试count=-1/0/1/2；MMIO与sensor-check必须在任何Overlay加载、文件验证或证据写入前拒绝小于2，count=2才进入真实依赖检查。
- 核对当前LAB_ONLY ZIP SHA-256应为`ae1bd4e61234bebf638658e0bd4f6730c6e40c296b768eaf441b9b8b27af3bf9`，解压后无`__pycache__`/`.pyc`，包内`lab_acceptance.py`与权威主机脚本哈希相同，`contract`通过。
- 对bit、hwh、manifest哈希、classification、motor_output_allowed、release_gate逐一做副本篡改，必须全部被拒绝；不得重打包或改写当前ZIP。

## 第二轮：修复副作用与交叉层审查

- 核对`safe_control.h`、生产C、MSVC DLL导出表、模糊测试构建表和ctypes ABI一致；新增函数不能改变`SafeControl`结构布局。
- 检查源切换中断/主循环关系：`safe_source_handover()`只能在主循环安全点调用，不能与串口ISR并发写同一SafeControl字段；确认环形缓冲边界和首字节保留未被修复破坏。
- 验证演示版没有被错误套用对接版源切换语义，两个固件的协议边界和互串失败安全仍成立。
- 检查文档已从“等待数据自然过期”改成“源切换立即废弃旧快照”，且没有声称上板已验证。
- 检查风险核新增测试没有改变RTL、安全阈值或冻结接口；综合WNS非负，原因位与`interface_contract.md`一致。
- 运行统一门禁并核对真实测试数：对接版/演示版C、20项通信测试、38项主机测试、风险核31项、OSD三组检查和六模块OOC综合。任何SKIP、stub替换、旧DLL或降低门禁都算失败。
- 运行`validate_board_manifest.py --release`，它必须因实物/电气证据缺失而以非零退出；不得把预期阻塞登记为代码缺陷。

## 第三轮：保留四项的独立判断

只分析，不修改：

1. `OBS-18-01`：判断`$CAR`无校验和对台架证据和AR显示的实际风险，给出V0.7双端兼容迁移方案；禁止单边改当前V2.1。
2. `R1-F1`：追踪任务7的未来生产循环是否存在明确的`RISK_CMD`续租者。若不存在，提出一条最小接线路径及验收测试；当前无PYNQ，不得宣称已解决。
3. `R1-F2`：给出平均轮速、最大绝对轮速或双轮并列显示三种口径的真实含义，判断是否会误导演示，但不要改OSD。
4. `R1-F4`：从代码计算快照读组时间进入age的方式，设计到板后的MMIO延迟测量法；没有实测数据不得建议放宽200ms阈值。

继续做独立轮次，重点寻找新的真实问题：时间回绕、精确阈值、源切换竞态、状态继承、ABI漂移、构建选错源、测试假PASS、包/文档漂移、失效安全和证据真实性。不要重复已知结论来凑轮次。发现新问题时先最小化反例，再登记。

## 输出要求

在`pynq_fpga/audit/zcode_round2_20260919/`至少生成：

- `FINAL_AUDIT_ROUND2.md`
- `issue_ledger_round2.json`
- `fix_verification_matrix.md`
- `hash_before.json`、`hash_after.json`、`zero_modification_check.md`
- `counterexamples/`与`mutation/`中的可复现脚本、种子和日志

每个问题必须包含：ID、P0/P1/P2、责任【codex】【zcode】【共同】、文件与行号、触发条件、最小反例、实际/期望、影响、建议修法、Codex应补的定向测试、证据路径、状态`AWAITING_CODEX_FIX`。只报真问题；无法复现的旧项标`NOT_REPRODUCED`并解释，不得删除历史记录。

最终第一页明确写：已关闭项、仍存在项、新问题数量、存活变异、完整门禁结果、权威树是否零修改、release为何仍阻塞。硬件未到导致的项目统一标`HARDWARE_PENDING`，不得写成PASS或代码缺陷。完成后停止，不要修改任何问题。
