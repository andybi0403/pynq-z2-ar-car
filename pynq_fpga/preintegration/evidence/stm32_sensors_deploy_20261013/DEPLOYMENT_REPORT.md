# PYNQ v0.10 实板部署记录

2026-10-13，STM32混合采集固件已烧录并完成读回及启动检查后，更新PYNQ。用户确认本轮STM32尚未接至PYNQ，因此不声明板间UART或传感器联合实测通过。

## 已完成

- 通过Windows COM14／PYNQ调试UART部署，没有更改电脑Wi-Fi或板卡网络。
- 板端目录：`/home/xilinx/stm32_sensors_v010_20261013_r3`。完整53个文件逐项SHA256匹配本地已通过完整流水线的候选；旧v0.9包保留。
- ARM视频库重编译通过，并实际加载核验ABI：`car-video/2;libjpeg-turbo/3.1.2`。
- 新bit/HWH加载及地址结构核对通过，实际MMIO接口ID为 `0xC425100A`。
- 使用现有Linux UART1节点 `/axi/serial@e0001000` 的设备树覆盖启用应用串口。实际驱动绑定 `/dev/ttyPS1`，寄存器地址 `0xe0001000`；原UART0调试控制台保持。
- DTBO由本机AMD Vitis的DTC v1.7.0+编译，DTB→DTS反向核验通过。覆盖只调整UART1状态和serial1别名，沿用既有时钟、中断和地址。驱动因动态别名未进入启动别名表而使用第一个空闲编号，实际得到ttyPS1。内核提示移除覆盖时可能泄漏属性内存；日志完整保留，入口检查已应用状态，避免重复插入。
- 共同时基短时读计数估算约99.9MHz，符合100MHz配置；这是200ms软件观察，不作为频率标定。

## 当前安全状态与范围

`EXT_SENSOR_MODE=1`，`EXT_SENSOR_STATUS=1`：选择STM32源，US/IR有效位均撤销。双轮SCALE为0，RISK_ENABLE为0，未发送释放或非零驾驶帧。

12秒串口观察记录223个PL快照，发送194个Q1与195个PSTOP，接收0字节。此检查未通过回传判据；用户随后确认“没接stm32”，保留原始失败结果，不将其写成通信成功。预检时未检测到摄像头，网口无物理链路；未启动浏览器视频或进行联合运行。

## 板端使用入口

平台目录：`/home/xilinx/stm32_sensors_platform_20261013`。程序、DTS和DTBO已保存在SD文件系统。

重启后，准备匹配的Overlay与UART1：

```sh
sudo env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 /home/xilinx/stm32_sensors_platform_20261013/prepare_hybrid.py
```

完整运行入口：`/home/xilinx/stm32_sensors_platform_20261013/start_hybrid.sh`，透传原运行器参数，保留电机断开、标定、传感器就绪与摄像头要求；没有配置开机自动运动或自动运行。入口调用准备脚本的 `--enable-risk-evaluation`，先撤销命令与轮尺度，再启用风险计算；此选项已在板端实际执行核验，随后恢复空闲RISK_ENABLE=0。单独准备命令默认保持风险禁用。没有满足外设和就绪条件时，不使用假样本或名义标定绕过检查。

后续板间接线（2026-10-14勘误，原K1两针写反）：PYNQ JB9 TX→底盘K1.3→S5接通2–3→STM32 PA3/RX；JB10 RX←K1.4←PA2/TX；K1.2与PYNQ共地。K1.1不接，蓝牙模块拔下，STM32需正常供电，BOOT0保持0。编码器继续保留既有PCB→PYNQ连接；原始部署观察日志不改写。

## 同源证据

- `stm32_sensors_v010_20261013_r3.json`：部署回执及53个文件哈希。
- `overlay_uart_activation_r2.json`：实际Overlay、ID、UART1驱动与地址核对。
- `deployment_complete_r2.json`：最终板端入口、启动选项实际执行、库ABI、寄存器最终状态及哈希；无后缀版本是入口修订前记录。
- `uart_bridge_summary.json`、`board_bridge_samples.jsonl`：未连接STM32时的真实观察结果。
- `pynq_car_uart1.dts`、`pynq_car_uart1.dtbo`：额外板端平台配置；没有更改不可变候选包。

bit SHA256：`cd7847bb47034f142c073d0f0a95e19eb23979b652265f1cec2448478f4be635`。

HWH SHA256：`f5e10d4e22463fa0f6f2f011575708c2e62b77652113c3e91893e77baeb08067`。

DTBO SHA256：`08b08a51bcc82ef50473764bb1bef7048e8b2a1fbf9f8704763161616c8cbac2`。

平台操作依据：[PYNQ DeviceTreeSegment接口](https://pynq.readthedocs.io/en/v2.6.1/pynq_package/pynq.devicetree.html)、[Cadence UART绑定](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/refs/heads/master/Documentation/devicetree/bindings/serial/cdns%2Cuart.yaml)。实际节点路径、时钟、中断和驱动状态以本轮板端检查为准。
