# PYNQ-Z2 多传感器 AR 辅助驾驶小车

本仓库与国赛 RAR 提交包使用相同文件内容，仅包含最近部署的 v014_video_720pl_jpeg_20261031_r7 软件及其 r6 FPGA 源码、配套 STM32 程序和项目 skill。接口契约 14 / 0xC425100E。

## 功能与分工

- PS：USB相机采集与MJPEG解码、UART、缓冲调度、Web服务、控制协调。
- PL：统一快照、三点中值滤波、距离趋势、Sobel、中文HUD、二维态势、完整1280×720 JPEG硬件编码。
- STM32：超声波与红外采集、电机执行、实际PWM及锁车回传、本地250mm前向保护。
- 浏览器：人工驾驶、原图/处理图、同帧对比、状态显示、记录导出与回放。

## 目录与使用

- `runtime/`：最近部署版本的板端软件（英文路径迁移见verification/path_migration.json）、bit/HWH及固件；桌面入口在 `runtime/desktop/`。
- `pynq_fpga/fpga/`：RTL、约束、寄存器定义及构建输入。
- `pynq_fpga/preintegration/`：整机集成、测试和构建脚本。720p重建入口 `build_complete.ps1 -Wireless`，说明见 `COMPLETE_BUILD.md`；需要 Vivado 2026.1 与相应 Python/C/RTL 工具。
- `stm32_pynq_firmware/`、`stm32_tools/`：本系统配套固件源码与基础驱动。
- `tests/`：源码级回归测试，不包含测试输出日志。
- `skill/amd-pynq-project-workflow/`：自建项目技能，先阅读 `SKILL.md`；历史案例仅用于方法参考，当前交付身份以根目录清单为准。
- `SOURCE_MANIFEST.json`：当前文件哈希、版本与原始上板来源追溯。运行 `python verify_source.py` 检查完整性。

部署：将 `runtime/` 整体复制到 PYNQ，先阅读其中的运行说明并检查板卡、串口和连接。默认锁车，首次只做静态检查；部署或加载FPGA不能代替实车验收。板端启动入口 `runtime/start_console.sh`。保留原运行目录以便回退。

## 版本及验证范围

PL时钟100MHz，完整720p输出。视频配置目标25fps、JPEG质量85；r6窗口短测约17.5fps，r7未新增性能长测。算法、像素仿真、布线及实板输出各有独立记录；本次只核对源码交付，没有重跑实车测试。重启通信恢复及整车长稳仍需核验。

未包含会话日志、调试记录、录屏、私人照片、缓存、旧版本压缩包和Vivado中间产物。第三方许可证与必要固件/bit/HWH保留。

## 开源许可

原创代码采用根目录MIT许可证；第三方IP、字体及厂商基础代码保留各自原始条款，参见 `THIRD_PARTY_NOTICES.md` 及各组件许可证。mjpegZero含额外条款，不能将整个仓库统一理解为MIT。

## 本次提交整理

所有包内目录、文件名采用英文；源码和说明正文保留中文。英文目录映射：`stm32_pynq_firmware/`为现用STM32固件，`stm32_tools/pc/`为PC协议工具。桌面入口为`runtime/desktop/open_console.pyw`，说明为`usage.md`。

验证摘要见[verification/README.md](verification/README.md)，来源见[verification/summary.json](verification/summary.json)。`verification/original_source_manifest.json`仅用于核对更名前的来源，不可当作当前路径清单；`SOURCE_MANIFEST.json`负责当前全部文件完整性。

模型协作、优化前后对比和从零复现说明属于AMD自主选题设计报告§3.3.5.3的明确内容。本源码包提供实现、构建/验证脚本及精简证据入口；不以此替代设计报告。
