# 9.19 ZCode夜间复核队列

今晚只提交一个长任务：

1. [ZCode两亿Token多轮对抗复核提示词](01_ZCode_两亿Token多轮对抗复核提示词.md)

建议在ZCode中选择最高思考并一次性粘贴全文。该任务已经内置20轮不同角度审计、追加变异/模糊循环、问题证据闭环和断点交接。ZCode被严格禁止修改权威项目，只能在独立审计目录提交问题、最小反例和建议修法，之后统一交给Codex处理。

当前没有PYNQ，所有实板项目必须保持`HARDWARE_PENDING`。ZCode完成后把`pynq_fpga/audit/zcode_20260919/FINAL_AUDIT.md`交回Codex复审。
