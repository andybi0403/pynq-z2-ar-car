# zero_modification_check：round4最终审查零修改证明

- 基线：`hash_before.json`（2236文件+`third_party_commits.json`6个commit）。
- 终线：`hash_after.json`（2255文件）。
- 排除规则与前几轮一致。

## 比对结果（round4审计窗口内）

- **REMOVED: 0**
- **ADDED: 19**——全部位于本轮统一门禁生成的`nightly/acceptance_20260918/run_20260919_183821/`时间戳目录。工具标准行为。
- **CHANGED: 8**——全部为编译产物（`host/c_build/obj/*.obj`、`safe_control.dll`、两版`tests/out/*.obj/*.exe`）：本轮C测试与门禁重编译（MSVC时间戳）。两版`safe_control.c`与`safe_control_prod.c`不在变更列表。
- **源码、测试、脚本、文档、寄存器机器源及三份生成物、manifest、XDC、bit/hwh、LAB_ONLY ZIP（fd813fdb…）、开源快照（6个commit记录于`third_party_commits.json`，逐一与前三轮登记相等）、既有审计目录：逐字节不变。**

## 开源快照commit核对（hash基线内）

| 仓库 | HEAD（round4实测） | 与OPEN_SOURCE_USAGE登记 |
|---|---|---|
| verilog-axi | 516bd5dadc3365b7f9e225d2af8fe0b8d804fe53 | 一致 |
| AMDC-Firmware | 5cf9769d33cc821fd55b4268ab80e285e3d4a607 | 一致 |
| PYNQ | e054c09c52db3244ef35c8ae08a2e62c1e4955fd | 一致 |
| PYNQ-Z2_sobel_filter_HDMI | 71a4409d76470fac7daed6552b9b3188ffe69d8f | 一致 |
| projf-explore | dd212c2e5e0e0d8bdcf93ba077630dbfd49ae708 | 一致 |
| HC-SR04-FPGA | f4df022d27349fbf1dd71fb0aa99834365dfe0a9 | 一致 |
