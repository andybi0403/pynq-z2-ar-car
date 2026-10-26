# 完整传感器联调台

该入口启动正式无线视频、PYNQ MMIO、STM32 hybrid-v3 UART 和浏览器联调页面。电机动力必须物理断开，页面保持零输出台架模式。

```sh
chmod +x start_sensor_console.sh
./start_sensor_console.sh
```

默认运行 1800 秒并创建新的 `evidence/sensor_console_<UTC时间>` 目录。可用环境变量：

```sh
SENSOR_CONSOLE_DURATION=1800 \
SENSOR_CONSOLE_VIDEO_MODE=auto \
SENSOR_CONSOLE_EVIDENCE=evidence/full_sensor_run \
./start_sensor_console.sh
```

终端会打印带本次随机令牌的浏览器地址。页面同时显示：

- 摄像头与真实 PL 处理画面；
- STM32 hybrid-v3 查询/回包计数、回包年龄、延迟和协议错误；
- 超声波距离与左右红外状态；
- QEI0/QEI1 编码器原始序号、有效性和速度寄存器；
- STM32 实际 LOCK、PWM、FAULT、drop；
- 可重置的完整联调统计。

联调通过要求至少持续 10 秒，并观察视频、STM32 回包、超声波、左右红外、锁车反馈和两个编码器通道。页面会明确提示需要遮挡哪一侧红外或手转哪个车轮。统计只来自本次实际回传，不使用请求值、缓存值或页面模拟数据。

该通过结论只覆盖当前会话的传感器互联。轮径标定、制动时延、HDMI 实屏、电池长稳和整车 release 仍需独立验收。
