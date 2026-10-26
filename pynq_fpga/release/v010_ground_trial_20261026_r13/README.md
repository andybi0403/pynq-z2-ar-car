# AR 小车连接与稳定测试上位机

电脑双击 `console_launcher.html`，粘贴 PYNQ 本次启动链接后连接。
板端在解压目录执行 `chmod +x start_sensor_console.sh && sudo ./start_sensor_console.sh`。
默认 1800 秒；电机动力保持物理断开。

此版本修复登录键盘、请求超时、同地址新令牌不登录、重连竞争和断线残留显示。
提供诊断启动、真实编码器位置、联调报告导出与最终测试操作说明。
采集启动检查未通过时可进入诊断页面，但摘要仍为失败。

第一次部署先执行 `python3 deployment_check.py --board` 和 `python3 lab_acceptance.py contract`。
如无 ARM 原生库，执行 `cmake -S native -B native-build -DCMAKE_BUILD_TYPE=Release`，
再执行 `cmake --build native-build --parallel 2`。
所需依赖仍为 Python 3.10+、PYNQ、pyserial、aiohttp、ffmpeg、原生库构建依赖。
启动脚本使用板端 PYNQ 虚拟环境，先加载本包 Overlay 并恢复 UART1，再运行完整上位机。
默认电机动力断开；显式连接诊断可使用 `SENSOR_CONSOLE_MOTOR_MODE=connected-zero-output`，
该模式据实记录动力未断开，保持锁车和零输出，不作为台架验收或驾驶许可。
板间协议、接线、bit/HWH、STM32 固件沿用 r5/r3 基线。

详细的连接排错、短联调、30 分钟长稳与演示步骤见 `SENSOR_CONSOLE_GUIDE.md`。
原始基线说明见 `README_R3_BASE.md`。
本次是软件修复，实板结果 PENDING，仍为 LAB_ONLY_NO_MOTOR_NON_RELEASE。
