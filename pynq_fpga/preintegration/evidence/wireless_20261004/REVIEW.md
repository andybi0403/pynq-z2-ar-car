# 无线实施自查与性能优化（2026-10-04）

基线 latest_candidate 为 v09_front_20261001_r1，合同 0xC4251009。保留硬件和 LAB_ONLY 门禁。用户确认暂时无法连接实板；下文所有 PC/仿真结果均不构成实板验收。

## 第一轮：接口、所有权和退出

新增原生 MJPEG/V4L2 + libjpeg-turbo 3.1.2、720p S2MM、浏览器 MJPEG/WS、同帧冻结。初次检查修复 STOP 未撤销 owner、旧 claim 未检查时间、部分 DMA 分配失败会泄漏、原生 read/close 竞态、关闭 Codec 后访问空句柄。有限帧 VDMA 重置并以 FrameCntEn/IRQFrameCount=1 停止两通道，输出必须在两通道完成且 halt 后才编码。

旧工程回归首次发现原 HDMI 阻塞驱动需要 stop 才能退出，而无线缓冲应在 worker join 后释放。改为显式 worker_owned_shutdown，保留旧驱动的取消行为。冻结测试首次使用固定等待时间，在完整回归中出现调度竞争；改为等待冻结请求确实生效后发布帧。

第一轮修正后：preintegration Python 94 项通过；完整 1280×720 wrapper + S2MM adapter 仿真通过 921600 像素，检查 SOF、EOL、BGR0、停顿保持和独立背景区域。初始背景区域误选 ROI 边框，缩到真实非覆盖区，不修改实际 PL 像素逻辑。

第一轮优化：原图保留相机 JPEG 直接转发；处理图直接解码到预分配 DMA；仅压缩 JPEG 经 Python 拷贝；固定输入/输出各 3 个缓冲；避免 Python 逐像素与大帧管道。

## 第二轮：拥塞、新鲜度和热路径

流水线测试使用真实电脑端 native JPEG 编解码与明确标注的离线 DMA fixture，发现历史关联缺少 submitted_host_ns / receive_to_submit_ms，补齐并验证有序独立帧与 worker 退出。

控制排队检查发现原本按服务器接收时重新给 100ms，会忽略指令在网络中已经消耗的时间。现将握手估算的原始年龄上界带入邮箱截止时间，消费时再检查。250ms 没有新意图即撤销 owner，时钟映射超期也撤销；独立 50ms watchdog 不依赖慢 WS 写入。延迟观测消息不续租。断连和重连不恢复控制。

第二轮优化：容量 1 的采集队列仅保留最新完整 JPEG；PL 与编码并行，输出缓冲直到编码完成才归还；编码队列容量 3；默认 75 / 4:2:0 固定；HTTP 分开写头和 JPEG 以减少压缩帧拼接；冻结请求只允许一个并发；页面静态内容启动缓存。原图模式的流水线回归确认没有 decode / DMA / encode 调用。

第二轮修正后 22 项无线测试通过。浏览器脚本通过 Node 语法校验。原生 Windows DLL 编译使用相同 CRT 并修正 CMake 本地归档路径，固定来源 SHA256；Windows SIMD OFF 仅用于正确性。Linux 构建添加 libm，保持 ARM SIMD ON，Linux V4L2/NEON 编译仍待到板执行。

复杂纹理 PC 基准见 host_codec_benchmark.json：AMD64 / Windows，720p 固定质量 75 / 4:2:0，编码约 75.8fps、解码+编码串行约 37.7fps。这不能证明 650MHz Cortex-A9 性能。随机纹理 JPEG 平均 553517 bytes，30fps 约 132.8Mbps；两倍余量应 >=265.7Mbps，150Mbps 不能覆盖所有复杂画面。摄像头原始 JPEG 码率另测。

## 完整构建与待验收

完整候选构建记录由 build_complete.ps1 生成独立 pipeline.json；只有源哈希、旧工程回归、720p 仿真、综合、布局布线、时序、DRC、HWH 和包合同全部通过，才更新 latest_candidate.json。任何失败均保留日志并修复后重新生成候选。

实板项目全部 PENDING：C270 原生 MJPEG/720p/30；Linux .so 编译及 NEON；VDMA 实际单帧完成；PL 真像素参考一致；完整 30 分钟唯一处理/接收帧率；两核总 CPU；无线 10m/20m 吞吐；屏幕显示和玻璃到玻璃延迟；电池与供电；UART 真实锁存/停车；运动发布。

交付未替换已有硬件、未给实板性能 PASS、未开放非零驾驶，也未以输出补帧或降低质量宣称达标。
