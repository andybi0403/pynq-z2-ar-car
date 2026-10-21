# ZCode第三轮审计观察项收口报告

日期：2026-09-19。第三轮报告没有发现新的产品、测试或文档缺陷；Codex对其两条非缺陷观察做了证据管理收口。

## OBS-R3-01：综合证据路径刷新

- 旧状态：`verification_20260919.json`的`software_rtl`指向`20260919_152413`，`synthesis`仍指向`20260919_034333/synth.log`。
- 处理：重新运行隔离预集成软件、RTL、工程创建、HWH契约和综合，将二者统一到`pynq_fpga/fpga/build/task7_8_tests/20260919_161107/`。
- 防回退：`test_verification_manifest_points_to_final_evidence`现在要求综合日志存在、与软件/RTL证据同目录、包含`PREINTEGRATION_FRAMEWORK_SYNTH_PASS`且不含三类已知坏时钟诊断。
- 结果：20项Python、312项像素适配RTL、34项控制占位RTL通过；框架综合WNS `+4.446ns`。

## OBS-R3-02：Vivado辅助文件归档

- 旧状态：Vivado在调用方工作目录生成120字节`retry_open_fs.log`，落在FPGA根目录。
- 处理：`fpga/scripts/run_acceptance.ps1`在时间戳`$out`目录中运行Vivado；`preintegration/run_tests.ps1`的工程创建、检查、综合和实现均在`$LogDir`中运行。根目录旧日志已删除。
- 结果：最新统一门禁证据目录`pynq_fpga/nightly/acceptance_20260918/run_20260919_161918/`包含Vivado工作文件，项目根目录没有新的`retry_open_fs.log`。

## 最终回归

- 隔离预集成：`run_tests.ps1 -Vivado -Synthesis -RequireAEBlocked`，退出码0，证据目录`20260919_161107`。
- 统一门禁：`run_acceptance.ps1 -Synthesis`，退出码0，标志`ARCHITECTURE_SOFTWARE_RTL_PASS (not hardware acceptance)`，证据目录`run_20260919_161918`。
- 统一门禁实际执行：两版STM32 C、20项通信、38项主机、104/43/31/124/31/33/1326/114695/614400/12项RTL检查、7×8192及307200像素比较、六模块OOC综合。
- LAB_ONLY ZIP未因本次证据管理修改而重打包，SHA-256仍为`fd813fdb509d252d703e3bb5741ffbbf5683eac594679a866f35a05d54c0a29e`。
- release仍按设计阻塞；真实板卡、外设电气、MMIO、UART时延、C270/HDMI、QEI标定和稳定性没有被写成PASS。
