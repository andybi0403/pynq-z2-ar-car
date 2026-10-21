# PYNQ-Z2 早期 SD 启动验证

成功完成早期启动时，预期 DONE 与 LED0 常亮，LED1–3 熄灭。点灯逻辑没有时钟、按键或开关输入。

BOOT.BIN 由官方 v3.0.1 的原始 FSBL 载荷、新生成的静态点灯 bitstream 和一个 ARM 空循环组成。官方 BootROM 头和 FSBL 载荷保持逐字节一致；原载荷只封装为 Bootgen 可接受的单 LOAD 段 ELF。应用入口为 DDR 0x00200000，符合 AMD 要求的入口高于 1 MiB。

Vivado 已完成综合、布局布线和 bitstream 生成。DRC 无错误，保留 ZPS7-1 警告：这是仅含 PL 点灯输出的诊断设计，PS 初始化由保留的官方 FSBL 执行。Bootgen 成功生成并读取三个分区；独立检查通过头/分区校验和、FSBL 身份、PL 完整配置载荷及应用入口检查。详见 output/verification.json。上述均为离线证据，实板待验证。

apply_to_sd.py 对已识别的 32 GB 学校卡操作：校验现有 v3.0.1 启动文件及 47 个项目文件，备份当前 BOOT.BIN，仅临时替换该文件，然后直接读回 FAT 分区核对并尝试弹出。Linux 分区、其他启动文件和项目文件保留。测试期间不启动 Linux、网络或小车应用。--restore 可恢复备份同版的原始启动文件，仍执行核对与读回。

灯亮可支持“SD 早期启动、FSBL 至 PL 配置路径以及 LED0 输出已工作”；不代表 Linux、项目或运动验收通过。灯不亮仍可能停在 BootROM/读卡、FSBL 的 PS/DDR 初始化或 PL 配置阶段，不能单凭结果断言具体器件损坏。

依据：[AMD FSBL 启动顺序](https://docs.amd.com/r/en-US/ug821-zynq-7000-swdev/First-Stage-Bootloader)、本地厂家 PYNQ-Z2 master XDC、官方 v3.0.1 镜像。
