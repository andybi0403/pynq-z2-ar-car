# FINAL_AUDIT_ROUND4：交付前最终全流程只读审查

日期：2026-09-19。审计员：ZCode。全部证据在`pynq_fpga/audit/zcode_round4_final_20260919/`。

## 第一屏结论

1. **新发现P0/P1/P2：0 / 0 / 0**。本轮所有验证（新鲜证据链、协议边界电池15/15、主机四变异4/4 KILLED、RTL两新变异KILLED、五条门禁、篡改矩阵11类、文档扫描9命中全为合理用法）均未发现新的真实问题。
2. **前三轮全部问题独立复验关闭**：P1×1（AUD-02-01）+P2×9全部CLOSED_VERIFIED；第三轮观察项OBS-R3-01（综合证据统一到`20260919_161107`+防回退测试）与OBS-R3-02（Vivado cwd Push/finally-Pop+假Vivado实验）均实测关闭。deferred四项与硬件项按规则维持。
3. **存活变异：0**。round4新增：主机V1版本检查移除/V2 epoch复核移除/V3 PS时间替换PL时间/V4 IR置V=0→全部被现有32项套件FAILED；RTL R1快照漏锁US组→KILLED(4 errors)、R2 epoch提前递增→KILLED(2 errors)。历史变异（C 12、D1-D4、前提4、风险核M1-M11+T1b）回归全KILLED。审计脚本自身3处错误（校验和剥位/漏逗号/E3标签）在审计目录内自修并记录，未计入产品问题。
4. **五条门禁真实退出码**：寄存器`--check`=0；`preintegration -Vivado -Synthesis -RequireAEBlocked`=0（`20260919_183125`，WNS +4.446）；`run_acceptance.ps1 -Synthesis`=0（`run_20260919_183821`，DLL重建SHA=EF32FB8A…，20+38 Python，104/43/31/124/31/33/12+1326/114695/614400 RTL，7×8192px+307200px逐像素）；包`contract`（`python -B`）=0且权威交付目录0个`__pycache__`；`validate_board_manifest.py --release`=**1（预期阻塞）**。
5. **LAB_ONLY ZIP真实哈希=`fd813fdb509d252d703e3bb5741ffbbf5683eac594679a866f35a05d54c0a29e`**——ZIP/sidecar/交接文档三方一致；15项无缓存无绝对路径；包内脚本与权威逐字节同；manifest与bit/hwh哈希字节数一致。
6. **权威树零修改：已确认**（2236→2255：0删除；19新增全为`run_20260919_183821`证据目录；8变更全为编译产物且源文件不变；6个开源快照commit逐一与登记相等——见`zero_modification_check.md`）。
7. **release为何仍阻塞**：`--release`真实退出码1——10个外接信号电气确认（qei0_a/b、qei1_a/b、us_trig、us_echo、uart_txd、uart_rxd、ir_l_raw、ir_r_raw）与实物板卡修订版确认缺失；属设计预期，非缺陷，本审计未触碰。
8. **离线交付结论：`OFFLINE_READY_FOR_HARDWARE`**——代码/测试/综合/实现/bit/hwh五层离线证据齐备且新鲜，无未闭环缺陷；实物层待板。
9. **到板顺序**：见`release_readiness_offline.md`（电机断开→修订版→电源/电平→超声红外→QEI标定→UART STOP→快照基线→safety-loop→色序→C270→1800s稳定性→夜间D MMIO复核→人工确认才谈发布bit）。

## 三、第三轮观察项收口复验（本轮实测）

- **OBS-R3-01**：`verification_20260919.json`的`software_rtl`与`synthesis`均指向`task7_8_tests/20260919_161107`；该目录含20项Python、312/34项RTL（xsim_console.log实测计数）、create/check/synth日志对；synth.log含`PREINTEGRATION_FRAMEWORK_SYNTH_PASS`与`WNS_NS=4.446`，无三类坏时钟诊断。**篡改矩阵5/5**（临时副本树+真实证据目录复制）：pristine OK；指向旧034333日志/不存在目录/删除synthesis键/软件综合分目录→全部FAILED。相对路径按测试文件位置（ROOT=parents[1]）解析，与cwd无关。
- **OBS-R3-02**：两脚本所有Vivado调用均在`Push-Location`+`try/finally{Pop-Location}`内（run_acceptance L61-73、preintegration L22/41/54/64）；外层`finally{Stop-Transcript}`。**假Vivado实验**（脚本副本+注入exit 1的vivado.bat）：exit 1、`throw 'Vivado framework creation failed'`、无`TASK7_8_PREINTEGRATION_PASS`、无AE PASS。本轮两条长门禁后FPGA根目录无`retry_open_fs.log`/`.Xil`残留。
- **隔离工程vs生产集成工程**：框架WNS 4.446与占位34项只用于隔离框架回归；生产核接入由`integrated_verification_20260919.json`（car_system@0x43C00000、无stub、完全布线+0.079/+0.027）单独证明，二者未混用。

