> 当前v0.10混合采集：先烧录包内stm32_hybrid_v3.hex，UART双方115200 8N1，超声波/红外恢复STM32接口，编码器仍经原PCB接PYNQ。新运行器先启动查询并原子提交传感器，再进行就绪检查；具体接线与协议见包内HYBRID_SETUP.md。旧9600/P帧步骤不适用于此版本。仍为电机动力断开的LAB_ONLY。

# PYNQ-Z2 无线候选：搭建与实测

本版为 LAB_ONLY，浏览器可以看视频、查看反馈、接管零输出意图与 STOP；非零 PWM 在服务器和已有控制层均被拒绝。必须保持电机动力断开。不能据离线测试宣称 720p30 或运动验收通过。

## 无网络测试与编解码对照

`wireless_runtime.py --video-only --headless --duration 180` 不启动浏览器服务，不探测路由地址。普通浏览器模式在访问地址探测失败时保留服务并继续视频，提示端口及网络故障；网口物理链路仍需恢复后才能访问。

默认保留 `--jpeg-profile balanced --decode-dct islow`。显式对照可以使用 `--jpeg-profile balanced_fast`（Q85/4:2:0、快速编码 DCT）及 `--decode-dct ifast --reuse-decoder`。解码扩展要求重新编译 native 库，不能把旧库的测试结果用于这些新配置。选择优化配置须保存同帧画质和 ARM 实测证据。

日志分别记录采集队列替换、采集年龄拒绝、关联失败、坏 JPEG 和故障边界发布拒绝。异常 JPEG 最多保存八帧。`published` 表示板端成功发布的唯一帧，`active_fps` 从各阶段首次事件计时并包含恢复，不代表浏览器绘制帧率。

## 接线和路由器

GL-SFT1200 的 LAN 口通过短 Cat5e/Cat6 网线接 PYNQ。C270 直接接 PYNQ USB HOST。电脑加入路由器的 5GHz 热点。首次需要在路由器管理页设置 SSID `PYNQ-CAR-5G`、独立密码、地址 `192.168.8.1`，为板卡 MAC 保留 `192.168.8.10`。地区选择实际所在地，使用允许的非 DFS 信道（初始 36）、80MHz；若干扰明显，记录配置后对比 40MHz。电脑地址自动获取。

热点本身即可连接小车，不需要互联网。要访问互联网，需要把路由器 WAN 接入上游网络或配置中继；首次验收先用独立局域网。不得把控制端口映射到公网。

充电宝 C1 -> 固定 12V PD 取电线 -> 板卡 5.5×2.1mm 中心正极 DC；板卡电源跳线 REG。C2 -> 5V/3A USB-C -> 路由器。双口同时应维持 12V/2A 和 5V/3A，不能只按宣传总功率判断。底盘沿用原动力电源。测极性、电压、双口插拔与满负载重启后再固定线束；实板本轮未接入，供电结果待测。

## 离线构建与板卡部署

开发电脑执行 `powershell -File preintegration/build_complete.ps1 -Wireless -Name <新的唯一名称>`。这会运行旧工程回归、新无线测试、布局布线、时序与 HWH 连线审核，生成独立 LAB_ONLY 包。旧 HDMI 调试配置可不加 `-Wireless` 单独构建，不与无线输出共用 READY。只有完整流水线成功才更新 latest_candidate。

将成功的同版完整候选包复制到 PYNQ。首先检查 `python3 --version`（需要 Python >=3.10）及当前 PYNQ 可导入；使用板卡镜像自带 NumPy，避免替换其 ABI。安装构建依赖 `cmake`、C 编译器及 aiohttp：

```sh
python3 -m pip install -r wireless_requirements.txt
cmake -S native -B native-build -DCMAKE_BUILD_TYPE=Release
cmake --build native-build --parallel 2
```

CMake 固定官方 libjpeg-turbo 3.1.2 release archive 和 SHA256，ARM 构建开启 NEON。没有互联网时，先在电脑取得官方 tar.gz，复制到板卡，配置时加 `-DWV_TURBO_ARCHIVE=/绝对路径/libjpeg-turbo-3.1.2.tar.gz`；仍核验相同 SHA256。电脑 DLL 仅用于离线正确性测试，不能复制到 ARM 板卡替代 `.so`。板卡 Linux 编译、NEON 汇编和运行仍须到板验证。

本地视频 ABI 为 `car-video/2`，Python 与本地库必须同版。C270 首次出图可能需要数秒；采集线程保持同一条流，最多等待 5 秒，并丢弃过旧的启动首帧。每次读取仍最多阻塞 500ms；取得首帧后超时与旧帧立即进入原故障处理。JPEG 解码仅兼容重启标记 RST0–RST7 之前的冗余填充字节，逐条检查全部解码警告；缺失数据、异常码流和其他警告拒绝。兼容计数记入 `jpeg_restart_padding_warnings`，不能据此宣称无 JPEG 警告或完成长期视频验收。

```sh
python3 wireless_benchmark.py capture --seconds 60 --output evidence/capture.json
python3 wireless_benchmark.py codec --jpeg 实际复杂画面720p.jpg --seconds 60 --output evidence/codec.json
sudo python3 wireless_runtime.py --motor-disconnected --calibration measured_wheels.json --duration 1800 --video-mode fixed
```

