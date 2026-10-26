# 完整传感器联调上位机 r4 软件验证

日期：2026-10-25

交付物：

- 运行目录：`pynq_fpga/release/v010_sensor_console_20261025_r4/`
- 下载包：`pynq_fpga/release/v010_sensor_console_20261025_r4.zip`
- 包 SHA-256：`8db26013561a0926b9df9532e103a4c015abed5fd1c06405d936706b57f69cf1`
- 候选记录：`pynq_fpga/preintegration/sensor_console_candidate.json`

本轮只修改主机/PS 页面和实时状态消费者，复用 r3 已验证的 bit/HWH 与 STM32 固件：

- bit SHA-256：`d3287345221c56d0f0c120508ef1bc54771eeedd7b85050e50906c3ff282d7ad`
- HWH SHA-256：`b0b2aeaee963cfc4f018c18ce1d68b9dc96a6d74b3cf02b3e6ac43015af4e81d`
- STM32 BIN SHA-256：`8b043a342c839414f021bbd68700ddfac48113509577872ace9074bb806f4f2d`

## 功能改动

- hybrid-v3 链路新增线程安全诊断：查询/回包计数、回包年龄、往返时间、协议错误、传输错误和 S1 传感器快照。
- 完整页面新增超声波、左右红外、QEI0/QEI1、LOCK/PWM/FAULT/drop 和 STM32 串口状态。
- 新增可重置的完整互联统计。通过条件包括视频、STM32 回包、超声波、左右红外分别遮挡/移开、锁车零 PWM 和双轮编码器计数。
- 新增 `/api/sensor-test/reset`，重置只改观察统计，不写硬件、不刷新控制租约。
- 新增 `start_sensor_console.sh`，默认启动完整视频、PL、STM32 UART、无线页面和证据记录。

## 已执行检查

| 检查 | 结果 |
|---|---|
| `python -m unittest discover -s pynq_fpga/preintegration/tests -p "test_*.py"` | 162 项 PASS |
| STM32 `test_hybrid_link.py` | PASS |
| 页面内联 JavaScript 语法 | PASS |
| 桌面视口 1440×1000 | 无横向溢出，16 个状态卡片、14 项联调检查完整渲染 |
| 移动视口 390×844 | 无横向溢出，视频宽度 332px，状态卡片和检查列表正常换行 |
| `lab_acceptance.py contract` | PASS，契约 `0xC425100A` |
| `verify_wireless(...)` | PASS |
| portable ZIP 内容与 manifest 哈希 | PASS，86 个文件 |

截图：

- `work/sensor_console_20261025/desktop.png`
- `work/sensor_console_20261025/mobile.png`

## 验证边界

本轮没有烧录、加载 Overlay、打开实板 UART 或操作电机。`lab_manifest.json` 和候选记录均保持 `hardware_result: PENDING`。实板通过条件由使用者在页面完成；页面通过也不改变 LAB_ONLY 零输出分类，不构成标定、制动、电池长稳或整车 release 验收。
