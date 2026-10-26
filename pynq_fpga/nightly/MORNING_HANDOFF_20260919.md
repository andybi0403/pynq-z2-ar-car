# 2026-09-19 早晨交接

> 2026-09-19晚间批注：本文件为当日晨间快照。其中"红外和编码器输出究竟为3.3V推挽、5V推挽还是开漏"一条，编码器部分已按厂家手册核定（4.5V—5V、板载上拉、经LVC245，输出级结构仍未知但不影响方案），见`docs/03_硬件与接线/10_霍尔编码器TT马达电气与QEI参数核定_20260919.md`；红外（LM393开集电极+模块上拉）结论不变。电平实测项仍未执行，release仍阻断。

## 第一屏

**已完成：**夜间A/B/C达到软件、RTL与OOC综合PASS；夜间D的MMIO适配、JSONL回放和真实C恢复链在PC通过，板上MMIO仍为PARTIAL。夜间E的板级资料、约束、电气门禁和无电机步骤已完成。生产感知核与OSD已经接入任务7/8独立候选，Vivado完全布线，WNS +0.079ns、WHS +0.027ns。另已生成受限的`LAB_ONLY_NO_MOTOR_NON_RELEASE` bit/hwh与一键验收脚本，供PYNQ预计一周后到货时直接取证。

**P0遗留：**自动测试范围内没有未修复P0。发布门禁仍阻塞：D没有真实PYNQ MMIO证据，外接传感器电平与板卡修订版未实测，也没有发布bitstream或实物安全/显示验证。

**一键重跑：**

```powershell
cd C:\Users\39909\Desktop\FPGA
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1 -Synthesis
```

**早晨最该做的三件事：**

1. 阅读[night_20260918_E.md](night_20260918_E.md)和[板级电气审查](../fpga/board/board_electrical_review.md)，确认发布门禁与真实硬件未验证边界。
2. 打开640×480实际RTL预览：[rtl_640x480.png](acceptance_20260918/run_20260919_102658/osd_compare/rtl_640x480.png)，再检查七个状态场景PNG。
3. PYNQ到货后先确认丝印/修订版和电平转换，不接电机；解压[LAB_ONLY台架包](../lab/task7_8_lab_only_20260919.zip)，先运行`python3 lab_acceptance.py contract`，再按[无电机验收](../fpga/board/no_motor_acceptance.md)执行。未完成前不要解除`--release`门禁。

## 工单与证据

| 项目 | 状态 | 权威证据 |
|---|---|---|
| 历史任务1—4 | PASS候选 | `acceptance_20260918/任务1-4验收与修改报告.md` |
| 夜间A | PASS（PC模型/RTL/OOC） | `night_20260918_A.md` |
| 夜间B | PASS（软件参考/RTL/OOC） | `night_20260918_B.md` |
| 夜间C | PASS（集成/可重建工程/OOC） | `night_20260918_C.md` |
| 夜间D | PARTIAL（PC闭环PASS） | `night_20260918_D.md`；真实PYNQ MMIO未验证 |
| 夜间E | PASS（静态/实现）；release BLOCKED | `night_20260918_E.md`；实物电气和无电机板测未执行 |
| 任务7/8集成候选 | 当前环境PASS、实板PARTIAL | 生产感知核与OSD已接入；HWH PASS；完全布线WNS +0.079ns/WHS +0.027ns；D实板和release门禁阻断 |
| LAB_ONLY台架载荷 | READY_FOR_HARDWARE | bit/hwh、哈希manifest、板端脚本与ZIP已生成；解压后契约复验PASS；不允许电机输出或发布 |

最终全量证据目录为`acceptance_20260918/run_20260919_102658/`。该轮在E/7/8集成后重建真实C DLL，20项链路、35项主机、十套RTL仿真和像素比对全部通过；六个OOC模块WNS均非负，最紧路径为OSD +0.981ns。完整集成实现报告位于`../fpga/build/task7_8_integrated/`，release预期失败由`validate_board_manifest.py --release`复核。

## 待人工确认

- 实物PYNQ-Z2修订版是否与`pynq-z2资料/`中的PA_v3/R12/XDC/board files对应。
- 红外和编码器输出究竟为3.3V推挽、5V推挽还是开漏；上拉电压及电平转换必须实测。
- 输出轮真实CPR与轮径标定值；当前生产scale复位为0，未标定即无效。
- 网页若要复用PL叠加画面，是否接受增加S2MM回采与缓存同步；当前任务8只完成到物理HDMI候选出口。
- OSD锁存图标是否需要新增STM32真实锁存状态回传；当前集成候选明确显示PL `risk_stop`代理。

## PYNQ缺席期间的完成边界

截至2026-09-19，本机未检测到PYNQ或可用板端网络，因此不能执行Overlay加载、真实MMIO/epoch、传感器输入、UART STOP时延、VDMA/HDMI、C270吞吐和30分钟稳定性。上述项目全部保留为未验证；编码器电机不影响这些无电机验收，QEI输入继续断开并允许`valid=false`。台架包交接见[LAB_ONLY_台架包交接_20260919.md](LAB_ONLY_台架包交接_20260919.md)。
