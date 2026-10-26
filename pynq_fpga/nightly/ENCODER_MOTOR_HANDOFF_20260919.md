# 编码器资料核定、电平转换与QEI参数修订交接（2026-09-19）

## 第一屏：已核实的电气结论

- **电机**：额定6V（建议3—9V）、额定200mA、堵转1.3A；1:48输出轴350rpm。编码器：AB相90°正交霍尔，**电机轴13线**，编码器电压**4.5V—5V**（手册P6参数表原文）。手册P9框图另标"编码器工作电压(5V、3.3V)"与参数表冲突，以参数表为准，3.3V供电未验证。
- **编码器板载上拉**：手册原文"编码器带上拉输出，单片机可直接采集"。只证明板上拉存在，输出级结构（推挽/裸开漏）厂家未给——对PYNQ按5V域高电平处理，A/B严禁直连PL。
- **计数**：x4合法跳变计数，输出轮一圈=13×减速比×4：1:48为**2496**、1:90为**4680**（手册P8原文）。13PPR在电机轴，不在轮轴。
- **PH2.0-6P针序**（手册P7图，自标签"电机线+"侧起）：电机线+、编码器负极、编码器B相、编码器A相、编码器正极、电机线-；中间四针从"电机线-"侧到"电机线+"侧为正极、A、B、负极。**实物线束颜色无标准，接线前必须逐针通断确认**。
- **例程佐证**：厂家STM32例程（C25 v5）用1:90/4680/60mm、TIM编码器模式TI12（x4）、浮空输入；Arduino例程（ard-end）用1:90/13线/65mm、双相CHANGE中断x4、INPUT_PULLUP。两份均为通用演示，不覆盖本项目配置。

## 推荐电平转换/上拉方案（首版两路）

编码器VCC接稳定5V（4.5—5V），编码器GND与PYNQ信号地单点共地；电机动力由TB6612供电，禁止从Pmod取电。A/B经**SN74LVC245A**（VCC=3.3V、输入5V容忍、DIR固定A→B、每片VCC-GND近端100nF去耦）进Pmod B 1—4；**PL侧XDC不启用PULLUP、不另加外部上拉**（板载上拉已存在）。实购器件必须确认完整料号SN74LVC245A或同等"3.3V供电、输入5V容忍"器件；74HC245/TXS/TXB/BSS138板不等价。`/OE`优先10k上拉到3.3V默认禁用+使能点拉低；硬接GND则必须在验收记录注明上电顺序限制。编码器5V先上电、PYNQ掉电/未配置、反向上电顺序均列为release实测项；未实测前`electrical_ready=false`、`release_ready=false`维持不变。Echo与红外既有方案未改动。

## 当前两只前轮的临时SCALE

- 用户已确认：**1:48减速比、原装轮胎未更换、双前轮编码器**（左前QEI0、右前QEI1，Pmod B 1—4）；65mm为手工粗测名义直径。
- 临时值：`QEI0_SCALE=QEI1_SCALE=5362=0x000014F2`（π×65mm/2496×65536，Q16.16）。**这是到货初测值/临时值**——65mm未带载标定、2496计数/轮未实物复核、转换前后电平未实测；不得写成精密标定PASS。
- 四组资料对照表（经独立脚本复算，单测覆盖）放附录A。

## 左右侧统一驱动关系（已固化为架构测试）

- TB6612只有左右两路：**同侧前后电机共用方向和PWM**；`safe_car.c`的`motors(left,right)`与`$P`帧L/R继续表示左右侧请求，安全锁存/制动/限幅同时作用于同侧前后轮。
- **前轮QEI即该侧速度观测**；后轮无编码器、无可观测性，不得宣称后轮单独打滑/堵转检测，不虚构QEI2/QEI3。
- 动态风险核以左右前轮速度较大值算前进制动距离（保守，保持不变）；任一路QEI无效/过期失效安全停车。
- 后电机真实减速比未被本资料证明；到货后须悬空测同侧前后轮转速差/电流/反向一致性，不通过换电机，不得用PID掩盖。

## 修改文件、测试命令与退出码

