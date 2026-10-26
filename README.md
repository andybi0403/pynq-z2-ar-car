# PYNQ-Z2 多传感器 AR 小车

**2026-10-26 最新交接：[接手先读](handoff/20261026/00_接手先读.md) · [通信故障与实测](handoff/20261026/02_通信故障时间线与复现.md) · [完整演示与验收](handoff/20261026/04_完整功能演示脚本与验收清单.md)。** 最新完整程序为 [r17b ZIP](pynq_fpga/release/v011_uart_recovery_20261026_r17b.zip)。STM32 已烧录并全片校验，PC COM10 查询 20/20；PYNQ 在 S5 ON/OFF 两次均 0/80，通信仍未恢复。板上 r16 服务已停止，r17b 尚未部署到 PYNQ；整车验收未完成。下文旧版本状态保留为历史，不覆盖本次交接。

[![validate](https://github.com/andybi0403/pynq-z2-ar-car/actions/workflows/validate.yml/badge.svg)](https://github.com/andybi0403/pynq-z2-ar-car/actions/workflows/validate.yml)

基于 PYNQ-Z2 / Zynq-7020、STM32F103C8T6 和 BST-4WD V4.5 底盘的低时延感知与显示系统。PL 负责统一时基、原子传感器快照、QEI 测速/里程、风险判定、视频帧关联、OSD 和无线视频 DMA；PS 负责设备、协议、控制监督、页面与证据链；STM32 负责电机 PWM 执行、锁车安全逻辑以及超声波/红外采集。

当前公开交付物是**电机动力断开的 LAB_ONLY 台架版本**，不是可驾驶的整车 release。已完成的实板范围包括 STM32 烧录与 128 KiB 独立读回、正常启动、锁车双板 UART、超声波/红外进入 PL，以及 PYNQ 重启后的 UART/Overlay 恢复。

## 当前版本

最新完整控制台软件为 [v0.11 / r16](pynq_fpga/release/v011_complete_console_20261026_r16/README.md)，[下载 ZIP](pynq_fpga/release/v011_complete_console_20261026_r16.zip)。整合视频、操控与实际反馈、传感器和双轮标定、记录回放与演示流程；红外触发、失效与断线只提示，不参与停车或解锁判断。连接助手拒绝旧受限试跑服务。新包包含重新构建且时序通过的 FPGA bit/HWH、配套 STM32 固件，并保存此前方案的左右 SCALE=5362 名义预设。153 项主机、187 项集成、35 项串口测试、29 个浏览器场景、22 个 RTL 测试台及完整构建通过；包与桌面源文件身份校验通过。**本包未联网部署、实板结果 PENDING**，不改变公开 LAB_ONLY 发布分类。详见 [验证记录](pynq_fpga/preintegration/validation/20261026_ir_advisory_console_r16.md) 和 [操作说明](tools/car_receiver/使用说明.md)。下表继续列出已验证的原实板基线。

| 项目 | 值 |
|---|---|
| 接口契约 | v0.10 / `0xC425100A` |
| 板卡 | PYNQ-Z2，`xc7z020clg400-1` |
| 完整 PL 构建候选 | `v010_edge_console_20261014_r2` |
| 当前实板锁车基线 | `v010_uart_role_fix_20261014_r3` |
| 工作包 | [`v010_uart_role_fix_20261014_r3.zip`](pynq_fpga/release/v010_uart_role_fix_20261014_r3.zip) |
| 工作包 SHA-256 | `12d0c5796bb00af5c37f477752c60a010eb84698b05428d2f4c0e361b79f9acf` |
| bit SHA-256 | `d3287345221c56d0f0c120508ef1bc54771eeedd7b85050e50906c3ff282d7ad` |
| HWH SHA-256 | `b0b2aeaee963cfc4f018c18ce1d68b9dc96a6d74b3cf02b3e6ac43015af4e81d` |
| STM32 BIN SHA-256 | `8b043a342c839414f021bbd68700ddfac48113509577872ace9074bb806f4f2d` |
| 发布状态 | `LAB_ONLY_NO_MOTOR_NON_RELEASE` |
| 整车验收 | `NOT_CLAIMED` |

机器可读的当前发布记录见 [`release_manifest.json`](release_manifest.json)。其中明确区分两个阶段：

- `r2` 是从当前 v0.10 RTL 经过完整回归、综合、布局布线、时序、DRC、HWH 与同源打包得到的 PL 构建候选。
- `r3` 复用完全相同的 bit/HWH，只修复 STM32 UART 数据口选择、PYNQ 首个有效样本和管理控制台烧录流程；其运行文件与实板证据单独绑定。

## 系统结构

```text
USB C270 ──USB──> PYNQ PS ──V4L2/MJPEG──> VDMA / AXI4-Stream
                                      │
STM32F103 ──UART 115200──> PS UART1 ──> EXT_SENSOR_MODE=1 ──> PL 传感器注入
                                      │
双霍尔编码器 ──电平转换PCB──> PYNQ Pmod ──> QEI / 测速 / 里程
                                      │
                                      v
                       统一快照 + 风险核 + 视频帧关联 + OSD
                                      │
                         HDMI / 无线浏览器状态页 / 证据日志
```

核心设计不变量：

- 数据、有效位、时间戳和序号同批更新；心跳不能刷新传感器新鲜度或驾驶意图。
- PL 使用一个公共 100 MHz 时基、一个 AXI-Lite 地址空间和一次全局原子快照。
- 历史视频状态不得参与当前控制；显示的实际执行器反馈不能由请求值或 PL STOP 代替。
- 电机释放与标定门禁独立；`SCALE=0`、传感器无效或命令失效时保持锁车。
- bit/HWH、契约、STM32 固件和运行 Python 文件必须来自同一发布记录。

## 快速开始

```bash
git clone https://github.com/andybi0403/pynq-z2-ar-car.git
cd pynq-z2-ar-car
```

### 1. 使用已打包运行文件

将 `pynq_fpga/release/v010_uart_role_fix_20261014_r3.zip` 解压到 PYNQ，例如：

```bash
cd ~/v010_uart_role_fix_20261014_r3
python3 deployment_check.py --board
python3 lab_acceptance.py contract
```

包内 [`HYBRID_SETUP.md`](pynq_fpga/release/v010_uart_role_fix_20261014_r3/HYBRID_SETUP.md) 给出 UART、超声波、红外和编码器接线摘要。执行任何测试前必须物理断开电机动力线。

### 2. 烧录 STM32

当前锁车基线使用包内 `stm32_hybrid_v3.hex`。烧录需要 BOOT0=1 后复位、PYNQ 调试串口和电机动力断开；烧录完成后恢复 BOOT0=0 并复位。

```powershell
python work/uart_live_fix_20261014/upload_flash_via_pynq_console.py --authenticate
```

密码只在本地终端隐藏输入，不写入仓库。工具会先读取当前 Flash，只有匹配已知安全基线或已验证目标身份时才允许擦除。

### 3. 启动台架运行

先只做只读检查：

```bash
python3 lab_acceptance.py mmio --evidence-dir evidence
python3 lab_acceptance.py sensor-check --label normal --count 10 \
  --expect-us-valid 1 --expect-us-fault 0 --distance-min 250 --distance-max 2000 \
  --expect-ir-valid 1 --expect-ir-stable 1 --expect-ir-mask 0 \
  --evidence-dir evidence
```

需要网页状态与视频时，使用包内 `startup/start_hybrid.sh` 或按包内 README 启动。当前没有配置成开机自启动服务。

## 构建与验证

环境基线：

- Vivado 2026.1
- Python 3.10 及以上；本机回归使用 Python 3.14
- ARM GNU Toolchain、Visual Studio 2022 C++ Build Tools
- Node.js
- PYNQ 3.1.1 / PYNQ 2.7 均保留过实板排查记录，当前锁定包以实际板端部署记录为准

### 完整 PL 构建

```powershell
python pynq_fpga/fpga/registers/generate_register_map.py --check
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/build_complete.ps1
```

每次构建使用新目录，成功后才更新 `pynq_fpga/preintegration/latest_candidate.json`。完整入口见 [`COMPLETE_BUILD.md`](pynq_fpga/preintegration/COMPLETE_BUILD.md)。

### 软件、固件与 RTL 回归

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/run_software_round.ps1 -Round 5
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/fpga/scripts/run_acceptance.ps1
```

### 发布一致性检查

```powershell
python skill/amd-pynq-project-workflow/scripts/inspect_release.py --project-root .
python skill/amd-pynq-project-workflow/scripts/inspect_candidate.py --project-root . --candidate pynq_fpga/preintegration/portable_r2/latest_candidate.json --skip-current-sources
python -m unittest discover -s skill/amd-pynq-project-workflow/scripts -p "test_*.py" -v
```

这些检查只证明文件、哈希和已记录证据的一致性，不替代 Vivado、电气测量或实板验收。

## 验证状态

| 层级 | 结果 | 证据 |
|---|---|---|
| v0.10 完整 PL 候选 | 回归、综合、完全布线、时序、DRC、HWH、ZIP 均 PASS | `pynq_fpga/preintegration/evidence/complete_v010_edge_console_20261014_r2/` |
| 时序 | WNS `+0.372 ns`，WHS `+0.015 ns` | 候选 manifest 与 timing report |
| 2026-10-21 软件回归 | 两套 C、7 项 ARM、28 项 PC、150 项主机、161 项预集成、15 个故障场景 PASS | `validation/20261021_software_rtl_validation.md` |
| 2026-10-21 RTL 回归 | 20 个自检测试 PASS，四组 OSD/视频链像素比对零差异 | `pynq_fpga/nightly/acceptance_20260918/run_20261021_234039/` |
| 实板锁车通信 | 烧录读回、正常启动、Q1/PSTOP、US/IR 入 PL、重启恢复 PASS | `work/uart_live_fix_20261014/completion_audit.json` |
| QEI 实板输入 | 原始输入仍有异常计数/非法跳变，控制门禁保持无效 | `pynq_fpga/preintegration/evidence/qei_retest_20261012/` |
| 电机连接、标定、制动时延、HDMI 色序 | 尚未验收 | 保持 PENDING |
| 1800 秒整车联合验收 | 尚未完成 | 不得宣称 release |

## 目录

```text
.
├─ docs/                        方案、进度、接线、选型与竞赛资料
├─ pynq_fpga/
│  ├─ fpga/                     RTL、TB、寄存器、约束、脚本、板卡定义
│  ├─ host/                     PS 感知、控制监督、标定与测试
│  ├─ preintegration/           构建入口、当前候选、运行/视频/证据代码
│  ├─ release/                  当前可下载的 r3 运行包
│  ├─ third_party/              固定版本的开源依赖与许可证
│  └─ audit/                    关键独立审查记录
├─ stm32_pynq对接版/            当前权威 STM32 固件与测试
├─ stm32预备程序/               历史演示、烧录与 PC 串口工具
├─ work/                        实板排查、UART/编码器/电池专项证据
├─ validation/                  当前源码回归与发布一致性结果
├─ skill/                       可复用 AMD / PYNQ 项目制作 skill
├─ release_manifest.json        当前发布、候选、源码补丁和硬件证据索引
└─ README.md
```

## 接线与硬件

- [STM32 传感器采集与 PYNQ 编码器方案](docs/03_硬件与接线/16_STM32传感器采集与PYNQ编码器方案_20261013.md)
- [UART 接线勘误与实板记录](docs/03_硬件与接线/17_UART接线勘误与实测_20261014.md)
- [BST-4WD V4.5 与 PYNQ-Z2 改装说明](docs/03_硬件与接线/BST-4WD_V4.5与PYNQ-Z2硬件改装说明.md)
- [双前轮编码器电平转换 PCB 需求](docs/03_硬件与接线/12_双前轮编码器电平转换PCB设计需求_20260920.md)
- [实物 PCB 与整车接线矛盾审查](docs/03_硬件与接线/15_实物PCB与整车接线矛盾审查_20261013.md)
- [PYNQ-Z2 本地引脚资料](pynq-z2资料/)

关键规则：Pmod 电源脚不是 5 V 源；霍尔板 4.5-5 V 供电来自 Arduino POWER 头 J7 pin 4；SN74LVC245A 的 `/OE` 默认由 10 kΩ 上拉到 3.3 V，QEI 电气未验收时保持无效。

## Skill

[`skill/amd-pynq-project-workflow`](skill/amd-pynq-project-workflow/SKILL.md) 覆盖选题、硬件、RTL、PS、视频、安全闭环、证据构建、发布检查和复盘。2026-10-21 新增“不可变候选 + 显式软件/MCU 补丁”审计，避免重写历史候选或把源码漂移当成通过。

## 已知限制

- 编码器原始输入仍有异常计数和非法跳变；当前只保留诊断和无效门禁，不用于控制。
- 没有完成电机连接下的行驶、实测 CPR、制动时延和物理停车验证。
- 没有完成 HDMI 实屏色序、摄像头长稳、超声波/红外故障矩阵和 1800 秒联合验收。
- 2026-10-21 的回归没有重新运行完整综合/布局布线；PL 构建结果以 r2 候选为准。
- `work/` 中的失败反例和修复前证据保留，不与最终通过样本合并或删除。

## 许可证

本项目原创代码采用 MIT License，见 [`LICENSE`](LICENSE)。固定版本第三方代码及资源保留各自许可证；采用关系、上游提交和修改范围见 [`pynq_fpga/OPEN_SOURCE_USAGE.md`](pynq_fpga/OPEN_SOURCE_USAGE.md) 与 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
