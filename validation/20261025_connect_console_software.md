# 连接式完整上位机 r5 软件验证

日期：2026-10-25

交付物：

- 运行目录：`pynq_fpga/release/v010_connect_console_20261025_r5/`
- 下载包：`pynq_fpga/release/v010_connect_console_20261025_r5.zip`
- 包 SHA-256：`817bf81a7a42837149a450d489e0e41f8a3056461b95fc346dbace6e11fa3a54`
- 候选记录：`pynq_fpga/preintegration/sensor_console_candidate.json`

## 页面流程

1. 打开基础地址时先显示连接页面。
2. 可填写 PYNQ 地址并粘贴本次启动链接中的 token。
3. 也可直接粘贴完整启动链接。
4. 验证成功后在浏览器写入 HTTP-only 会话 Cookie，并进入操控界面。
5. 直接打开带 `#token=` 的启动链接会自动登录。
6. 点击“断开连接”、令牌失效或服务重启后回到连接页面，旧视频和旧传感器数据不会作为在线数据保留。

页面仍是标准 HTML，但视频、状态、控制和日志都来自 PYNQ Web 服务，因此不能脱离 PYNQ 作为普通本地文件运行。

## 已执行检查

| 检查 | 结果 |
|---|---|
| 预集成完整测试 | 163 项 PASS |
| STM32 hybrid-v3 链接测试 | PASS |
| 页面 JavaScript 语法 | PASS |
| 手动输入 token 连接 | PASS |
| 启动链接自动登录 | PASS |
| 断开连接清除 Cookie | PASS |
| 桌面连接页 1280×900 | PASS，无横向溢出 |
| 移动连接页 390×844 | PASS，无横向溢出 |
| 原操控页面响应式布局 | PASS |
| `lab_acceptance.py contract` | PASS，契约 `0xC425100A` |
| wireless 文件与 manifest 哈希 | PASS |
| portable ZIP | PASS，86 个文件 |

截图：

- `work/sensor_console_20261025/connect-desktop.png`
- `work/sensor_console_20261025/connect-mobile.png`
- `work/sensor_console_20261025/desktop.png`
- `work/sensor_console_20261025/mobile.png`

## 验证边界

本轮只验证连接界面、登录跳转、退出和原上位机页面，不加载 FPGA、不打开实板 UART、不操作电机。运行包继续复用 r3 已验证的 bit/HWH 和 STM32 固件，`hardware_result` 保持 `PENDING`。