运行器核验包哈希、无线 HWH 720p/双 DMA 连线和原保护合同，再独占一次 Overlay；终端打印带本次会话令牌的浏览器链接。复制完整链接进入电脑浏览器，地址为 `http://192.168.8.10:8080`。重启后旧 Cookie、控制身份和接管权失效。摄像头不支持原生 MJPEG/1280×720/30 时会明确失败，无输出 fps 补帧滤镜。

## 视频与控制

默认自动模式上限30fps/Q85；Q≥85 使用4:4:4色度和准确DCT，Q<85 保留4:2:0节省带宽；可在页面选择auto/manual/fixed，或启动时使用`--video-mode manual --fps 24 --quality 65`。固定验收模式必须显式选`--video-mode fixed`，保持30fps/Q75，不会降档。自动模式结合编码、发送、接收/绘制、CPU和队列压力，降低输出目标，稳定五秒后逐档恢复，分辨率保持720p。界面同时显示目标、实际接收/绘制帧率、单帧大小和舍弃计数，降档不计作720p30通过。原图质量固定摄像头原生，帧率可调；画质选择仅作用于处理图。

新bit加载会清空轮尺度；使用既有合同的`--calibration measured_wheels.json`先加载并回读轮标定，再进行采集就绪检查。缺少有效尺度时明确拒绝启动，不能通过删除保护绕过。名义标定仅可用于无电机台架，不代表实车已标定。ZERO参数至少66个100MHz时钟；默认100ms静止观察。控制状态提供停车原因及命令/风险是否同批，视频故障重试不退出传感器服务，恢复后不自动恢复接管。

Linux状态统计提供进程/系统两核CPU、进程RSS峰值、可用内存及25.80MB固定DMA容量。长期分位统计保留最近8192项；累计帧率和逐分钟帧率独立保留，无重复帧。实际资源余量需到板完整负载记录。

默认处理图质量 75、4:2:0。原图直接转发摄像头 JPEG，不做完整帧解码和编码；冻结触发一次真实 PL 回写与同帧 JPEG 对比。传输仅一路；第二个视频请求替换前一个。采集队列容量 1，输入和输出各 3 个预分配 DMA 缓冲，另有 1 个不进入编码队列的私有完成缓冲，编码队列容量 3；所有主动丢帧计数。处理图从真实 S2MM 完成后编码，不能用 CPU 仿造 PL 图。现有帧元数据协议占用输入前 18 像素，按已有硬件协议解释；原始 JPEG 不修改。

控制仍由现有会话线程唯一拥有 MMIO 和 UART。WS 仅提交有界邮箱。四时间戳握手建立时间映射；映射每秒刷新，误差过大、旧指令、重放、断连均撤销接管并 STOP。只有新的有效意图延长 250ms 租约，视频和状态查询不续租。WASD 事件框架每 50ms 提交意图，当前候选固定零输出；空格、失焦、释放按键、页面隐藏和断连停止。运动发布必须另行完成电气、标定、制动和故障验收，不提供绕过开关。

## 到板验收

先以 `ethtool eth0` 确认 1000Mb/s；电脑运行 iperf3 服务，板卡在 10m/20m 分别测 TCP 双向，目标 >=150Mb/s 且 >= 实际平均视频码率 2 倍。固定路由固件、信道、质量和测试画面；复杂纹理、快速运动均须覆盖。

电脑接收审计：`python wireless_benchmark.py receive --token <本次令牌> --seconds 1800 --output evidence/pc_receipt.json`。此工具占用唯一视频连接，浏览器会被替换；实际屏幕帧率和延迟另用可见时间标记/屏幕拍摄验证。PC 与 PYNQ 单调时钟不能直接相减。接收计数也不能代替显示帧率。

完整负载连续 >=30 分钟，每完整分钟采集/处理/接收独立帧率 >=29.7；编码独测 >=36fps 且联合预算有余量；两核平均总 CPU <=80%；队列无持续积压；WS 往返 P95 <=50ms；可见图像端到端 P95 <=250ms；电池运行 >=1 小时；无供电重启、JPEG 损坏或 DMA 溢出。记录摄像头拔出、网络中断、编码阻塞、切换和服务重启的失败及恢复情况。

软件编码未达标时保留真实失败证据，下一阶段进入已审核 mjpegZero 版本的 PL JPEG 优化，重新测复杂画面吞吐、流控与溢出；本版未伪造 PL JPEG 编码器或降低规格宣称通过。


C270 清晰度配置：对比度36、锐度32、50Hz防闪烁、关闭低光降帧（Exposure Auto Priority=0）。保留自动曝光和自动白平衡。原生Linux打开摄像头时读取并核验四项控制，失败回滚；其他摄像头不套用C270参数。显式基线对照可用环境变量 WV_CAMERA_PROFILE=0。解码使用准确整数DCT；固定Q75验收仍采用4:2:0，高清Q85不计为固定Q75验收结果。
# 视频分项测试与编码选择

`wireless_runtime.py --video-only` 使用正式采集、PL、HTTP 和浏览器视频路径，不打开 UART，不接受接管或标定，也不产生 STM32 反馈。传感器未标定状态保持无效；视频分项结果不能作为整车联合验收。日志为 `video.jsonl` 和 `video_summary.json`。

默认 `--jpeg-profile balanced` 保持完整 1280×720、准确 DCT 和所选质量参数，采用 4:2:0 色彩采样以降低编码负担。`detail` 为 4:4:4 准确 DCT，`legacy` 保留旧版按质量切换的编码方式。每帧记录实际编码方式和解码、PL、编码耗时；该选择不改变固定验收的 30fps/Q75 目标，也不证明已达到目标。
