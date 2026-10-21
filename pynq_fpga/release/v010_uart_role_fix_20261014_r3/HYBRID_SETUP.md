# v0.10 接线与启动摘要

本文件只总结当前LAB_ONLY执行所需的电气连接。完整核对、实测记录和未决项以仓库
`docs/03_硬件与接线/16_STM32传感器采集与PYNQ编码器方案_20261013.md`及
`docs/03_硬件与接线/17_UART接线勘误与实测_20261014.md`为准。

## 连接

- PYNQ-Z2与STM32使用115200 8N1；运行链路使用PYNQ `PS UART1`，Linux设备名
  `/dev/ttyPS1`。PYNQ调试控制台仍是`PS UART0`，两者不可混用。
- 超声波、红外由STM32采集后经UART上报，PYNQ写入PL的`EXT_SENSOR_MODE=1`。
- 双前轮霍尔编码器保留PCB到PYNQ，A/B信号必须经过SN74LVC245A电平转换。
- 霍尔板4.5-5V供电接Arduino POWER头J7 pin 4；Pmod电源脚只有3.3V，不能作为5V源。
- SN74LVC245A的`/OE`由JA9/W18控制，外部10k上拉到3.3V；未完成电气检查时保持QEI无效。

## 启动

1. 物理断开电机动力线，确认BOOT0=0。
2. 将整个包目录放到PYNQ，例如`/home/xilinx/v010_uart_role_fix_20261014_r3`。
3. 运行`python3 deployment_check.py --board`，确认PYNQ、NumPy、pyserial、FFmpeg和设备路径。
4. 运行`python3 lab_acceptance.py contract`，再按README执行只读MMIO和传感器场景。
5. 需要重启恢复时，使用包内`startup/prepare_hybrid.py`加载Overlay并启用`/dev/ttyPS1`；
   `startup/start_hybrid.sh`是现有手动入口，不构成开机自启动服务。

## 禁止项

- 不连接电机动力运行。
- 不发送非零PWM、`$PREL#`或任何运动释放命令。
- 不将UART收到查询或STOP响应当成车轮已经物理停止。
- 不把本包的LAB_ONLY实板通过写成完整整车release。
