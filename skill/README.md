# 本次 FPGA 项目的可复用技能包

制作日期：2026-10-01，代码检查与发布基线更新于2026-10-21。技能：[AMD / PYNQ 项目制作全流程](amd-pynq-project-workflow/SKILL.md)，调用名 `$amd-pynq-project-workflow`。

本目录响应本地 AMD 选题指南 §3.3.5.2 对适用范围、使用方法、失效条件和失败来源的要求。覆盖此次项目从选题、底盘调试、采购/硬件、RTL、PS、视频、控制到验证、交付与复盘的全部阶段。未来硬件验收部分是可执行方法，当前结果仍待测。

## 使用方式

- Codex：将整个 `amd-pynq-project-workflow` 文件夹作为个人 skill 使用。示例：`用 $amd-pynq-project-workflow 盘点这个 PYNQ 工程现在能交付到哪一步，并推进最先缺失的环节。`
- 陌生队伍：先读 SKILL.md，再按任务读取分项指南；用自己的板卡、工具链、接口和验证数据替换案例参数。包内只读脚本专用于此次工程的 manifest 格式，其他工程不应直接运行。
- 本项目：完整PL候选从 `pynq_fpga/preintegration/latest_candidate.json` 定位；当前发布和实板证据从 `release_manifest.json` 定位；完整重建从 `pynq_fpga/preintegration/COMPLETE_BUILD.md` 进入。

只读检查：

```powershell
python skill/amd-pynq-project-workflow/scripts/inspect_release.py --project-root .
python skill/amd-pynq-project-workflow/scripts/inspect_candidate.py --project-root .
python -m unittest discover -s skill/amd-pynq-project-workflow/scripts -p "test_*.py" -v
```

## 验证效果与边界

已验证实践包括最小串口隔离诊断、生产 C 控制故障回归、RTL/像素参考比较、寄存器版本拒绝、来源绑定、软件/MCU补丁发布审计及独立整机布线。2026-10-21当前源码回归包含2套STM32 C测试、7项ARM串口角色测试、28项PC链路、150项主机测试、161项预集成测试、15项故障场景、20项RTL仿真和像素比对。对应来源和观察见[项目索引](amd-pynq-project-workflow/references/project-map.md)与[复盘账本](amd-pynq-project-workflow/references/retrospective.md)。新写的流程改进和提示词没有据此声称被陌生队伍实际复现。

结构和脚本验证记录见 [本次检查结果](validation.json)。当前整个作品仍为 LAB_ONLY，实板分项、标定、停车时延、显示色序及1800秒联合验收未完成；完成本技能包不等于完成小车。

当前技能压缩包：[amd-pynq-project-workflow_20261021.zip](amd-pynq-project-workflow_20261021.zip)，SHA-256 `7d2f0fb3d91659e524ff20b306840ec76552088f8a8177be4b75b215923cb63c`。

不能直接复用：PYNQ-Z2 引脚到其他板卡、历史串口格式到新固件、名义轮径到实测标定、旧 bit/HWH 到新运行程序，以及校赛要求到 AMD 全国赛全部规则。没有电气/机械证据时保持待验证。
