# 第五轮：完整交付、长期内存和扩展余量（测试前计划）

1. 在前四轮修复后读取来源清单内全部文本，记录路径/类型/行数/SHA256；检查新JS也被构建来源绑定，旧LAB_ONLY发布条件不被绕过。
2. 检查新无线入口能否从全新bit启动并显式应用现有轮标定，避免上位机还没开放时就卡在未标定状态。原HDMI独立入口保留。
3. 检查长时间统计容器和队列容量。用>12000帧观测证明统计内存有界，独立帧/总时长统计保持累计；记录窗口百分位，避免冒充整程分位数。
4. 补充PYNQ进程RSS、系统MemAvailable与CPU实际采样接口，以及理论像素/DDR预算。核对部署依赖按视频配置选择，无线不强依赖旧FFmpeg。
5. 源码冻结后执行整套软件、17套RTL/720p像素、独立风险扫查、OOC综合及完整720布局布线；setup/hold/DRC/连线/来源全部通过才能替换latest_candidate。失败保留并继续修改重建。
6. 依据最终布局布线利用率计算LUT/FF/BRAM/DSP实际余量；编码、无线、PC/轮子延迟因无实板不填写虚构性能。
7. 针对赛题二方向三，提出无需新硬件的PC异步AI感知+多传感器风险解释+事件回放，写明离线模型、接口、帧身份/时效、测试集/消融/故事和实现阶段；不把AI接入安全执行权限。

## 软件复验及新增反例

第五轮软件矩阵：PS108、预集成117、PC20、两套STM32 C、生产C14故障场景及Node接收端通过。12,000帧与54,000帧统计测试证明固定8192窗口、累计独立帧率准确；累计count/min/max/mean另外保留，早先最坏延迟不会被滚动窗口掩盖。新bit轮标定先于就绪检查、非法帧率先于任何硬件调用均通过。

新增修复：来源绑定遗漏.js已补齐；无线部署不再要求旧FFmpeg，检查aiohttp与ARM.so；网络write超时进入拥塞判断，而切换取消/正常断连不误当拥塞；该超时不结束本地控制会话。

完整构建r2在OOC综合门禁发现car_perception_top=-0.851ns，候选被拒绝。将Q16.16正速度向上取整移到既有s0→s0a流水线，保留算术/时间戳同样延迟；独立物理扫查23827项再次通过。失败时序保留ooc_before_pipeline.rpt，最终完整构建使用新的独立版本。其余改进以最终源码冻结后的完整结果为准。

## 最终冻结源码回归

r3的source_start与全量读取清单310文件/96,895行逐项相同，证据为round5_evidence/inventory_build_match.json。完整回归于04:10通过：PC20、PS108、预集成117、两套生产C测试、14故障矩阵、Node接收端、17套RTL仿真、720p捕获的921,600个像素、前向AR/元数据/OSD独立像素对照、10模块OOC综合。最后一次car_perception_top综合时序通过，未删除或放宽100MHz门禁。源码回归后再次哈希核验通过。

权威完整日志：../../preintegration/evidence/complete_v09_wireless720_five_20261004_r3/regression.log。软件测试成功写入stderr的诊断不代表失败，流水线以各测试进程退出码和显式PASS为准。

## 完整构建与交付复核

2026-10-04 04:22，r3七阶段全部PASS，最新完成指针更新。整机100MHz WNS=+0.111ns、WHS=+0.014ns，TNS/THS=0；DRC无Warning/Critical Warning/Error级违例，保留两项BRAM Advisory；跨时钟bus-skew裕量8.880ns/8.623ns。双DMA、HP0互连和无线720p HWH审核通过。

最终资源为LUT11,691/53,200，寄存器17,252/106,400，BRAM5.5/140个36Kb等效块，DSP9/220；余量与使用条件见REPORT.md。编码及无线不能由PL空闲比例推导。

交付后独立只读复核通过：ZIP CRC/SHA256、bit/HWH及20项runtime与13项无线文件一致；全部310项源码哈希与生成工程绑定相同。证据round5_evidence/delivery_verification.json。未连接实板，hardware=PENDING、motor_output_allowed=false、LAB_ONLY分类仍保留，未绕过运动发布。
