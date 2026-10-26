# 当前状态（2026-09-19，v0.6主架构 + 夜间A—E与任务7/8集成候选）

| 工作项 | 状态 | 当前证据/入口 |
|---|---|---|
| 历史任务1 固件/通信 | 模块PASS；夜间A已补PC跨层时限模型 | `acceptance_20260918/任务1-4验收与修改报告.md`、`night_20260918_A.md` |
| 历史任务2 接口/快照 | PASS，104项 | v0.5验证包装层继续回归 |
| 历史任务3 US/IR | PASS，43项 | 60/30ms采集预算与配置锁存 |
| 历史任务4 双QEI/测速 | PASS候选，155项 | `task_4_result.md` |
| v0.6统一感知顶层 | 架构与仿真PASS候选 | `car_perception_top.v`；33项；单时基/单AXI/全局快照 |
| v0.6 PL风险核 | 架构、仿真与OOC PASS候选 | `car_risk_core.v`；31项；QEI双路过期与IR stable变异均可检出；100MHz WNS +3.217ns |
| 夜间A 安全闭环 | PASS（PC模型/RTL/OOC） | 真实对接版C DLL；17项链路单测+16项跨层；源切换废弃旧快照；未上板 |
| v0.6 AXIS OSD | 夜间B PASS候选 | 数字/负号/独立无效显示；1326项基础+114695项随机流+614400项全帧；WNS +0.981ns |
| 夜间B OSD增量 | PASS（软件/RTL/OOC） | 七场景逐像素一致；640×480共307200像素一致；`night_20260918_B.md`；未上板/HDMI |
| 夜间C 统一工程 | PASS（E/7/8集成及第三轮审计收口后复验） | `run_20260919_161918`全门禁通过；十套RTL仿真、六模块OOC WNS非负；未上板 |
| 夜间D PS驱动/回放 | PARTIAL（PC闭环复验PASS） | 跨层IR语义、严格JSONL和MMIO边界已修；38项主机+完整综合门禁通过；真实PYNQ MMIO未测试，`night_20260918_D.md` |
| v0.6寄存器源 | PASS | `register_map.json`生成Verilog/Python/Markdown三份 |
| v0.6 Vivado工程 | 可重建、可打开 | `fpga/build/car_architecture_v0_6/car_architecture_v0_6.xpr`；仅PL RTL候选 |
| PS主机客户端 | PC闭环PASS，板上PARTIAL | `perception_client.py`/`perception_replay.py`；38项主机总测试；PYNQ MMIO未实测 |
| 夜间E 板级约束 | PASS（静态/实现）；release BLOCKED | 22端口manifest（含QEI `/OE`的JA9/W18）、双来源管脚证据、电气审查与无电机步骤；实物与外设电平未验证，`night_20260918_E.md` |
| 任务7 PYNQ控制工程集成候选 | PC/Vivado PASS、实板PARTIAL | 生产核集成；LAB_ONLY bit/hwh与一键验收包已生成；真实Overlay/MMIO仍待PYNQ到手 |
| 任务8 摄像头与HDMI链路集成候选 | PC/Vivado PASS、实板PARTIAL | 生产OSD已接入；LAB_ONLY包含色条/C270入口；物理画面、颜色和性能未验证 |
| 双前轮编码器修订 | 软件/实现PASS、实物PARTIAL | 1:48、2496计数/圈；临时SCALE 5362；J7 pin4 5V与JA9 `/OE`已落地；61+21项测试、实现WNS +0.383ns；`ENCODER_MOTOR_CODEX_REVIEW_20260920.md` |

执行顺序：A安全闭环（PASS）→B流式OSD（PASS）→C统一集成（PASS）→D PS驱动/回放（PC闭环PASS、板上PARTIAL）→E板级静态验收（PASS、release阻塞）→任务7/8集成候选（当前环境PASS）。主架构和各任务允许修改边界见`主架构_v0.6.md`，后续开发不得另建第二套顶层、风险核、OSD、寄存器表或驱动。

唯一统一接口：`interface_contract.md` v0.6；统一ID为`0xC4251006`。旧ID `0xC4250105/0205/0405`只属于三个验证包装层。

统一回归：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1 -Synthesis
```

当前任务7/8证据已包含PS/DDR/VDMA/HDMI候选Block Design、生产感知核与OSD、HWH、综合和完全布线实现，并生成LAB_ONLY非发布bitstream；仍没有实物上板或真实停止时延。`validate_board_manifest.py --release`必须在电气与实物证据缺失时失败。

任务7/8的隔离基线证据见`任务7-8预集成框架交接_20260918.md`；最新集成证据见`night_20260918_E.md`与`preintegration/manifests/integrated_verification_20260919.json`。占位槽已在独立候选工程中替换，发布bitstream仍由D实板证据和E release门禁阻止。
