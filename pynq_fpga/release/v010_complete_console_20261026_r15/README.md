# PYNQ AR 小车完整控制台 r15

完整页面整合驾驶总览、原图与真实 PL 图、同帧冻结、传感器与双轮标定、
手动操控、实际执行反馈、记录导出与历史回放、六阶段演示流程。
电脑双击 `desktop/打开完整控制台.pyw`（需 Python 3.10+ 和 Edge），
先打开本地完整界面，由操作者点击连接助手后才联网；连接助手另需 paramiko。
包内 `desktop/使用说明.md` 说明完整流程，工作区桌面程序为 `tools/open_car_console.py`。

此包为配套板端完整服务，未部署、未进行本包实车验收。
沿用已核验的 bit/HWH/STM32 固件，仅更新软件；文件身份见两个 manifest。
`lab_manifest.json` 保留原台架入口的身份和分类，完整控制服务另由
`console_manifest.json` 绑定，不表示已有整车驾驶 release。

板端依赖及 native 库检查沿用 SENSOR_CONSOLE_GUIDE.md。
启动完整服务：`sudo sh start_console.sh`。默认记录动力连接、仅观察并保持锁车，
不自动解锁；需要有效实测标定、新鲜感知与实际锁车反馈后才允许手动接管及解锁。
动力物理断开后可用 `SENSOR_CONSOLE_MOTOR_MODE=disconnected sudo -E sh start_console.sh`，
也可在仅观察模式据实更新动力状态后应用标定。
PWM 上限 400，连续单次动作上限 1 秒；超时、松手、失焦和断链停车。
默认会话 1800 秒，视频保留；硬件异常不会以假速度或假里程代替。

旧 `start_sensor_console.sh` 仍为只观察、零输出的台架入口。
完整功能与本地验证见包内 validation/20261026_complete_console_r15.md。
