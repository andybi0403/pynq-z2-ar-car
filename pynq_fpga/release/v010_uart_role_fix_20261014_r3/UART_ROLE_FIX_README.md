# 烧录与两板通信修复完成 · 2026-10-14

STM32修复版已写入并通过全128 KiB读回；用户将BOOT0恢复0后正常复位，正式PYNQ链路及超声波/红外进入PL均已实测通过。当前同版软件为`v010_uart_role_fix_20261014_r3`，FPGA bit/HWH复用r2的已验证产物，未改RTL或宣称新的整机布线结果。

## 已解决的问题

1. 密码输入：旧miniterm把命令/密码一次性转成CRLF，认证失败被误判为密码错误。等待sudo提示后逐项发送的方法实际以默认凭据通过，返回UID=0；不需要重置PYNQ账户或重刷SD镜像。
2. 烧录程序：修复4字节容量字段错误地用2字节unpack解析的问题；区分新复位ROM与已同步ROM，避免再次发送孤立0x7F破坏命令边界；使用压缩传输和独立上传/运行等待时间，去掉cat/EOF、回显标记误匹配。未知固件身份禁止擦除。
3. STM32：USART1/USART2独立缓存解析，由首个合法CRC Q1固定数据口；错误字节/调试活动不能抢占。停车在两口均有效，报告由实际数据口回传，上电继续锁车。
4. PYNQ：无回复时不再提交序号0空样本；仅清除有效位及采集基准，让首条真实回复建立样本序号。保留CRC、会话/请求匹配、采样年龄、重复/倒退拒绝和控制许可门禁。

## 实物与独立核验

| 检查 | 结果 |
|---|---|
| STM32写入 | 9240字节，擦除0～9页 |
| 全Flash读回 | 131072字节，电脑独立逐字节比对通过；其余Flash保持原备份 |
| 写入BIN SHA-256 | `8b043a342c839414f021bbd68700ddfac48113509577872ace9074bb806f4f2d` |
| 全读回SHA-256 | `d327416b36ca5dfbd6b25a3a1c2ea87876560b983fd19c86ceff61b535a97e02` |
| ROM GO后10秒 | 369条合法S1，全部LOCK=1、左右实际PWM=0 |
| 正常BOOT0=0、修复后正式链路60秒 | 窗口内920条合法回传；关闭时另收1条，原始流共921条，逐条CRC/请求配对通过 |
| 60秒PL采集 | 1103次快照；US/IR各1102次有效，均能按序号对应到实际UART样本 |
| 传输错误 | sensor_errors=0，transport_error=None；仅Q1/PSTOP |
| 高序号首样本回归 | 实际首IR低16位=36908（上半区），15秒内US/IR均276/276有效，无等待回绕 |
| 最终状态 | BOOT0=0已由用户复位；电机动力断开；STM32运行修复固件；PL风险许可0、双轮SCALE=0 |

修复前的反例保存在`normal_boot_acceptance_summary.json`：串口461条正常，但PL红外0/552有效。该失败记录保留；最终通过证据为`fixed_runtime_acceptance_summary.json`及`high_sequence_acceptance_summary.json`。

## 交付与重现

- 板端软件：`/home/xilinx/edge_console_v010_uart_role_fix_20261014_r3`，当前核验记录`/home/xilinx/current_verified_uart_runtime.json`。
- 电脑软件包：`pynq_fpga/lab/task7_8_lab_only_v010_uart_role_fix_20261014_r3`；包内STM32 BIN与已写入芯片的固件相同，旧r2保留作为历史基线。
- 烧录入口：`python work/uart_live_fix_20261014/upload_flash_via_pynq_console.py --authenticate`。密码在本机终端隐藏输入，不保存；需要BOOT0=1后RESET、当前COM14连接和电机动力断开。工具先读取当前全Flash，只有原备份或已验证目标身份才继续。完成后BOOT0恢复0并RESET。
- 原始备份：`before_uart_role_fix.bin`；新读回：`after_uart_role_fix.bin`；分别131072字节。
- 独立证据：`independent_flash_audit.json`、`fixed_runtime_independent_audit.json`、`high_sequence_independent_audit.json`；逐帧/快照审核工具`audit_uart_capture.py`。
- 回归：STM32 C安全/协议套件和6项ARM指令测试、PYNQ主机27项相关测试、ROM状态连接3项测试均通过。

本轮验收范围为烧录、正常启动、锁车双向通信及US/IR数据进入PL。LAB_ONLY仍维持电机动力断开，行驶及完整整车验收属于后续任务。

## PYNQ重启与日常启动入口

已备份并修正`/home/xilinx/stm32_sensors_platform_20261013/prepare_hybrid.py`和`start_hybrid.sh`，两者现指向r3；仅替换包目录，Python编译与shell语法检查通过。旧入口存于平台目录`startup_before_uart_role_fix_20261014`。

实际重启PYNQ后，系统自动登录。监测程序最初等待手动登录，超时记录保留；启动日志确认已正常启动。重启后`/dev/ttyPS1`确实尚未启用；运行更新后的prepare入口，重新加载同版Overlay和UART设备树，调试串口保持可用。随后30秒正式链路收到461条有效回传，协议错误0；552次PL快照中，US有效551次、IR有效551次。独立审核通过，最终LOCK=1、实际PWM=0、风险许可0、双轮SCALE=0。

证据：`startup_entry_update.json`、`pynq_reboot_automatic_login_proof.json`、`reboot_startup_entry_proof.json`、`reboot_independent_audit.json`。这是现有手动启动入口的重启恢复验证；没有新增上电自动运行服务。
