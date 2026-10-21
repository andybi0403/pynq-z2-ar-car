# 本轮脚本归档与复现

本目录保存执行过的脚本，归档副本不是脱离项目的一键部署包。权威工程根目录为 `C:/Users/39909/Desktop/FPGA`，原脚本在 `work/qei_retest_20261012`，串口执行器在 `work/encoder_debug_20261011/run_root.py` 和 `tmp/video_six_uart_exec_20261009.py`。必须保留项目相对布局，或显式把脚本 ROOT 改为实际工程根。

原命令：第一轮使用 `run_root.py work/qei_retest_20261012/round1_board.py pynq_fpga/preintegration/evidence/qei_retest_20261012/round1_uart.json 420 --quiet`；完整构建使用 `powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/build_complete.ps1 -Name v09_qei_retest_20261012_r2 -Wireless`；部署使用 `python work/qei_retest_20261012/deploy_final.py`；第二轮使用 `run_root.py work/qei_retest_20261012/round2_board.py pynq_fpga/preintegration/evidence/qei_retest_20261012/round2_uart.json 600 --quiet`。独立审核使用 `analyze_round.py <UART记录> <新的输出目录>`。

以上第一、第二轮命令中的 run_root.py 均指 `python work/encoder_debug_20261011/run_root.py`。实际构建、部署和采样输出拒绝覆盖；复测必须改用新的候选名称、板端目录和本地证据目录，原档案不得覆盖。板端 PACKAGE 必须指向完成所有构建与部署哈希校验的完整候选。

本次 COM14 及 PYNQ 账号仅适用于当前实物，迁移时重新核对。上板前真实确认电机动力线断开、轮子静止，保持风险许可关闭；临时比例不是实测标定。采样 finally 清双轮 SCALE 并读回 RISK_ENABLE=0。先检查 DeviceLease 和包 manifest；不要为绕过其他 MMIO 所有者而删锁文件。
