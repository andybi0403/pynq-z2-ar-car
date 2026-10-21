# full_traceability_matrix：竞赛要求→架构→代码→测试→综合/实现→实物待办

日期：2026-09-19（round4最终审查）。✅=六链闭合；🟡=离线已证/实物待验；⛔=未覆盖（明确不做）。

## 1. 感知与实时（PL不可替代任务）

| 竞赛要求 | 架构/代码 | 测试 | 综合/实现 | 实物 |
|---|---|---|---|---|
| 超声波测距（Trig/Echo、超时、卡高、无回波） | `car_ultrasonic.v`（同步器、两级等待、K=7365869定点） | tb_car_sensors 43项；参数锁存不中帧 | OOC WNS +2.696 | 🟡 HARDWARE_PENDING（正常/fault1/fault2场景） |
| 红外双路（低有效、滤波、stable/mask） | `car_ir.v`（IR_TS为变化时间戳，DEF-D-01修正） | tb 43项+风险核IR用例 | 同上 | 🟡（IR 0/1/2/3场景） |
| 双路QEI+周期法测速 | `car_qei.v/car_qei_velocity.v`（格雷x4、非法重同步、64拍除法、Q16.16饱和） | tb_car_qei 31+velocity 124 | WNS +2.367 | 🟡（CPR/相序/SCALE标定，生产SCALE=0） |
| 64位时基/全局快照/独立sample_ts/seq/valid | `car_time_counter.v`+`car_perception_top.v`单屏障锁存24影子 | tb_perception 33项（round4新增R1/R2变异KILLED证明组完整性与epoch语义） | WNS +2.367 | 🟡（epoch/撕裂上板步骤9） |
| PL风险融合（四级流水、原因位、失效即停） | `car_risk_core.v`（布局reason[31:16]/res[15:3]/level[2:1]/stop[0]，基线0x00020007） | tb 31项（round3后）；M1-M11全KILLED | WNS +3.217 | 🟡（RISK_CMD写者接线HARDWARE_PENDING） |
| 流式OSD（纯AXIS、SOF提交、背压保持） | `car_axis_osd.v`+自制font mem（单源） | 1326+114695+614400检查；7×8192+307200px逐像素 | WNS +0.981；386 LUT | 🟡（物理画面/色序人工确认） |

## 2. 通信与执行安全（STM32最终锁存）

| 要求 | 代码 | 测试 | 实物 |
|---|---|---|---|
| $P帧（校验范围'$'..N、P1-1位置绑定、±2400限幅、MMM≤9999） | `safe_control.c:126-191` | C单测+13万fuzz+round4边界电池15/15 | 🟡 实链路 |
| 200ms数据龄/250ms租约/300ms解锁/1000ms USB回切（无符号回绕安全） | `safe_control.c:28-55` | 边界用例（恰阈值/回绕）+DLL矩阵 | 🟡 实测时延 |
| 源切换立即废弃快照（AUD-02-01修复） | `safe_source_handover()`两方向调用 | 9时间线矩阵+D1-D4 KILLED | 🟡 |
| 距离回差只屏蔽正向/IR锁存/TB6612真值表 | `safe_tick/safe_outputs/brake/channel` | C单测+DLL | 🟡（电机断开验收步骤1-12） |
| 看门狗/上电锁存/启动文件向量表 | `safe_car_init/safe_startup.c`（SysTick+USART1/2向量，其余→safe_panic） | 构建唯一源断言 | 🟡 |

## 3. 集成与视频

| 要求 | 代码/工程 | 证据 | 实物 |
|---|---|---|---|
| 单PS/单AXI从机/单时基（无第二套） | `car_board_video_wrapper`（HWH审计+架构不变量测试4项） | HWH契约PASS、占位核拒绝 | 🟡 |
| C270→DDR→VDMA MM2S→32/24适配→OSD→VTC→RGB2DVI→HDMI | `create_integrated_candidate.tcl`（中断/HPDN/UART EMIO） | 完全布线WNS +0.079/WHS +0.027/DRC 0阻断 | 🟡（900帧/色序/HPDN IRQ） |
| 带宽核算 | BGR0 4字节：640×480@30=36.864MB/s单遍；4次搬运预算147.456MB/s（`video_contract.py`公式+测试）；有效像素3字节=27.648MB/s仅用于说明，DDR按4字节对齐缓冲计——无重复/漏算 | Python契约测试 | 🟡 实测HP0 |
| 三缓冲所有权/帧新鲜度 | `frame_pipeline.py` TripleBufferQueue+FrameFreshnessGuard | 框架测试 | 🟡 |

## 4. 交付供应链

| 项 | 证据 |
|---|---|
| LAB_ONLY ZIP=`fd813fdb…`三方一致、15项、无缓存、脚本逐字节同、bit/hwh哈希匹配 | round3+round4复测（11类篡改全拒） |
| 七阶段台架（contract/mmio/sensor-check/uart-stop/safety-loop/color-bars/camera） | 缺PYNQ非零退出；fake transport 1通过+4拒绝；RISK_CMD基线文档化 |
| release门禁 | `--release` exit 1（10外接信号电气+板卡修订版未确认）——正确阻塞 |

## 5. 明确不做（⛔）

检测类DPU/人脸检测（07报告范围外）；`$CAR` V0.7单边修改；OSD改风险物理口径；放宽200ms；解除release门禁。
