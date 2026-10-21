# PYNQ-Z2 首次烧录与启动（2026-09-27 核对）

本项目使用官方 PYNQ Linux 镜像启动，再用 Python 加载项目 Overlay。
首次验证系统启动不需要先打开 Vivado，也不需要先下载项目 bitstream 或自己制作 BOOT.bin。

## 1. 写 TF 卡

1. 板子断电，取出 TF 卡，用读卡器接电脑；备份卡中需要保留的内容。
2. 官方板卡页面当前提供 PYNQ-Z2 v3.1.1。电脑已有解压后的镜像：
   `C:\Users\39909\Desktop\FPGA\pynq-z2资料\系统镜像\pynq_z2_v3.1.1.img`。
3. 用 Win32DiskImager（官方 Windows 教程采用的工具）或 balenaEtcher 写入整卡镜像。
   选择上述 `.img`，核对 TF 卡容量与设备后写入；不是将 `.img` 复制到卡内。
   现有卡约 32GB，但每次仍须重新核对设备，不能依赖旧盘符。
4. 等待写入完成并进行读回校验。Windows 若询问格式化 Linux 分区，取消。
5. 安全弹出后，再把卡插回板子。

## 2. 断电设置与上电

- BOOT 跳线选 SD；按板上丝印和官方连接图确认，不按照片的左右方向猜。
- Micro USB 供电时电源跳线选 USB，接 PROG–UART 口；使用合适的外接 12V 稳压电源时选 REG。
- 初次只接电源、TF 卡和网线。项目实测阶段保持电机物理断开。
- 打开电源，等待约 1～2 分钟。记录电源灯、DONE 灯和用户 LED 的变化。
  红色电源灯只说明已经有供电，不能单独证明 Linux 启动成功。

官方连接图与启动指示说明：
https://pynq.readthedocs.io/en/v3.1/getting_started/pynq_z2_setup.html

## 3. 电脑直连

网线连接板子和电脑。如果 Windows 有线网卡仍显示“网络电缆被拔出”，先排查供电、启动、线缆与端口。
链路建立后，在这块有线网卡的 IPv4 属性中设置：IP `192.168.2.10`，掩码 `255.255.255.0`，网关和 DNS 留空。
浏览器访问 `http://192.168.2.99`，默认登录用户名/密码均为 `xilinx`。
如果使用路由器 DHCP，应从路由器查看板子实际 IP，不套用直连地址。

打开 Jupyter 后先运行官方入门示例，确认基础系统工作，再上传本项目测试包。
USB 的未知设备/JTAG 枚举问题与 SD 写入是不同步骤；不要把 Vivado 中 localhost Connected 当作板卡连接成功。

## 4. 加载本项目

把修复后测试 ZIP 上传到 Jupyter 初始目录，打开 Terminal，进入 ZIP 所在目录并解压。
在解压目录中依次运行：

```bash
python3 lab_acceptance.py contract
python3 lab_acceptance.py mmio --evidence-dir evidence
```

仅在确认电气连接、HDMI 显示器接入且电机断开后，继续 README 中的色条与摄像头测试。
`contract` 证明文件与接口契约匹配；`mmio` 通过才证明本次 Overlay 加载和寄存器交互通过。
Vivado 时序/DRC 通过不能替代真实 HDMI 画面与长期稳定性验证。

## 官方来源

- 当前 PYNQ-Z2 镜像： https://www.pynq.io/boards.html
- Windows 整卡写入： https://pynq.readthedocs.io/en/v3.1/appendix/sdcard.html
  （该通用页仍用 Z1 文件名举例，本板必须选择 Z2 镜像。）
- Z2 跳线、上电和连接： https://pynq.readthedocs.io/en/v3.1/getting_started/pynq_z2_setup.html

本文只整理步骤，没有在本次修复期间再次写卡或确认板端启动。
