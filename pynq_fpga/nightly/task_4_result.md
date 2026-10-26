# 原任务4完成交接：双路QEI与PL周期法测速

2026-09-18 Codex接续ZCode半成品完成。状态：PASS（软件/RTL及模块综合候选），实物未测。

实现：car_qei.v、car_qei_velocity.v、car_qei_top.v。编码器结构参考固定AMDC快照；滤波、非法恢复、周期、速度和双路快照为本项目实现。前端直接复用verilog-axi。

本文件记录任务4完成时状态；当前开发以[契约v0.5](interface_contract.md)为准，QEI验证顶层ID=0xC4250405。SCALE=Q16.16 mm/轮轴x4计数，SHIFT保留必须0，0x170/184为100ms零速窗口；禁止使用原v0.3的M法乘移位公式。默认SCALE=0，无实物参数不产生有效速度。

PL速度=floor(SCALE×100MHz/相邻同向边沿周期)，64拍恢复除法，标定常数流水准备；有符号Q16.16 mm/s饱和。首次边沿、反转首沿、非法跃迁、过快周期与未配置无效；无边沿窗口完成发布0。双路全部元组一次触发锁存，各有seq/ts/valid，读期间不被新批覆盖。

验证：tb_car_qei 31项，tb_car_velocity 114项（独立SI数值模型，20种周期/标定/正负组合，时间戳跨32位边界、极值、配置中断与过快输入）。位置从0倒转跨FFFFFFFF再正转跨0；非零AB复位不虚构运动；滤波与非法跳变、双路同拍和WSTRB均验证。

综合：xc7z020clg400-1，100MHz，1767 LUT / 2297 FF / 4 DSP / 0 BRAM；OOC综合Setup WNS +2.367ns/TNS 0。未布局布线，未约束板级I/O延迟，不能据此声称上板稳定。
脚本：fpga/scripts/run_sim.ps1、synth_modules.tcl、run_acceptance.ps1。总验收及证据见[任务1—4报告](acceptance_20260918/任务1-4验收与修改报告.md)。

待实物确认：输出轮一圈完整x4 CPR、轮周长、相位/安装方向、信号电压/上拉、最大边沿率和滤波。首版两路，不含四轮、PID或打滑检测。瞬时机械反转/低速非匀速误差不能由理想仿真精度代替。

后续消费：CTRL.bit0触发→等done→读两路POS/PERIOD/VEL/TS/VALID_SEQ；核对valid和正确模位宽下的age。INFO是快照时诊断，不是速度批的方向标签；速度符号见VEL。集成后必须统一时基和地址。
