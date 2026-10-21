# USART2 旁路测试

这个版本绕过底板 CH340，使用原蓝牙接口的 USART2：`PA2 = TX`、`PA3 = RX`，参数为 9600/8N1。它不启动任何电机 PWM、舵机或传感器，电机方向脚固定为停止电平。

接线方向：DAP 右侧 `TX → PA3`，DAP 右侧 `RX ← PA2`，DAP `GND → GND`。测试时必须拔下 `K1 BLUE/WIFI` 上的蓝牙模块，不能让 DAP 和蓝牙模块同时驱动 PA2/PA3。

构建脚本会生成 `build_minimal_uart2_test/minimal_uart2_test.hex`。烧录并运行后，DAP 虚拟串口应每 500 ms 收到 `$MINI2,OK,STOP#`。`mini2_error_count` 是 USART2 的硬件错误计数，可用 DAP 读取。

## 本次测试结果（2026-09-09）

- 固件写入和校验成功，运行约 3 秒发送 6 次，USART2 硬件错误计数为 0。
- DAP 虚拟串口 COM10 已实际收到连续 `$MINI2,OK,STOP#` 心跳，说明 DAP TX → PA3 接线和 9600 波特率正确。
- 电机方向脚始终为停止电平。正式切换前仍需确认 DAP RX → PA2 的回传方向；COM10 若被系统占用，先关闭占用串口的软件并重新插拔 DAP USB。
