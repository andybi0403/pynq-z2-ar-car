> 2026-10-13：当前源码为v0.10，ID 0xC425100A；新增STM32固件构建/哈希绑定、115200 UART v3传感器上报与PL原子注入。编码器接线保留。默认CLI使用HybridCarLink；须同步烧录新STM32固件和使用新Overlay，旧v0.9包不支持该分工。接线与协议见 ../../docs/03_硬件与接线/16_STM32传感器采集与PYNQ编码器方案_20261013.md。

# 当前完整工程重建与部署

当前源码契约v0.9，ID为0xC4251009。旧目录与旧包保留追溯，不能直接配当前主机运行程序。本次仍为LAB_ONLY，无实板PASS、无电机释放或驾驶许可。

在Windows项目根目录执行唯一完整入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/build_complete.ps1
```

可用`-Name v09_my_test`指定可辨认的目录名；已存在的目录拒绝覆盖。默认名称包含当前契约版本和毫秒时间。流程为：捕获源码→两份STM32 C回归/PC协议/寄存器/主机/运行器/故障矩阵/联合软件证据/13个RTL TB和像素比对/9个OOC综合→源码核对→独立Vivado工程综合与完全布线→时序/DRC/HWH检查→bit/HWH及运行软件打包→最终源码核对。

各阶段结果写到`preintegration/evidence/complete_<名称>/pipeline.json`，阶段输出与哈希保存在同一目录。失败不更新最新候选。只有全部通过后写`preintegration/latest_candidate.json`，其中包含可打开的工程目录、完整包目录、ZIP和SHA256。Vivado工程文件为该build_dir下的`task7_8_integrated.xpr`。旧`rebuild_video_reliability.ps1`已转到此入口，不再默认写9月27日目录。

默认生产风险参数不能被打包步骤改写。构建身份绑定RTL、寄存器生成器、构建脚本/约束/IP及主机/测试/权威STM32 C和PC输入；生成的DLL/编译日志不作为输入。包另逐个绑定实际20份运行Python文件。测试后或构建中源码改变会失败，避免测试结果与新包错配。

将整个包目录解压/复制到PYNQ；这是Overlay包，不是SD卡系统镜像。Python 3.10及以上，PYNQ/NumPy/pyserial/FFmpeg和设备路径由包内`deployment_check.py --board`检查，检查不会加载FPGA或打开串口。分项/联合启动与独立日志审核见包内README及STATUS_PAGE.md。软件审核、DRC、时序和包文件通过不代表电气、传感器标定、停车时延、HDMI色序或30分钟实物联合验收通过。

联合CLI在正式计时前最多等待5秒，要求采集健康、周期数据新鲜、轮子静止且持续稳定300ms；配置了双轮SCALE时还要求里程有效。就绪结果另存`startup_readiness.json`，失败不开始正式测试，也不删掉正式记录中的异常样本。视频启动在工作线程中进行。收尾时视频/帧源清理各等待最多1秒，随后等待视频线程3秒；超时记录资源终止未确认并继续关闭UART，整个会话判为失败，不能作为资源全部回收或实板通过的证明。