| 文件 | 改动 |
|---|---|
| `docs/03_硬件与接线/10_霍尔编码器TT马达电气与QEI参数核定_20260919.md` | **新增**：集中核定结论（资料位置/电气图/针序/四组SCALE/剩余实测项） |
| `docs/03_硬件与接线/09_编码器与正交解码器选型报告.md` | 废止13PPR轮轴假设与51Hz/0.5计数口径；1:48/1:90计数与板载上拉写实；已购1:48双前轮写实；"四轮全装"改历史扩展建议；v0.4/三选一候选改v0.6 |
| `docs/03_硬件与接线/08_红外超声波接PYNQ连接方案.md` | 删除"编码器/Echo/红外建议PULLUP true"；编码器改为板载上拉+LVC245+PL无PULLUP；Echo/红外各自结论未连带改写 |
| `pynq_fpga/fpga/board/board_electrical_review.md` | 编码器从"型号/输出未知"改为已核定参数+LVC245方案；release仍阻断 |
| `pynq_fpga/fpga/board/no_motor_acceptance.md` | 扩充步骤7a—7e（电平/手转10圈/悬空转速差/带载滚动周长/qei-config写SCALE）与落地直行、/OE记录要求 |
| `pynq_fpga/nightly/interface_contract.md` | QEI公式后补2496/4680与四组SCALE表；保留复位0与65536=1mm/count测试语义 |
| `pynq_fpga/fpga/board/board_manifest.json` | 仅更新QEI证据描述（左前/右前、LVC245、10号文档指向）；`electrical_ready/release_ready`保持false |
| `pynq_fpga/host/qei_calibration.py` | **新增**：纯软件SCALE计算器+四组命名预设，无MMIO |
| `pynq_fpga/host/tests/test_qei_calibration.py` | **新增**：预设复算、实测周长重算、非法输入、Q16.16解码误差、无硬件副作用 |
| `pynq_fpga/host/perception_client.py` | 新增显式`configure_qei_scales(left,right)`与`configure_qei_profile(name)`：先verify_contract，校验1—0xFFFFFFFF，写QEI0/QEI1生成地址并读回一致，否则ContractError；无构造/导入副作用 |
| `pynq_fpga/host/tests/test_perception_client.py` | 新增QeiScaleConfigTests：写地址顺序、左右独立、ID门、读回不一致失败关闭、临时5362、未知profile无写入、构造无写入 |
| `pynq_fpga/host/tests/test_architecture_invariants.py` | 新增TwoWheelEncoderArchitectureTests：safe_car.c仅left/right两路、无前后独立通道；RTL/寄存器表恰两路QEI；QEI0=左前/QEI1=右前与共用PWM已写入10号文档 |
| `pynq_fpga/preintegration/host/lab_acceptance.py` | 新增独立`qei-config`子命令：必须`--motor-disconnected`，显式`--qei-profile`或`--left-scale/--right-scale`，写后二次读回并出证据json；未混入sensor-check |
| `pynq_fpga/preintegration/tests/test_framework.py` | 新增qei-config CLI失败关闭测试（缺电机断开确认/缺参数/参数互斥/半参均exit=1；参数合法仍被包校验门拦下且不写证据文件） |
| `pynq_fpga/preintegration/build_lab_only.ps1` | 打包清单加qei_calibration.py；LAB_ONLY目录与zip已用`-SkipRegression -ReuseBitstream`重新生成（未触碰RTL/综合），包内副本与权威源diff一致 |
| `pynq_fpga/nightly/MORNING_HANDOFF_20260919.md` | 顶部加晚间批注：编码器输出类型一条已核定，指向10号文档（原文保留） |
| `pynq_fpga/nightly/ENCODER_MOTOR_HANDOFF_20260919.md` | 本报告 |

测试命令与退出码（Windows，Python 3.14）：

```text
python fpga/registers/generate_register_map.py --check   → REGISTER_MAP_PASS, exit=0
python fpga/scripts/validate_board_manifest.py           → BOARD_MANIFEST_PASS(21 ports; release=False), exit=0
python -m unittest discover -s host/tests  (pynq_fpga下) → Ran 58 tests, OK, exit=0
python -m unittest discover -s preintegration/tests      → Ran 21 tests, OK, exit=0
powershell build_lab_only.ps1 -SkipRegression -ReuseBitstream → TASK7_8_LAB_ONLY_PACKAGE_PASS, exit=0
  （含 BOARD_MANIFEST --release 反向校验 LAB_ONLY_RELEASE_GATE_CONFIRMED_BLOCKED、
    HWH_CONTRACT_PASS、LAB_CONTRACT_PASS、zip sha256=7a0ffc43…529b3c3）
独立脚本四组SCALE复算（tmp/enc_motor_20260919/）：4949/5362/2640/2860与十六进制逐一吻合
qei-config失败路径冒烟：缺motor-disconnected/缺参数/参数互斥/半参/scale=0/未知profile 全部拒绝（exit=1/2）
```

本轮只改文档、纯计算器、PS显式配置与测试，未触碰RTL、寄存器机器源与综合产物，故未运行`run_acceptance.ps1 -Synthesis`；LAB_ONLY包按构建脚本重新生成而非手改。

## 附录A：四组SCALE资料对照（独立复算，非复制）

