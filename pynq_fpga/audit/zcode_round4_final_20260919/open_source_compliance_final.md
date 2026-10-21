# open_source_compliance_final：开源许可与竞赛合规终审

日期：2026-09-19（round4）。方法：逐行核对`OPEN_SOURCE_USAGE.md`↔本地快照git HEAD↔许可证正文↔实际采用文件。

## 复用清单核对（round4实测）

| 模块 | 上游与commit（本地git实测） | 许可证正文 | 采用方式 | 核对结论 |
|---|---|---|---|---|
| AXI-Lite前端 | alexforencich/verilog-axi `516bd5d` | MIT文件头（3文件均含Alex Forencich声明） | 原样编译（从快照路径直接加入工程，无副本漂移；round1已证`fpga/rtl`无第二副本） | ✅ |
| 原子快照/编码器结构参考 | AMDC-Firmware `5cf9769d`（sparse） | BSD-3-Clause（LICENSE.md在位） | 参考结构独立实现，未复制代码 | ✅ |
| 板级IP（axi_dynclk/rgb2dvi/TMDS接口） | Xilinx/PYNQ `e054c09c`（含boards/ip/if） | BSD-3-Clause（LICENSE在位） | IP随工程编译+调用官方驱动，Tcl重写 | ✅ |
| 超声波结构参考 | yunkai1841/HC-SR04-FPGA `f4df022d` | CC0-1.0（LICENSE在位） | 结构参考+补同步/超时/有效期 | ✅ |
| OSD字符寻址参考 | projf/projf-explore `dd212c2e` | RTL MIT（根LICENSE在位）；Unifont字体OFL例外未复制 | 参考`draw_char.sv/get_glyph_line.sv`思路；字模为自制16槽`.mem`单一源 | ✅ |
| Sobel仓库 | aclich `71a4409d` | **无LICENSE** | 仅行为/目录参考；仓库内无.v/.sv/.ipynb可复制（round1/round4两度实测find为空） | ✅ |

## 合规要点

- 6个固定commit与登记逐字相等（`third_party_commits.json`）；无重新许可、无虚称上游测试通过（上游cocotb TB未运行已在登记"未核实事项"中声明）。
- GPL/无许可候选（Sobel、fpga4fun）未并入交付；Derek-X-Wang与verilog-axis无本地快照，登记为"未采用"——与实际一致。
- NOTICE/许可随快照保留于`third_party/`；交付物（LAB_ONLY ZIP）内不含第三方源码，仅本项目自研脚本+自产bit/hwh。

## 竞赛合规（"检测在PS、叠加在PL"不构成FPGA仅搬运）

PL承担且代码/仿真/综合可证的不可替代实时任务：
1. HC-SR04 10µs Trig生成+Echo脉宽100MHz计数（`car_ultrasonic.v`）；
2. 双路正交解码x4+非法跃迁重同步+周期法测速64拍除法（`car_qei*.v`）；
3. 64位时基、多传感器独立时间戳/序号、单屏障原子快照（`car_time_counter/perception_top`）；
4. 四级流水风险融合（刹停距离定点倒数、14原因位、失效即停，`car_risk_core.v`）；
5. 纯AXIS背压OSD（SOF状态提交、double-dabble、帧同步诊断，`car_axis_osd.v`）。
PS侧仅做UVC取流/缩放/BGR0打包与UART桥接——检测/测距/决策/叠加的实时核心均在PL，符合赛道对FPGA实时角色的要求；演示文档（README/任务8）按此表述，未把PS工作冒充PL。

评分项覆盖：基础5条（UART协议+安全锁存+超声+红外+驱动）✅离线证据齐；拓展5条（QEI测速+风险融合+OSD+视频链路+回放）🟡实物待验；100分项中检测DPU按方案明确不做。排期/分工/命名与`status.md`一致，未把未上板候选写成完成产品。
