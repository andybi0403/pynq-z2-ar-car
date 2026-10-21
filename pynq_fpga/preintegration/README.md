# 预集成、构建与发布

本目录把 RTL、STM32、PS、视频、页面和证据链接到一套可复现流水线。当前契约 v0.10 / `0xC425100A`。

## 当前基线

- 完整 PL 候选：[portable_r2/latest_candidate.json](portable_r2/latest_candidate.json)
- 当前实板锁车运行包：[../release/v010_uart_role_fix_20261014_r3/](../release/v010_uart_role_fix_20261014_r3/)
- 仓库发布记录：[../../release_manifest.json](../../release_manifest.json)
- 完整构建入口：[COMPLETE_BUILD.md](COMPLETE_BUILD.md)
- 首次启动说明：[FIRST_BOOT_PYNQ_Z2.md](FIRST_BOOT_PYNQ_Z2.md)
- 无电机台架包说明：[LAB_ONLY_README.md](LAB_ONLY_README.md)

## 运行层次

| 层 | 证明内容 | 不证明 |
|---|---|---|
| Python/C/RTL 回归 | 算法、协议、边界、并发与自检结果 | 物理电气和实板兼容 |
| `build_complete.ps1` | 同源综合、完全布线、时序、DRC、HWH、ZIP | 实际传感器、电机和屏幕 |
| `deployment_check.py` | 板端依赖、文件和设备路径 | Overlay 已加载或通信正常 |
| `lab_acceptance.py` | MMIO、传感器、UART STOP、摄像头等分项 | 连续整车运行 |
| `system_runtime.py` + `joint_evidence.py` | 联合会话和原始日志复核 | 未测配置或驾驶许可 |
| `release_manifest.json` | 历史候选、软件补丁、包和证据的当前索引 | 新的隐藏测试 |

## 常用命令

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/run_software_round.ps1 -Round 5
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/build_complete.ps1
python skill/amd-pynq-project-workflow/scripts/inspect_release.py --project-root .
```

## 约束

- `latest_candidate.json` 只由完整构建成功路径更新。
- 仅修改主机软件或 MCU 时，另建软件补丁发布记录，显式列出源码差异并复用原 bit/HWH。
- 旧日志、失败反例和修复前材料保留追溯，不覆盖成最终通过。
- 当前包是 LAB_ONLY，电机动力断开，整车 release 为 `NOT_CLAIMED`。
