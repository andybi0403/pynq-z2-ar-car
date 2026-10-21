# ZCode只读审计问题处理报告

日期：2026-09-19。处理者：Codex。原审计证据目录`pynq_fpga/audit/zcode_20260919/`保持不改，本目录记录复现、修复和复验结果。

## 结论

- `AUD-02-01`：确认并修复。源切换现在立即废弃旧传感器快照和解锁计时，USB接管与回切USART2共用同一安全接口。
- `AUD-AP-01/02`：确认测试缺口并补齐。风险核从22项增至31项，M4和M6均被杀死；主机层新增QEI双路过期和IR stable失效断言。
- `AUD-06-01`：确认并修复。寄存器机器源拒绝重叠区域、重复区域名和反向范围。
- `AUD-18-01`：CLI原本已经拒绝`count<2`，所以“命令行可空PASS”的触发描述不成立；底层函数直接调用仍缺门禁，已按防御性修复并测试。
- `OBS-18-01/R1-F1/R1-F2/R1-F4`：不在本轮改变冻结协议、生产接线或显示语义，保留给下一轮只读复审和实板数据判断。

## 关键改动

1. `stm32_pynq对接版/Source/APP/safe_control.c/.h`新增`safe_source_handover()`；`safe_car.c`的两个源切换方向均调用它。DLL与模糊测试构建导出表同步更新。
2. C单测和真实DLL跨层测试加入源切换反例。历史`ce_arm_unlock.py`只用`safe_fault()`模拟旧实现，不能作为修复后的判定器；新的判定器是`ce_source_handover_fixed.py`。
3. `tb_car_risk_core.sv`加入QEI0/QEI1年龄恰等于阈值、恢复新鲜、IR stable失效与恢复；`test_perception_client.py`加入对应主机断言。
4. `generate_register_map.py`加入区域结构校验，并新增独立负向测试。
5. `lab_acceptance.py`的两个采样函数增加`count>=2`前置条件；LAB_ONLY已重打包。

## 复验结果

| 验证 | 结果 |
|---|---|
| 对接版`tests/run_tests.cmd` | PASS |
| 对接版`build_safe.ps1` | PASS；text/data/bss=`7772/84/3188` |
| 真实生产DLL跨层 | 16/16 PASS |
| 修复后源切换判定器 | PASS |
| 风险核RTL | 31/31 PASS |
| M4删除QEI0 stale | KILLED（工具以exit 1表示被测试发现） |
| M6删除IR stable检查 | KILLED（工具以exit 1表示被测试发现） |
| 寄存器生成与负向测试 | PASS |
| 主机感知客户端 | 8/8 PASS |
| 台架框架Python测试 | 18/18 PASS |
| `run_acceptance.ps1 -Synthesis` | exit 0；十套RTL仿真和六模块OOC综合通过 |
| release门禁 | 保持阻塞；未做实物声明 |

生产`safe_control.c` SHA-256：`EF32FB8A078FCA7FAF719377BCB728A908D450E8EF43A4BF2D85665E7BE365D3`。

统一门禁证据目录：`pynq_fpga/nightly/acceptance_20260918/run_20260919_134826/`；任务7/8隔离回归证据目录：`pynq_fpga/fpga/build/task7_8_tests/20260919_135726/`。

LAB_ONLY ZIP SHA-256：`ae1bd4e61234bebf638658e0bd4f6730c6e40c296b768eaf441b9b8b27af3bf9`；包内无`__pycache__`或`.pyc`。bit/hwh复用既有已实现产物，因为本轮未修改RTL、BD或XDC；主机脚本和manifest已重新打包。

## 保留项

- `$CAR`无校验和是V2.1双端一致的遥测协议设计；若升级必须定义V0.7兼容策略并同时改两端，不能在当前冻结协议上单边追加。
- PL风险核`RISK_CMD`的生产续租者需在PYNQ实板控制循环确定后验收。
- OSD平均轮速与风险最大轮速是显示口径问题，需要确定UI含义后再改。
- 快照读取耗时导致的保守年龄增加需要真实MMIO延迟数据，当前不放宽失效门限。
- Overlay/MMIO、Pmod电气、UART实链路、C270/HDMI、编码器CPR和30分钟稳定性仍为`HARDWARE_PENDING`。
