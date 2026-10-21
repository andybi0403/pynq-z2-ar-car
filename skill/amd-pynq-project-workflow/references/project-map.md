# 项目事实、来源和阅读索引

## 快照边界

盘点日期2026-10-21。项目根目录是使用者传入的FPGA目录；下列路径均相对该根目录。当前案例为 PYNQ-Z2 / Zynq-7020、STM32F103C8T6 / BST-4WD V4.5、USB C270、超声波、红外、双前轮霍尔编码器的AR辅助驾驶小车。

源码契约v0.10 / `0xC425100A`，Vivado 2026.1，生产公共时基100MHz。完整PL构建候选为 `v010_edge_console_20261014_r2`；当前实板锁车基线为复用同一bit/HWH的 `v010_uart_role_fix_20261014_r3`。2026-10-21已用当前源码重跑软件、固件和RTL回归，未重新布局布线。

| 范围 | 2026-09-30记录的证据 | 尚未证明 |
|---|---|---|
| 软件与协议 | 193项Python测试、两份STM32 C回归、14个生产C故障场景 | 实际UART与物理停车 |
| PL功能与显示 | 13项RTL TB、3项像素比对、历史帧生产链路921600像素零差异、9项模块综合 | 传感器电气、HDMI物理输出 |
| 整机实现 | Fully Routed；WNS +0.077ns / WHS +0.020ns；DRC无Warning/Error/Critical Warning，保留1条REQP-181 Advisory | 全部工具消息都无warning、板端可用、连续运行 |
| 交付 | 独立工程、同版bit/HWH与20份运行文件、ZIP及来源绑定 | 板端Python/依赖兼容与实测标定 |
| v0.10构建 | `v010_edge_console_20261014_r2`全流水线PASS；WNS +0.372ns / WHS +0.015ns；bit/HWH与运行包同源 | 新源码的整机重新布局布线 |
| v0.10实板 | `v010_uart_role_fix_20261014_r3`完成烧录读回、正常启动、锁车UART、US/IR入PL和PYNQ重启恢复 | 电机连接、标定、停车时延、HDMI色序、1800秒联合验收 |
| 作品状态 | LAB_ONLY无电机台架，whole-vehicle=NOT_CLAIMED | 允许驾驶的release |

G1共用会话、G2控制闭环、G3帧关联、G4里程/标定接口、G5显示/页面、G6异常收尾、G7联合证据审核、G8完整构建均已形成离线基础；各组硬件证明仍未完成。以后更新从最新机器记录和原始证据出发，不直接沿用本表。

## 权威入口

| 查询事项 | 路径 |
|---|---|
| 导航和最新重建 | `README.md`；`pynq_fpga/preintegration/COMPLETE_BUILD.md` |
| 当前发布与硬件证据 | `release_manifest.json`；`pynq_fpga/release/v010_uart_role_fix_20261014_r3/`；`work/uart_live_fix_20261014/completion_audit.json` |
| 完整PL候选、流水线与结果 | `pynq_fpga/preintegration/latest_candidate.json`；其evidence_dir下的`pipeline.json`与`RESULT.md` |
| 寄存器与接口 | `pynq_fpga/fpga/registers/register_map.json`、同目录`generate_register_map.py`；`pynq_fpga/nightly/interface_contract.md`；生成的`register_map_v0.9.md` |
| PL生产源码、TB | `pynq_fpga/fpga/rtl/`、`pynq_fpga/fpga/tb/`；顶层`car_perception_top.v`与`car_board_video_wrapper.v` |
| PS感知、控制、标定 | `pynq_fpga/host/perception_client.py`、`control_supervisor.py`、`calibration_config.py`、`qei_calibration.py` |
| 联合视频、界面、日志 | `pynq_fpga/preintegration/host/system_runtime.py`、`overlay_session.py`、`frame_association.py`、`frame_metadata.py`、`status_server.py`、`joint_evidence.py` |
| STM32权威实现 | `stm32_pynq对接版/Source/APP/safe_control.c`及头文件；`stm32预备程序/`演示版单独维护；权威PC链路`stm32预备程序/pc/pynq_link.py` |
| 两份固件验证/构建 | 两份固件目录内`tests/run_tests.cmd`、`build_safe.ps1`；主机C DLL夹具是测试产物，不替代权威固件 |
| 板级约束与验收 | `pynq_fpga/fpga/board/board_manifest.json`、`board_electrical_review.md`、`no_motor_acceptance.md`；`docs/03_硬件与接线/13_下一步上板与联合验收流程_20260930.md` |
| PYNQ原始板级依据 | `pynq-z2资料/引脚约束文件/pynq-z2_v1.0.xdc`、`原理图/PYNQ-Z2_PA_v3.pdf`、`原理图/TUL_PYNQ Schematic_R12.pdf`、`board_files/pynq-z2/A.0/` |
| 开源采用情况 | `pynq_fpga/OPEN_SOURCE_USAGE.md`、`pynq_fpga/third_party/`固定快照及对应许可；历史07调研报告仅作背景 |

