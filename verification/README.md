# 精简验证说明

本说明提取已有记录的关键结论，不包含原始调试日志。历史结果与本次检查分列；未重新上板、烧录或驱动车辆。

## 交付身份与可核查来源

- 软件：`v014_video_720pl_jpeg_20261031_r7`；FPGA沿用r6；寄存器契约14 / `0xC425100E`。
- `summary.json`保留历史验证摘要、源文件哈希和原始记录哈希；`original_source_manifest.json`保存更名前的来源清单。
- `path_migration.json`说明英文命名迁移。迁移涉及路径与文档；当前文件哈希以根目录`SOURCE_MANIFEST.json`为准。
- bit、HWH、STM32固件、原生动态库须保持与原交付字节一致；完整性检查会逐项验证。

## 已有验证结果

| 层次 | 历史结果及范围 |
| --- | --- |
| r7软件 | 180项Python测试、27项浏览器场景通过；25个锁车零输出启动样本。 |
| 滤波及趋势RTL | 1449个样本与独立参考比对；24664个分类边界用例通过。 |
| 同帧元数据 | 6帧、24字元数据，含反压验证。 |
| 二维态势叠加 | 7帧、6451200像素比对通过，覆盖帧内状态变化及随机反压。 |
| 完整视频链仿真 | 4帧1280×720输出，检查态势输出及过期关闭。 |
| r6布局布线 | 100MHz；WNS +0.071ns、TNS 0、WHS +0.022ns、THS 0。 |
| r6资源 | placed报告：LUT 23633/53200、FF 18881/106400、BRAM 25.5/140、DSP 2/220。 |
| 实板视频 | 已有完整720p PL处理及JPEG/DMA输出记录；r6短窗口录屏约17.5fps。25fps是配置目标，不等于持续实测结果。 |

时序与资源摘要对应r6实际实现，r7没有更换FPGA。报告原件没有作为源码文件或原始日志装入本包。

## 本次打包检查

先运行`python verify_source.py`：检查当前所有文件哈希、英文无空格路径、旧路径引用迁移、原有二进制身份与RTL绑定。板端lab_manifest运行文件清单及console_manifest的基清单/桌面文件哈希已同步更新；source_identity保留FPGA构建时的历史路径，不作为当前文件入口。离线回归命令和本次结果见`package_checks.json`。最终RAR另经解压后逐文件核对；GitHub使用同一份源码树。全量Python测试依赖先构建safe_control.dll和Windows car_video.dll；本次未构建这两个库，相应3项报缺失依赖，不能视为全量通过。Windows构建入口分别是pynq_fpga/host/c_build/build_car_c_dll.ps1和pynq_fpga/preintegration/build_wireless_native.ps1。

本次不重跑Vivado、不重新烧录，也不把历史测试计为新测。r7显示闪烁效果由使用者核对；r7未新增性能测试或整车长测。此前重启后的STM32无回包诊断不等于已经恢复；此包不新增恢复结论。启动历史中出现过一条损坏JPEG解码提示，保留在摘要中。

## 快速复核

```powershell
python verify_source.py
python -m unittest discover -s tests -p "test_tactical_*.py" -v
python -m unittest discover -s skill/amd-pynq-project-workflow/scripts -p "test_*.py" -v
```

源码重建与板端启动入口见根目录README及`pynq_fpga/preintegration/COMPLETE_BUILD.md`。从零环境的全流程复现需另外执行构建和实板验收，本次不声称完成该验证。
