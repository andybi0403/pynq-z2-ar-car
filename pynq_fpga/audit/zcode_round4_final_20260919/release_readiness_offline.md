# release_readiness_offline：六层交付就绪状态（PYNQ到货前）

日期：2026-09-19。结论：**OFFLINE_READY_FOR_HARDWARE**——离线可验证层次全部有新鲜证据；无未闭环P0/P1/P2；实物层次全部HARDWARE_PENDING。

| 层 | 状态 | 证据（round4本轮新鲜产出） |
|---|---|---|
| 1 代码存在 | ✅ | 生产C两版、RTL 16文件、host/preintegration/lab Python、机器源寄存器表齐备；哈希基线2236文件 |
| 2 自动测试 | ✅ | 寄存器--check PASS；预集成20 Python+312/34 RTL（`20260919_183125`）；统一门禁20通信+38主机+104/43/31/124/31/33/1326/114695/614400/12 RTL+7×8192px+307200px逐像素（`run_20260919_183821`）；DLL重建SHA=EF32FB8A…；变异存活0 |
| 3 综合 | ✅ | 六模块OOC综合WNS全正（本轮重跑：+5.273/+2.696/+2.367/+3.217/+2.367/+0.981）；框架综合WNS +4.446（161107） |
| 4 实现 | ✅ | 集成候选完全布线WNS +0.079/WHS +0.027/TNS/THS 0/0阻断DRC（`impl_final_session_20260919_094906.log`，无CRITICAL WARNING/坏时钟诊断） |
| 5 bit/hwh | 🟡 | LAB_ONLY bit/hwh已生成（db0200a7/b2d3783b，ZIP=fd813fdb…）——**仅限无电机台架**，非发布bitstream；发布bit被门禁阻止 |
| 6 实物 | ⛔ HARDWARE_PENDING | Overlay/MMIO、Pmod电气（5V Echo）、板卡修订版、UART≤300ms、C270、HDMI色序、CPR标定、30分钟稳定性、RISK_CMD写者 |

## 到板后按顺序必须完成的人工/实物项目

1. 电机物理断开确认（步骤1，拍照`01_motor_disconnected.jpg`）。
2. 板卡丝印/修订版与PA_v3/R12比对（步骤2）。
3. 电源/共地/电平转换逐路实测（步骤3-4；Echo>3.3V严禁直连）。
4. 只接超声/红外：`sensor-check`跑正常/fault1/fault2与IR 0/1/2/3（步骤5-6），按`baseline_pl_risk`+`risk_reason_changes`判读，不得以恒stop冒充。
5. 只接QEI手动转轮（步骤7），实测CPR后写SCALE。
6. 拔蓝牙接UART：`uart-stop --motor-disconnected`，核对新`$CAR`锁存与≤300ms（步骤8）。
7. ID/epoch/快照序列检查（步骤9，记录首次RISK_STATE基线）。
8. `safety-loop --motor-disconnected`注入四类故障（步骤10）。
9. 色条人工确认RGB顺序→C270 900帧性能（步骤11）。
10. `--duration 1800`联合稳定性（步骤12）。
11. 全部通过后：夜间D的MMIO版本/epoch门控复核→`check_ae_gate`→人工确认才谈发布bitstream；地面运动另需单独人工确认。