## 制作过程与失败来源

| 时间/主题 | 原始记录 | 可以提炼的经验 |
|---|---|---|
| 9月9日底盘串口 | `stm32预备程序/最小串口测试说明.md`、`USART2旁路测试说明.md` | 最小固件、核心板脱离底板、发送器开关和旁路对照缩小故障范围 |
| 9月17日方案/固件审查 | `9.17夜间任务队列/10_固件与方案V2安全审查报告_20260917.md` | 租约、协议、针脚、视频回写、CPR、量纲与赛题覆盖缺口 |
| 9月18日实现验收 | `9.18夜间任务队列/01_上次错误与防回退要求.md`、`pynq_fpga/nightly/acceptance_20260918/任务1-4验收与修改报告.md` | 确定性预期、真实背压、全局快照、批次配对、测试变异 |
| 9月19日多轮复验 | `pynq_fpga/audit/zcode_round4_final_20260919/FINAL_AUDIT_ROUND4.md`及前三轮审查/修复目录 | 独立反例与篡改矩阵、失败门禁、关闭历史问题而保留硬件缺口 |
| 编码器/PCB | `docs/03_硬件与接线/10_霍尔编码器TT马达电气与QEI参数核定_20260919.md`、`12_双前轮编码器电平转换PCB设计需求_20260920.md` | 电机轴PPR与轮轴CPR分开，名义标定隔离，OE默认禁用 |
| 9月27日视频可靠性 | `pynq_fpga/preintegration/evidence/video_reliability_20260927/RESULT.md` | 根据实际网络/复位修复供应商IP连接，保留未解除的Advisory |
| 9月30日DSP优化 | `pynq_fpga/preintegration/evidence/drc_optimization_20260930/RESULT.md` | 算术等价与DSP流水同步验证，不能只消警告 |
| 9月30日整机缺口与补齐 | `pynq_fpga/preintegration/evidence/project_completion_audit_20260930/RESULT.md`、`PROGRESS.md`；最新候选RESULT | 模块完成不等于产品可运行，补齐G1—G8并一次同源重建 |

AMD资料为`docs/01_竞赛与报名/01_2026FPGA选题指南_AMD.pdf`：§3.2.5.3与§3.3.5.2（后者PDF第24页，印刷第21页）要求技能包说明范围、方法、失效条件与验证效果，陌生队伍可复用。通用PYNQ技能还需跨题目/板卡验证才能论证通用性，不能仅凭本案例声称已获加分。校赛、AMD具身智能和AMD自主选题的要求分别核对；这里不承诺得分或参赛资格。

## 已知文档漂移

读取时发现：`pynq_fpga/README.md`前段仍有“尚未生成bitstream”的历史文字，后段已列最新LAB_ONLY包；`interface_contract.md`某些段落仍写“尚未完整重建”，但当前ID与候选记录为v0.9。按来源/阶段解释冲突，定位原始日志，不把历史段落当当前状态。此次创建skill未直接修改旧技术文档。