| 减速比 | 轮径 | x4计数/轮 | SCALE十进制 | SCALE十六进制 | 性质 |
|---|---|---:|---:|---:|---|
| 1:48 | 60mm | 2496 | 4949 | `0x00001355` | 资料对照 |
| 1:48 | 65mm | 2496 | **5362** | `0x000014F2` | **当前profile临时值**（TT_48_ORIGINAL_WHEEL_FRONT_2） |
| 1:90 | 60mm | 4680 | 2640 | `0x00000A50` | 资料对照（厂家STM32例程口径） |
| 1:90 | 65mm | 4680 | 2860 | `0x00000B2C` | 资料对照（厂家Arduino例程口径） |

公式：`SCALE=round(loaded_rollout_mm/(13×gear×4)×65536)`；直径估算时`loaded_rollout=π×diameter`。生产复位SCALE=0=未标定无效，任何名义值不得成为RTL/寄存器复位默认值；5362只能由PS显式选择profile后写入。

边沿率：当前profile（1:48/65mm）20cm/s≈**2445Hz**，10ms窗口≈24.4计数；旧"51Hz/0.5计数"已废止；附录对照1:90/65mm≈4584Hz。手转10圈预期24960计数/路（1:48）。

## 剩余实测项（未测不得PASS）

手转10圈计数复核、左右带载滚动周长与重算SCALE、正反转符号/里程/风险输入验证、逐针通断、转换前后波形、三种上电顺序、/OE使能落地、同侧前后轮悬空转速差与落地直行。完整清单见10号文档第10节。

## 交给Codex复审的问题（原始记录；处理结果见下一节）

1. **`/OE`使能方式**：任务双向都允许（10k上拉默认禁用+使能点，或硬接GND+上电顺序限制入档）。转接板焊接前应定案一种；若用使能点，建议由PYNQ某可用GPIO或跳线控制——本任务未指定具体引脚，需要Codex从Pmod A余量脚（JA9/JA10=W18/W19）或板载跳线中给出推荐并确认不与扩展冲突。
2. **编码器供电来源**：推荐"PYNQ外5V轨或小车MVCC轨"尚未定案；Pmod B的3.3V/5V脚电流预算与上电时序需在接线图定稿时明确（手册只给4.5—5V）。
3. **QEI0/QEI1与左右物理轮的对应**：软件契约已固定QEI0=左前、QEI1=右前，但实物若把左前电机接到了Pmod B 3/4，正确做法是换线而不是改契约——是否需要在XDC/接线图中加一个"接反时只允许换线"的显式提醒，请Codex复核交接文档措辞是否足够。
4. **`configure_qei_scales`失败后的寄存器状态**：当前契约是"失败后状态未定义，调用方必须停止并重配/重载"。是否需要增加"写前读旧值、失败时尝试恢复"的回滚？本任务按最小失败关闭实现，未加回滚。
5. **65mm名义直径与原装轮胎的真实对应关系**：原车BST-4WD V4.5说明与轮胎规格资料中若有官方轮径，到货标定时应一并核对，确认粗测65mm的偏差方向。

## 2026-09-20 Codex复审结论

1. `/OE`已定案为**外部10k上拉到3.3V+JA9/W18控制**。PL未配置和同步复位期间保持高电平禁用，复位释放后才拉低；RTL、集成Tcl、XDC、板级manifest与TB已同步。禁止硬接GND。
2. 编码器5V已定案取自PYNQ Arduino POWER头**J7 pin 4的VCC5V0**；TUL R12第3页明确Pmod A/B电源脚均为VCC3V3，第4页标出J7 pin 4为VCC5V0。该电源只供两块霍尔编码器板，电机仍由TB6612供电；电压、电流和纹波仍须上板实测后才能把`electrical_ready`改为true。
3. 物理契约保持QEI0=左前、QEI1=右前；接反只换线，不改地址或软件含义。
4. 找到并修复“第二通道写入/读回失败后留下半配置”的真实缺陷。现在任一配置或稳定性校验失败都会尽力把两路SCALE清零并逐路读回；若清零也无法确认，错误会明确要求重载bitstream。未采用恢复旧值，因为旧值可能已经不可信。
5. 65mm继续只作临时值；左右轮最终SCALE必须来自各自带载滚动周长。计算器同时新增Q16.16结果范围检查，过小量化为0和溢出均拒绝。

独立复验：host 61项、preintegration 21项通过；`run_acceptance.ps1 -Synthesis`退出0，全部RTL仿真/像素比对及六模块OOC综合通过。LAB_ONLY包已在修复后重新生成；新增JA9 `/OE`的bitstream需由后续集成工程重建结果替换，实物电气项仍为`HARDWARE_PENDING`。
