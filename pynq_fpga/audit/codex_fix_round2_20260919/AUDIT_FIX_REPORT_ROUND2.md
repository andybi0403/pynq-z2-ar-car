# ZCode第二轮只读审计问题修复报告

日期：2026-09-19。修复者：Codex。对应输入：`pynq_fpga/audit/zcode_round2_20260919/FINAL_AUDIT_ROUND2.md`与`issue_ledger_round2.json`。

## 结论

第二轮报告的3项P2均已处理并复验。R2-01和R2-02关闭；R2-03的软件证据与文档缺口关闭，生产`RISK_CMD`写入者、250ms续租和实板现象仍按原计划保留为`HARDWARE_PENDING`。没有修改安全阈值、RTL风险策略、bit/hwh或release门禁。

## R2-01：非零前提使请求清零断言可杀死变异

- C测试：`stm32_pynq对接版/tests/test_safe_control.c:122`先接受`L=1200/R=-800`，确认非零，再调用`safe_source_handover()`并断言清零。
- 跨层测试：`pynq_fpga/host/tests/test_night_a_loop.py:505`用真实生产DLL执行同一非零前提。
- 反例复验：ZCode原`run_handover_mutations.py`和`run_handover_host_mutations.py`重跑后，D3/D4在C与主机两层均KILLED，共4/4。
- 影响边界：只增强测试，没有改变`safe_source_handover()`实现或ABI。

## R2-02：损坏HWH干净失败

- 实现：`pynq_fpga/preintegration/host/lab_acceptance.py:51`捕获`ET.ParseError`，转换为包级契约错误。
- 测试：`pynq_fpga/preintegration/tests/test_framework.py:82`验证退出码、稳定错误前缀和无`Traceback`。
- 实包副本：将HWH截断为`<broken`后，退出码为1，仅输出`LAB_CONTRACT_FAIL: hwh not well-formed: ...`；正常包仍输出`LAB_CONTRACT_PASS`。

## R2-03：纠正风险位布局并提高台架证据质量

- RTL真实拼接为`{risk_reasons, 13'b0, risk_level, risk_stop}`，即`reason_bits[31:16] / reserved[15:3] / level[2:1] / stop[0]`。
- 因此只含command-invalid、FAULT level=3、stop=1时是`0x00020007`。ZCode建议的`0xC0000002`不符合实现，未采用。上电首次快照还可能叠加US/IR/QEI等无效原因，不能强制要求每次原始值都等于该常量。
- `lab_acceptance.py:157`新增统一解码；联合时间线在`baseline_pl_risk`保留基线，并用`risk_reason_changes`记录原因位变化。
- `fpga/board/no_motor_acceptance.md:5`和`preintegration/LAB_ONLY_README.md:82`明确当前LAB_ONLY不写`RISK_CMD`，注入验收必须比较原因位，不能用恒为1的stop证明成功。
- 当前没有PYNQ，不接入未经实测的生产命令写者；该决策继续保留为`HARDWARE_PENDING`。

## 回归证据

- 对接版C测试：PASS。
- 真实生产DLL跨层：16/16 PASS；生产C SHA-256保持`EF32FB8A078FCA7FAF719377BCB728A908D450E8EF43A4BF2D85665E7BE365D3`。
- 预集成框架：20/20 Python测试、312/312传感器RTL、34/34视频包装RTL通过，证据目录`pynq_fpga/fpga/build/task7_8_tests/20260919_152413/`。
- 完整门禁：`run_acceptance.ps1 -Synthesis`退出码0，最终标志`ARCHITECTURE_SOFTWARE_RTL_PASS (not hardware acceptance)`；证据目录`pynq_fpga/nightly/acceptance_20260918/run_20260919_152456/`。
- LAB_ONLY ZIP：`fd813fdb509d252d703e3bb5741ffbbf5683eac594679a866f35a05d54c0a29e`；包内无缓存，`lab_acceptance.py`与权威源SHA一致，正常契约通过。
- release门禁：退出码1，继续阻塞10个外接信号的电气检查和实物板卡修订版确认，行为正确。

## 尚未关闭的既有项

`OBS-18-01`、`R1-F1`、`R1-F2`、`R1-F4`继续维持deferred；真实MMIO、Pmod电气、UART时延、C270、HDMI、QEI标定和30分钟稳定性维持`HARDWARE_PENDING`。
