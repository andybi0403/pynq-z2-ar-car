# v0.9完整候选构建与交付核验

本轮状态：LAB_ONLY_CANDIDATE，硬件验收PENDING。没有运行电机、加载实板Overlay或生成实板PASS。

## 可交付文件

- Vivado工程：`fpga/build/task7_8_v09_complete_20260930_r2/task7_8_integrated.xpr`。
- 部署目录：`lab/task7_8_lab_only_v09_complete_20260930_r2/`。
- 部署ZIP：`lab/task7_8_lab_only_v09_complete_20260930_r2.zip`。
- 最终ZIP SHA256：`f3fdebdf8b1959225ae0f6db1d1efb00c7bb84682444fbe17d2711d9d510ac4c`。
- 契约v0.9，ID `0xC4251009`；权威寄存器生成表、RTL、HWH和20份运行源码一致。

## 本轮实际证据

完整回归：193项Python测试（PC20、主机105、预集成68），两份STM32 C回归，14个生产C故障场景，13项RTL TB，3项像素参考比对，9项模块综合。生产历史帧显示链路三帧921600像素零差异。

独立整机完全布线：WNS +0.077ns、WHS +0.020ns，TNS/THS为0；DRC无Warning/Error/Critical Warning，保留1条REQP-181 VDMA存储器Advisory。这只描述DRC检查，不表示所有工具日志无warning。时序报告仍列TIMING-18端口延迟及XDCB-5约束查询方法提示；内部无时钟/无约束端点为0。

视频拓扑/HWH、共享复位和总线偏斜审核PASS，三组bus skew余量+9.122/+8.959/+8.813ns。bit/HWH生成、生产契约自检、源码前后核对通过。独立ZIP核验逐一重算20份源码及bit/HWH哈希，核对归档内实际清单和文档、回归来源身份及7阶段日志哈希，结果保存`post_package_audit.json`。`deployment_offline.json`仅验证开发机文件包；没有检查板端依赖。

流水线完成后发现状态页面说明仍写着“还没有新版完整布线包”。已仅修正文档并复用同一已核验bit/HWH重新打包，独立记录documentation_refresh阶段；运行源码/RTL/回归来源没有改变。初始ZIP哈希保留在pipeline的initial_zip_sha256，最终ZIP以本页及pipeline的zip_sha256为准。未将文档刷新伪装成重新运行RTL测试。

## 1—8完成审计

| 项目 | 当前证据 | 尚需证据 |
|---|---|---|
| G1共用会话 | 一次加载/唯一MMIO、慢视频启动控制不阻塞、并发测试和匹配包 | 实板加载、配置保持、启动与退出 |
| G2控制闭环 | 意图租约、风险限幅/STOP/显式恢复、真实C软件故障矩阵 | 实际UART停车时延与硬件故障场景 |
| G3帧关联 | 原始记录重算、随帧历史状态、完整生产像素链路、身份/实际SOF时刻寄存器 | 实板HDMI帧身份/时延；曝光至屏幕需独立测量 |
| G4里程/标定 | 双轮PL64位里程、有效性/故障/epoch、严格配置保存和读回 | 编码器接线方向、轮径/SCALE及制动实测 |
| G5显示/页面 | HDMI实际LOCK/原因/里程、页面配置队列与下载、像素/HTTP测试 | 真实显示色序和板端页面操作 |
| G6异常收尾 | 摄像头/串口异常、慢启动和卡住清理反例、超时失败且继续关闭UART | 实板摄像头拔出、VDMA/HDMI异常后进程与资源回收；清理超时不能证明驱动已终止 |
| G7联合验收 | 软件故障矩阵、日志审核、包/标定来源核验、正式1800秒门禁 | 真实30分钟同一会话及电气/传感器/串口/视频测量 |
| G8构建/部署 | 独立完整流水线、完全布线、同版包/哈希、导航、离线部署检查 | 板端依赖与实际启动兼容性 |

本机只读联网检查显示有线网卡Disconnected，板端IP尚未核验，见board_connectivity_precheck.json。此事实不足以判断板卡本身故障。继续实板验收需要可访问的板端地址、登录环境以及电机物理断开的确认。完整目标保持IN_PROGRESS，不以软件/构建结果替代硬件证据。
