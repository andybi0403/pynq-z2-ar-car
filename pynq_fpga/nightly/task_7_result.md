# 任务7结果：完整PYNQ控制工程

Status: PARTIAL

## 当前环境完成项

- 保留隔离基线，并建立接入生产`car_perception_top`和`car_axis_osd`的独立PYNQ-Z2集成候选，目标器件为`xc7z020clg400-1`。
- 建立PS7、M_AXI_GP0、S_AXI_HP0、AXI VDMA MM2S、生产感知控制核、视频时钟、HPD GPIO、UART1 EMIO和PS中断链。
- 固定并审计地址：VDMA `0x43000000`、生产控制核`0x43C00000/4KiB`、dynclk `0x43C10000`、VTC `0x43C20000`、HPD GPIO `0x41230000`。
- 提供HWH审计和板端运行入口；开发机缺少PYNQ包或bit/hwh不匹配时明确失败，不伪装硬件。
- 17项预集成Python测试、312项视频适配检查、完整生产回归及12项板级包装层检查通过。
- 集成工程完全布线，WNS `+0.079ns`、WHS `+0.027ns`、TNS/THS 0，阻断DRC为0。
- 已生成独立`LAB_ONLY_NO_MOTOR_NON_RELEASE` bit/hwh和可复制ZIP；包内契约、SHA-256、板端MMIO、传感器矩阵和UART STOP入口自检通过。UART验收只接受STOP后新收到的状态并记录300ms响应门限。

## 未完成条件

真实PYNQ上的Overlay加载、MMIO、IRQ发现、VDMA DDR访问与Linux驱动行为未验证；板卡修订版和外部电气条件也未确认。已生成的bit仅限无电机台架，不是发布bitstream。因此工程达到“生产核已集成的可复现候选”，尚未达到“完整板上控制工程发布”。

## 重跑入口

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/run_tests.ps1 -Vivado -Synthesis -Implementation -RequireAEBlocked
vivado -mode batch -source pynq_fpga/preintegration/vivado/create_integrated_candidate.tcl
vivado -mode batch -source pynq_fpga/preintegration/vivado/impl_integrated_candidate.tcl
```

详细证据见`night_20260918_E.md`和`../preintegration/manifests/integrated_verification_20260919.json`。
