# 任务8结果：摄像头与HDMI视频链路

Status: PARTIAL

## 当前环境完成项

- 固定摄像头为Logitech C270，VID:PID `046D:0825`；Windows DirectShow枚举和短时烟测已有证据。
- 建立FFmpeg dshow/v4l2统一输入、精确整帧读取、640×480@30缩放、`BGR0`打包、色条、指标统计和三缓冲所有权模型。
- 建立完整候选视频链：DDR → VDMA MM2S → AXIS 32→24 → 生产`car_axis_osd` → AXIS-to-Video → VTC → RGB2DVI → PYNQ-Z2 TMDS。
- VDMA帧完成和主动低HPDN中断均接入PS IRQ；HWH契约检查通过。
- DDR保守搬运预算为147.456 MB/s；这是四次4字节像素搬运的预算值，不是实测性能。
- 本地XDC与原理图交叉核对HDMI管脚；HPDN在R19配置为主动低输入。
- Vivado集成实现完全布线，WNS `+0.079ns`、WHS `+0.027ns`、TNS/THS 0，阻断DRC为0。
- LAB_ONLY包已包含同名bit/hwh、色条、C270 900帧采集和证据输出入口；camera默认检查≥25fps、P95≤50ms、推算掉帧率≤5%，色条明确等待人工确认色序。

## 未完成条件

C270在PYNQ Linux上的V4L2模式、实际30fps、颜色顺序、物理HDMI画面、Linux中断、端到端延迟、掉帧和30分钟稳定性均未验证。生产OSD已在独立候选中接入，但没有发布bitstream和实板证据。因此不能声明摄像头到显示器已跑通。

## 板上首测入口

生成并人工批准匹配的bit/hwh后，先显示DMA色条，再接C270：

```bash
python3 host/board_runtime.py --bit candidate.bit --hwh candidate.hwh
python3 host/board_runtime.py --bit candidate.bit --hwh candidate.hwh --ffmpeg /usr/bin/ffmpeg --camera-device /dev/video0 --frames 900 --metrics evidence/c270_30s.json
```

详细证据见`night_20260918_E.md`和`../preintegration/manifests/integrated_verification_20260919.json`。
