# PYNQ-Z2 摄像头接入方案与开源项目推荐

## 1. 最终推荐

本项目首版采用：

> **USB 2.0 UVC 摄像头 → PYNQ-Z2 的 USB Host → PS 端 OpenCV 采集 → DDR/视频帧缓存 → PL 端硬件 OSD → HDMI OUT 显示器**

摄像头硬件优先选 **罗技 C270**；如果后续发现体积不适合车体安装，再换成明确支持 Linux UVC、能够输出 640×480@30fps 的 USB 板载摄像头模块。

软件基线只采用 AMD/Xilinx 官方 [PYNQ](https://github.com/Xilinx/PYNQ) 仓库中的 PYNQ-Z2 Base Overlay 和 webcam/HDMI Notebook。不要从老项目直接复制 `.bit`、`.hwh` 文件。

## 2. 与竞赛方向三的对应关系

本项目对应《2026 东南大学第二十届 PLD 设计竞赛命题指南》题目二的 **方向三：多传感器采集在环与 AR/VR 特色显示**。

试题不是单纯要求把摄像头画面显示出来，而是要求形成：

```text
传感器/数据输入 → 实时处理 → 感知结果生成 → 显示输出
```

FPGA 不能只承担视频直通、接口转换或简单搬运。结合现有小车方案，各项基础要求按下表落实：

| 方向三基础要求 | 本项目的实现方式 | 摄像头在其中的作用 |
|---|---|---|
| 至少两类传感器实时采集与同步 | 摄像头、左右编码器、前向超声波，共三类；使用统一时间戳和有效期判断 | 提供实时道路背景帧，并记录帧号和进入 PL 视频流的时间 |
| FPGA 至少完成两项传感器数据处理 | PL 完成编码器速度/里程估计和超声波距离计算；风险融合也放在 PL | 不依赖 OpenCV 代替这两项硬件处理 |
| 至少一种 AR 叠加 | PL 在摄像头画面中叠加速度、距离、风险区和预警图标 | 摄像头提供被叠加的真实画面 |
| 车辆状态可视化 | 显示左右轮速度、累计里程、停车原因、传感器状态和简化俯视车辆标记 | 作为主显示背景，并与仪表信息同屏 |
| 报告说明关键架构 | 说明同步、融合、显示流水线、坐标系和资源占用 | 记录格式、帧率、帧时间戳、视频缓存和延迟 |

由此可见，**摄像头 + 编码器** 已经满足“至少两类传感器”；加入超声波后证据更完整。编码器测速/里程与超声波测距正好对应题目列举的 FPGA 处理功能，因此不需要把复杂目标检测或深度估计作为首版前置任务。

### 必须补强的同步证据

普通 USB 摄像头由 PS/Linux 接收，不能直接宣称已经实现硬件同步曝光。正式设计采用以下可验证方案：

1. 编码器和超声波数据由 PL 的统一计数器产生时间戳。
2. PS 取得一帧摄像头图像时记录帧号和接收时刻。
3. 视频通过 VDMA 进入 PL 后，在 AXI4-Stream 的帧起始位置锁存 PL 时间戳。
4. AR 显示使用与当前画面时间最接近的一组传感器快照，同时显示数据是否有效、是否过期。
5. 设计报告明确区分摄像头接收时刻、视频进入 PL 时刻和传感器测量时刻，不把 USB 摄像头描述成硬件触发同步摄像头。

这样可以对题目要求的“同步机制与时间戳方案”给出真实、可复现的工程证据。

### 关于分辨率和帧率

方向三的条文没有像方向一、方向二那样明确规定 640×480 和 25fps，但系统仍须实时、稳定、可量化。因此本项目把 **640×480、有效输入不低于 25fps** 定为团队验收指标，并记录：

- 摄像头有效输入帧率。
- HDMI 输出刷新率。
- 摄像头取帧到 HDMI 显示的端到端延迟。
- 丢帧数量和传感器数据年龄。

这些是团队为性能评估设置的指标，报告中不能写成方向三的原文硬性指标。

### 对评分细则的影响

摄像头方案应优先服务于基本指标的稳定得分，而不是盲目追求复杂视觉算法：

| 评分项 | 摄像头链路需要提供的证据 |
|---|---|
| 系统完整、主要功能 | 从 USB 摄像头输入，经实时处理和 AR 叠加，到 HDMI 输出的连续完整链路 |
| 性能评估 | 实测有效帧率、端到端延迟、丢帧、30 分钟稳定运行结果 |
| 操作界面 | 画面中清晰显示速度、距离、风险、模式、故障和数据新鲜度 |
| 优化与改进 | 对比纯软件叠加与 PL 流水线叠加的延迟、CPU 占用、资源占用或帧率 |
| 拓展灵活性 | 摄像头参数、风险阈值和显示模式可配置，UVC 摄像头可替换 |
| 实际应用性与演示效果 | 小车实景低速运行时画面稳定，预警与停车状态能够即时、直观地显示 |

所以最高优先级是“链路稳定 + 指标可测 + FPGA 作用清楚”。目标检测可以作为时间充足后的拓展，不应挤占编码器、超声波、同步、风险融合和 OSD 的实现时间。

## 3. OpenCV 在项目中的位置

OpenCV 适合本项目，但它不是整个 FPGA 视频方案。

OpenCV 在 PYNQ 的 PS（ARM/Linux）端负责：

- 打开 USB 摄像头。
- 设置分辨率、格式和帧率。
- 获取最新画面。
- 在开发早期验证画面、保存测试图和调试算法。
- 必要的颜色格式转换。

PL（FPGA）负责：

- 正式比赛版的实时 AR/OSD 叠加。
- 将速度、距离、风险等级、故障原因等信息叠加到视频流。
- 后续需要的硬件图像处理或加速。

因此不能把最终方案写成“OpenCV 在 Python 中画完所有文字，再由 FPGA 输出”。这种做法可以用于界面原型，但不足以证明 AR 叠加是在 FPGA 中完成的。

## 4. 推荐链路

```text
USB UVC 摄像头
    ↓ USB 2.0
Linux uvcvideo / V4L2 驱动
    ↓
OpenCV VideoCapture（PYNQ PS）
    ↓ BGR 图像，存入 DDR
PYNQ 视频帧缓存 / VDMA
    ↓ AXI4-Stream
自研 PL 硬件 OSD
    ↓
HDMI OUT → 场边显示器
```

USB 摄像头的数据不会直接进入 PL，而是先由 PS/Linux 接收并进入 DDR。随后仍然可以通过视频 DMA 把画面送入 PL，在硬件中完成正式叠加。

首版建议冻结为：

| 项目 | 首版设置 |
|---|---|
| 摄像头输入 | 640×480，目标 30fps |
| HDMI 输出 | 640×480，显示刷新率可为 60Hz |
| OpenCV 后端 | V4L2 |
| 对焦方式 | 固定焦或手动焦 |
| 视场角 | 普通广角，约 60°～90°，暂不选鱼眼 |
| 正式叠加 | PL 内的 AXI4-Stream OSD |

摄像头帧率和 HDMI 刷新率是两个指标。即使 HDMI 保持 60Hz，也可能只是在重复摄像头最后一帧，因此必须另外检测摄像头帧号或更新时间。

## 5. 摄像头硬件选择

### 5.1 第一选择：罗技 C270

选择理由：

- USB-A 接口，符合 PYNQ-Z2 的 USB Host 接入方式。
- 固定焦，车辆运动时不会频繁自动重新对焦。
- Linux 内核源码中可查到 Logitech HD Webcam C270 的设备记录，Linux 兼容性依据比普通无品牌摄像头更充分。
- 720p 是其上限能力，但本项目先使用 640×480，降低 PS、DDR 和视频链路压力。
- 型号常见，出现问题时更容易找到 Linux/UVC 使用经验。

官方资料：[Logitech C270 产品手册](https://www.logitech.com/assets/46735/6/hd-webcam-c270.pdf)；Linux 设备依据：[Linux USB quirks 源码](https://github.com/torvalds/linux/blob/master/drivers/usb/core/quirks.c)。

需要接受的缺点是：它比板载小摄像头体积大，车架上需要单独设计支架。

### 5.2 第二选择：USB UVC 板载摄像头

如果体积优先，可以选板载 USB 摄像头，但商品说明中必须明确写出：

- 支持 USB Video Class（UVC）。
- 支持 Linux/V4L2，不依赖厂商专用 Windows 驱动。
- 明确列出 640×480@30fps 的输出格式，优先同时支持 MJPEG 和 YUYV。
- 使用 USB 2.0 和 USB-A 接口，或配可靠的 USB-A 转接线。
- 镜头视场角和对焦距离适合室内小车。

不能只看“免驱摄像头”四个字；有些商品只保证 Windows 可用，没有公布 Linux 格式和帧率。

### 5.3 首版不推荐

| 方案 | 不作为首版的原因 |
|---|---|
| MIPI CSI 摄像头 | PYNQ-Z2 没有树莓派式 CSI 摄像头接口 |
| OV7670/OV5640 并口接 Pmod | 占用引脚多，时序、缓存和驱动工作量大 |
| 模拟摄像头＋USB 采集卡 | 多一层转换，延迟和 Linux 兼容性更难控制 |
| HDMI 摄像机接 HDMI IN | 体积、供电和安装更复杂，不适合当前低成本首版 |
| 无品牌且不公布 UVC 格式的摄像头 | 无法在购买前判断 Linux/PYNQ 兼容性 |

## 6. GitHub 开源项目优先级

| 优先级 | 项目 | 与本项目的关系 | 使用结论 |
|---:|---|---|---|
| 1 | [Xilinx/PYNQ](https://github.com/Xilinx/PYNQ) | 官方 PYNQ-Z2 Base Overlay、USB webcam、OpenCV、HDMI 示例 | **直接作为基线** |
| 2 | [Xilinx/PYNQ_Composable_Pipeline](https://github.com/Xilinx/PYNQ_Composable_Pipeline) | 官方可组合视频流水线，明确支持 PYNQ-Z2 和 AXI4-Stream 动态连接 | **学习正式 PL 视频架构** |
| 3 | [Xilinx/PYNQ-HelloWorld](https://github.com/Xilinx/PYNQ-HelloWorld) | 展示同一图像任务在 PS 软件和 PL 加速中的区别，支持 PYNQ-Z2 | **学习 PS/PL 分工** |
| 4 | [aclich/PYNQ-Z2_sobel_filter_HDMI](https://github.com/aclich/PYNQ-Z2_sobel_filter_HDMI) | USB 摄像头 → Sobel 硬件处理 → HDMI，功能路径非常接近 | **只参考结构和步骤** |
| 5 | [Xilinx/PYNQ-ComputerVision](https://github.com/Xilinx/PYNQ-ComputerVision) | 官方较早的 OpenCV FPGA 加速 Overlay | **只参考算法与接口思想** |

官方 PYNQ-Z2 仓库已经包含 `opencv_face_detect_webcam.ipynb`、`opencv_filters_webcam.ipynb`、`hdmi_video_pipeline.ipynb` 等视频示例，可在[官方 PYNQ-Z2 视频目录](https://github.com/Xilinx/PYNQ/tree/master/boards/Pynq-Z2/base/notebooks/video)核对。

### 版本风险

- 当前项目按 PYNQ 3.1 系列和 Vivado 2024.1 建立新工程。
- `PYNQ_Composable_Pipeline` 的公开构建说明使用 Vivado/Vitis 2020.2，不能把它的旧预编译文件直接当作本项目最终 Overlay。
- `PYNQ-HelloWorld`、`PYNQ-ComputerVision` 和第三方 Sobel 项目也来自较早的软件环境。
- 第三方 Sobel 仓库未见明确许可证时，不把其中代码直接并入比赛交付物；只学习其视频通路设计。

正确策略是：以当前官方 PYNQ-Z2 Base Overlay 建立可运行基线，再把旧仓库中有价值的模块思想移植到当前工具链，而不是围绕旧 bitstream 降级整个项目环境。

## 7. 到货后的兼容性验收

在没有实物测试前，可以确认“接口和官方软件路径兼容”，但不能对某个摄像头个体、线材和供电作百分之百保证。到货后按以下条件验收：

1. PYNQ Linux 能通过 `lsusb` 识别摄像头。
2. 系统出现 `/dev/video0` 或其他 `/dev/video*` 设备。
3. `v4l2-ctl --list-formats-ext` 能列出 640×480@30fps。
4. OpenCV 连续读取 1000 帧，不持续报空帧。
5. USB 摄像头画面能够由官方 PYNQ Notebook 输出到 HDMI。
6. 运行 30 分钟，不出现设备掉线、内存持续增长或画面永久冻结。
7. 拔掉摄像头时，程序能识别数据失效，系统显示故障而不是继续使用旧画面。

只有以上步骤通过，才把该摄像头型号和当前 PYNQ 镜像版本记录为“已验证兼容”。购买时应优先选择可退换渠道。

## 8. 最小 OpenCV 采集代码

用户不需要先系统学习 Python。下面这段代码与 C++ 的 `cv::VideoCapture` 思路基本相同，只需先看懂打开、设置、读取和释放四步。

```python
import cv2

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

ok, frame = cap.read()
if not ok:
    raise RuntimeError("摄像头读取失败")

cv2.imwrite("camera_test.jpg", frame)
cap.release()
```

该代码只用于确认采集。正式 HDMI 输出应从官方 PYNQ-Z2 webcam Notebook 开始修改，随后再接入自研 PL OSD。

## 9. 现在应执行的选择

1. 先购买或借用一只罗技 C270，暂不追求高分辨率或深度摄像头。
2. PYNQ-Z2 到货后先运行官方 webcam → HDMI 示例，保存镜像版本和测试结果。
3. 使用 OpenCV 做界面和数据叠加原型，但正式版把 OSD 移入 PL。
4. 官方链路稳定后，再参考 `PYNQ_Composable_Pipeline` 设计可插入的 AXI4-Stream OSD。
5. 暂不引入目标检测、FINN 或神经网络，以免偏离“传感器融合、风险判断和 AR 辅助驾驶”的主线。

## 10. 一句话结论

> **摄像头选 USB UVC，硬件优先罗技 C270；OpenCV 只负责 PYNQ PS 端采集和原型验证；最终视频通过官方 Base Overlay 进入 PL，由自研 OSD 完成 AR 叠加，再从 HDMI OUT 输出。**
