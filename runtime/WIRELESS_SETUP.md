# 普通电机首轮演示运行包

本目录是独立 v0.12 / 0xC425100C 运行程序。STM32 固件与 r17b 相同，不需要重刷。

- 保留真实距离、左右红外、视频与 PL 叠加、手动控制、实际 PWM/LOCK 反馈。
- 里程显示估算值；网页和视频均不显示速度，不出现未配备编码器的提示。
- 估算读取实际 STM32 PWM 回包，按相邻回包时间及 demo_mileage.json 中系数积分。仅供展示，不参与控制。
- PL 使用固定 250 mm 前向停车距离；没有动态测速制动模型。红外保持告警用途。
- 不需要编码器、绿色转接板或双轮标定。原编码器版在原目录保留。

首次将本包放在 /home/xilinx/v012_plain_motor_demo_20261028_r7，停止原 pynq-car-console.service 后：

```bash
cd /home/xilinx/v012_plain_motor_demo_20261028_r7
python3 deployment_check.py --board
cmake -S native -B native-build -DCMAKE_BUILD_TYPE=Release
cmake --build native-build --parallel 2
sudo env SENSOR_CONSOLE_MOTOR_MODE=disconnected sh start_console.sh
```

真实接入动力后改用 SENSOR_CONSOLE_MOTOR_MODE=connected；启动保持锁车。电脑打开 desktop/打开完整控制台.pyw，手动粘贴板端打印的链接与令牌。接管并显式解锁后才能按住方向键。松手、失焦、断链或意图过期停车。首轮 PWM 上限 400、连续按住最长 30 秒。

估算系数 mm_per_pwm_second 默认 0.25，代表人为假定 PWM 400 持续 1 秒估算 100 mm；不是电机规格或实测值。调整参数后必须重新生成包内 manifest。

本包已通过离线软件、真实 C、RTL、浏览器和整机 FPGA 构建；未上板，整车演示结果 PENDING。可选独立服务为 pynq-car-demo-plain.service，不覆盖原服务。两者不能同时占用 PL/UART。

2026-10-28：已取消运行方式选择，统一接管→安全解锁。旧模式接口返回 410，不能改变或撤销新页面的接管。短于 200ms 的调度抖动记录并重新安排采样；250ms 驾驶意图租约和传感器新鲜度保护保持生效。

2026-10-28 驾驶优先更新：默认 PWM=1800，范围400~2400（定时器周期7199），取消按住时长上限；松手/短暂失焦归零，显式急停与断联锁停，驾驶意图租约500ms。当前FPGA仍有250mm前向保护、STM32仍有200mm单超声波限前进/250mm释放门槛。10cm且双红外联合停车的候选固件及RTL已准备、未烧录，详见 pending_joint_stop_100mm。