## 四、STM32固件全审查（对接版+演示版分别对待）

- **pnum/帧解析**：round4边界电池15/15——内嵌NUL、非ASCII、无终止符、空字段、恰好18/29字节、30字节拒、5位PWM=99999解析（输出经DRIVE_RAW限幅±2400）、6位拒、负零=0、前导+、前导零距离09999=9999、10000拒、坏帧不刷新sample_ms/command_ms/clear_tracking。
- **校验和三方一致**：C `safe_pframe`求和范围（'$'..N，不含N后逗号）＝`pynq_link.checksum`＝协议V2示例；手算`$P,1200,1200,1,0888,0,0`=**0x6B**与C注释/文档示例`6B#`一致。校验失败仅`safe_fault(FAULT_FRAME)+drop_count++`，不刷新样本/租约/解锁跟踪（E12实测）。
- **两版互串**：对接版要求IR字段（演示版7字段帧在N后缺逗号→`p[i]!=','`拒）；演示版对8字段帧`i!=n-4`拒；拒绝后两版均FAULT_FRAME+锁存+不刷新租约——round1 fuzz 13万+round2 Python 6万输入与本轮边界电池互证。
- **时间语义**：`>=`恰阈值（20ms缩放TB：US age exact/lease exact）、前后、0xFFFFFE00回绕用例、1000ms USB空闲回切——C单测/DLL矩阵全绿。
- **源切换/解锁/距离回差**：D3/D4在C+真实DLL两层被杀（round3，round4复用证据）；9时间线矩阵+恢复路径（round2）未回退；回差180→240→260推演（≤200屏蔽正向、200-250保持、≥250恢复，负向保留）与TB6612真值表（IN1=IN2=H短刹、PWM=|v|、锁存即brake）一致，无失控正转路径。
- **ISR竞争表**（代码级）：`serial_irq()`写`rx[head]`(数组)+`rx_head`(volatile u8, 写后memory barrier)、`usb_owner/usb_byte_ms`(volatile)、`rx_handover/rx_handover_head`、`rx_error`；主循环在`irq_save/irq_restore`内读改`rx_tail/rx_handover`，SPSC环形缓冲127有效字节，溢出/半帧/切源尾帧（`frame_len=0`+`rx_tail=boundary`）均有处理；SafeControl字段仅主循环访问（`safe_source_handover`亦然）。ISR重入由PRIMASK关中断窗口+单字节入队避免。
- **启动文件**：向量表59项——[0]=栈顶、[1]=Reset（data拷贝+bss清零+SystemInit+main）、[15]=SysTick、[53]=USART1(16+37)、[54]=USART2(16+38)，其余→Default_Handler→safe_panic；构建脚本唯一`stm32_pynq*`目录断言+SHA双向校验。演示版未误改（0处新接口引用）。

## 五/六/七：PL、OSD、PS层

- 寄存器`--check` PASS；区域校验七类负向（round3）维持；生产顶层单时基/单AXI/单快照（架构不变量4项+HWH契约）。
- 新RTL变异：快照漏锁US组→KILLED（"US same snapshot got=0 want=0x3e8"）；epoch提前递增→KILLED（"snapshot epoch got=3 want=1"）——33项TB的组完整性与epoch语义真实载荷。
- 主机四变异全杀：版本检查移除（verify_contract）、epoch复核移除（snapshot after==epoch）、PS时间替换PL时间（evaluate_snapshot输入）、IR置V=0（snapshot_to_link_sample）——"record/replay同一生产解析路径、IR保留FAULT_IR来源"由同套件守护。
- OSD/视频/带宽：1326/114695/614400来自真实RTL输出+PNG由XSim输出生成（round1-3已核）；带宽账目清晰（DDR侧4字节BGR0 36.864MB/s×4搬运=147.456MB/s；27.648MB/s仅为3字节有效像素说明值）；C270仅认`046D:0825`、缺设备/PYNQ包非零退出。

## 八/九/十/十一

- XDC 21端口与官方XDC逐脚一致（round1实测）、板卡修订版未确认→release阻塞。
- LAB_ONLY供应链见第一屏第5条；七阶段无非零运动/PREL/伪造硬件路径（round2/3 fake矩阵）。
- 开源合规与竞赛合规详见`open_source_compliance_final.md`；文档一致性详见`document_consistency_final.md`。

## 证据索引

- `logs/gate_acceptance_synth.log`、`logs/gate_preintegration.log`（本轮原始门禁输出）
- `counterexamples/`：round4_protocol_edges.py(+output)、round4_interleave.py不在本目录（round3）——round4新增如上；zip3矩阵、hwh_cases、probe_risk_layout见round3目录（round4引用）
- `mutation/`：本机主机四变异与RTL R1/R2的运行记录（本文件内联+issue_ledger_round4.json）；round2/3目录的历史变异脚本继续有效
