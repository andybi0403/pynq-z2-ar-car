# 当前完整工程重建与部署

本包当前源码契约14，ID为0xC425100E；软件r7、现用FPGA来自r6。以下脚本产生新的构建候选，不覆盖本包已经部署过的二进制。历史验证与本次整理范围见根目录verification/README.md。

在Windows项目根目录执行唯一完整入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pynq_fpga/preintegration/build_complete.ps1 -Wireless
```

可用`-Name v014_my_test`指定可辨认的目录名；已存在的目录拒绝覆盖。默认名称包含当前契约版本和毫秒时间。流程为：捕获源码→两份STM32 C回归/PC协议/寄存器/主机/运行器/故障矩阵/联合软件证据/13个RTL TB和像素比对/9个OOC综合→源码核对→独立Vivado工程综合与完全布线→时序/DRC/HWH检查→bit/HWH及运行软件打包→最终源码核对。

各阶段结果写到`preintegration/evidence/complete_<名称>/pipeline.json`，阶段输出与哈希保存在同一目录。失败不更新最新候选。只有全部通过后写`preintegration/latest_candidate.json`，其中包含可打开的工程目录、完整包目录、ZIP和SHA256。Vivado工程文件为该build_dir下的`task7_8_integrated.xpr`。旧`rebuild_video_reliability.ps1`已转到此入口，不再默认写9月27日目录。

默认生产风险参数不能被打包步骤改写。构建身份绑定RTL、寄存器生成器、构建脚本/约束/IP及主机/测试/权威STM32 C和PC输入；生成的DLL/编译日志不作为输入。包另逐个绑定实际20份运行Python文件。测试后或构建中源码改变会失败，避免测试结果与新包错配。

将整个包目录解压/复制到PYNQ；这是Overlay包，不是SD卡系统镜像。Python 3.10及以上，PYNQ/NumPy/pyserial/FFmpeg和设备路径由包内`deployment_check.py --board`检查，检查不会加载FPGA或打开串口。分项/联合启动与独立日志审核见包内README及STATUS_PAGE.md。软件审核、DRC、时序和包文件通过不代表电气、传感器标定、停车时延、HDMI色序或30分钟实物联合验收通过。

联合CLI在正式计时前最多等待5秒，要求采集健康、周期数据新鲜、轮子静止且持续稳定300ms；配置了双轮SCALE时还要求里程有效。就绪结果另存`startup_readiness.json`，失败不开始正式测试，也不删掉正式记录中的异常样本。视频启动在工作线程中进行。收尾时视频/帧源清理各等待最多1秒，随后等待视频线程3秒；超时记录资源终止未确认并继续关闭UART，整个会话判为失败，不能作为资源全部回收或实板通过的证明。

## 当前720p配置与依赖

使用`-Wireless`选择`wireless720`，不加时脚本选择`hdmi640`；两者不是相同输出配置。先安装Vivado 2026.1及PYNQ-Z2板卡文件，确保python、Node.js、GCC/ARM工具链可用；浏览器场景需Playwright及Edge。第三方源码保留在pynq_fpga/third_party，许可见根目录THIRD_PARTY_NOTICES.md。

脚本中的Vivado安装路径、ARM编译器位置需按机器调整。build_wireless_native.ps1构建Windows测试用原生库，使用MSVC、CMake并获取libjpeg-turbo依赖；板端ARM库需在匹配的ARM/Linux环境根据native/CMakeLists.txt单独构建。板端需PYNQ、NumPy、pyserial及相机解码依赖。既有runtime/native/libcar_video.so为板端ARM库，不能直接作为Windows库使用。

英文命名迁移已同步源码内的STM32路径及固件目录查找。完整从零构建未在本次整理中重新执行；构建候选必须另行核验源码绑定、时序、板端身份、完整720p画面和静态通信，再安排实车验收。
