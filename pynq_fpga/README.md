# PYNQ FPGA 工程

当前接口契约 v0.10 / `0xC425100A`，目标 PYNQ-Z2 `xc7z020clg400-1`，生产公共时基 100 MHz。完整构建候选为 `v010_edge_console_20261014_r2`，当前实板锁车运行基线为 `v010_uart_role_fix_20261014_r3`。

## 主要入口

| 内容 | 路径 |
|---|---|
| 仓库总览 | [根目录 README](../README.md) |
| 完整构建与回归 | [COMPLETE_BUILD.md](preintegration/COMPLETE_BUILD.md) |
| 当前发布和硬件证据 | [release_manifest.json](../release_manifest.json) |
| 可移植候选记录 | [portable_r2/latest_candidate.json](preintegration/portable_r2/latest_candidate.json) |
| 当前运行包 | [release/v010_uart_role_fix_20261014_r3](release/v010_uart_role_fix_20261014_r3/) |
| 接口契约 | [interface_contract.md](nightly/interface_contract.md) |
| 开源采用记录 | [OPEN_SOURCE_USAGE.md](OPEN_SOURCE_USAGE.md) |

## 目录

- `fpga/rtl/`：生产 RTL、安全核、QEI、OSD 和视频包装层。
- `fpga/tb/`：20 套自检仿真与跨层反例。
- `fpga/registers/`：机器可读寄存器契约和生成器。
- `fpga/constraints/`、`fpga/board/`：XDC、板级 manifest 与无电机验收规则。
- `host/`：PS 感知、控制监督、标定、回放与单元测试。
- `preintegration/`：完整构建、运行会话、网页、证据审核和发布入口。
- `release/`：GitHub 下载用同源运行包。
- `third_party/`：固定版本依赖、许可证与采用来源。

## 构建与检查

```powershell
python pynq_fpga/fpga/registers/generate_register_map.py --check
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/run_software_round.ps1 -Round 5
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/build_complete.ps1
python skill/amd-pynq-project-workflow/scripts/inspect_release.py --project-root .
```

完整构建在全新目录执行；成功才写 `latest_candidate.json`。文档或纯元数据修改不能冒充新时序、新 DRC 或新实板结论。

## 当前边界

- r2 已完成完整回归、综合、布局布线、时序、DRC、HWH 和同源打包。
- r3 复用完全相同的 bit/HWH，只修改 STM32 UART 数据口选择、PYNQ 首个有效样本和烧录管理流程。
- 已实板验证烧录读回、锁车通信、US/IR 入 PL 和 PYNQ 重启恢复。
- 电机动力保持断开；QEI 原始输入稳定性、CPR 标定、制动时延、HDMI 色序和 1800 秒联合验收未完成。
