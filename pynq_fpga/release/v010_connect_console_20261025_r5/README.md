# AR 小车连接式完整上位机 r5

本包是 v0.10 的软件补丁，复用已经过完整构建的同一份 bit/HWH，新增先连接后进入操控的页面流程、STM32 hybrid-v3 链路诊断、左右红外、双轮编码器和可重置的传感器互联统计。电机输出仍被锁定为 LAB_ONLY 零输出台架。

## 使用前

- 电机动力线必须物理断开。
- STM32 使用包内 `stm32_hybrid_v3.hex`，BOOT0 正常运行时为 0。
- 板间 UART 为 `115200 8N1`，接线保持已验证方案：PYNQ JB9→K1.3、JB10←K1.4、公共地→K1.2、K1.1 不接。
- 超声波和红外由 STM32 采集；编码器继续经原转接 PCB 进入 PYNQ。
- PYNQ 需要 Python 3.10 及以上、PYNQ、pyserial、aiohttp、ffmpeg 和匹配的 ARM 原生视频库。

只读检查：

```sh
python3 deployment_check.py --board
python3 lab_acceptance.py contract
python3 -c "from pathlib import Path; from wireless_runtime import verify_wireless; verify_wireless(Path('lab_manifest.json'),Path('task7_8_LAB_ONLY.hwh')); print('HASH_PASS')"
```

第一次运行或原生库尚未编译时：

```sh
cmake -S native -B native-build -DCMAKE_BUILD_TYPE=Release
cmake --build native-build --parallel 2
```

## 启动完整上位机

```sh
chmod +x start_sensor_console.sh
./start_sensor_console.sh
```

默认运行 1800 秒并创建新的证据目录。终端会打印带本次会话令牌的浏览器链接：

```text
http://<PYNQ地址>:8080/#token=<本次随机令牌>
```

可选参数：

```sh
SENSOR_CONSOLE_DURATION=1800 \
SENSOR_CONSOLE_VIDEO_MODE=auto \
SENSOR_CONSOLE_EVIDENCE=evidence/full_sensor_run \
./start_sensor_console.sh
```

## 页面功能

- 1280×720 摄像头原图和真实 PL 处理图。
- STM32 Q1/S1 查询和回包计数、回包年龄、最近往返时间、CRC/会话错误。
- 超声波距离、年龄和有效性。
- 左红外 bit0、右红外 bit1、IR 位图和序列号。
- QEI0 左前、QEI1 右前编码器序号、有效位和速度寄存器。
- STM32 实际 LOCK、左右 PWM、FAULT 和 drop。
- 可重置的完整互联统计，明确指出还需遮挡哪侧红外或手转哪个车轮。
- 运行记录和验收摘要下载。

完整互联通过要求至少持续采样 10 秒，并观察到视频、STM32 回包、超声波、左右红外各自遮挡/移开、锁车零 PWM 和双轮编码器计数。这个结论只覆盖本次实际观察，不替代轮径标定、制动、HDMI 实屏或整车 release 验收。

## 文件

- `start_sensor_console.sh`：完整上位机启动入口。
- `wireless_runtime.py`：视频、PYNQ MMIO、STM32 UART 与网页服务。
- `wireless_page.html`：完整联调页面。
- `pynq_link.py`：STM32 hybrid-v3 协议与诊断。
- `system_runtime.py`：控制会话、实际状态和互联统计。
- `SENSOR_CONSOLE_GUIDE.md`：联调操作说明。
- `lab_manifest.json`：同源哈希、复用的 bit/HWH、STM32 固件和软件补丁身份。
- `README_R3_BASE.md`：原始 r3 基线说明，供追溯。

当前 `lab_manifest.json` 中 `sensor_console.hardware_result` 为 `PENDING`。软件回归和页面布局验证已经通过，实板传感器互联结果由使用者现场完成。
