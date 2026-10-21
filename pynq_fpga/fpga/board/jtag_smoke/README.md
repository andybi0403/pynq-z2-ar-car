# PYNQ-Z2 无 SD 卡 JTAG 板卡测试

此工程仅使用板载 SW0/SW1、BTN0/BTN1 和 LD0—LD3。SW0→LD0、SW1→LD1、BTN0→LD2、BTN1→LD3。不需要 PYNQ Linux、外接线或电机。

使用 Vivado 2026.1 在本目录运行 `build.tcl`，生成 `output/led_switch.bit`。将板子的启动跳线设为 JTAG，正确设置供电跳线，电脑用 Micro-USB 数据线连接 PROG/UART，开机后在 Vivado Hardware Manager 中连接目标设备并下载此 bit 文件。下载后拨动开关、按住按钮，观察对应 LED。断电后配置消失。

此测试仅证明 JTAG 下载及板载 PL I/O 工作，不证明 PS、SD 启动、网线、USB 摄像头或项目 LAB_ONLY 工程已通过。
