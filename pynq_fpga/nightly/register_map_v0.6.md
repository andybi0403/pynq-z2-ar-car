# 统一寄存器表 v0.6

由 `fpga/registers/register_map.json` 生成，禁止手工修改本表。

| 偏移 | 名称 | 访问 | 复位 | 说明 |
|---:|---|---|---:|---|
| 0x000 | ID_VERSION | RO | 0xC4251006 | magic/type=integrated/version=06 |
| 0x004 | CTRL | WO | 0 | bit0 global snapshot; bit1 64-bit time latch |
| 0x008 | STATUS | RO | 3 | bit0 snapshot done; bit1 time latch done |
| 0x00C | SNAP_EPOCH | RO | 0 | increments once per global snapshot |
| 0x010 | TS_LIVE_LO | RO | 0 | debug live time low |
| 0x014 | TS_LIVE_HI | RO | 0 | debug live time high |
| 0x018 | TS_SNAP_LO | RO | 0 | atomically latched time low |
| 0x01C | TS_SNAP_HI | RO | 0 | atomically latched time high |
| 0x020 | SCRATCH | RW | 0xA55A5A5A | WSTRB test register |
| 0x040 | US_DATA | RO | 0 | snapshot distance/fault |
| 0x044 | US_TS | RO | 0 | snapshot full 32-bit sample time |
| 0x048 | US_META | RO | 0 | bit31 valid; bits15:0 seq |
| 0x04C | US_ERR | RO | 0 | bits15:0 saturated error count |
| 0x050 | IR_STATUS | RO | 0 | bit0 left obstacle; bit1 right; bit2 stable |
| 0x054 | IR_TS | RO | 0 | snapshot full 32-bit change time |
| 0x058 | IR_META | RO | 0 | bit31 valid; bits15:0 seq |
| 0x080 | QEI0_POS | RO | 0 | snapshot batch position |
| 0x084 | QEI0_PERIOD | RO | 0 | snapshot edge period |
| 0x088 | QEI0_VEL | RO | 0 | signed Q16.16 mm/s |
| 0x08C | QEI0_TS | RO | 0 | snapshot full 32-bit sample time |
| 0x090 | QEI0_META | RO | 0 | bit31 valid; bits15:0 seq |
| 0x094 | QEI0_INFO | RO | 0 | direction/period/diagnostics |
| 0x098 | QEI1_POS | RO | 0 | snapshot batch position |
| 0x09C | QEI1_PERIOD | RO | 0 | snapshot edge period |
| 0x0A0 | QEI1_VEL | RO | 0 | signed Q16.16 mm/s |
| 0x0A4 | QEI1_TS | RO | 0 | snapshot full 32-bit sample time |
| 0x0A8 | QEI1_META | RO | 0 | bit31 valid; bits15:0 seq |
| 0x0AC | QEI1_INFO | RO | 0 | direction/period/diagnostics |
| 0x0C0 | RISK_STATE | RO | 0 | bit0 stop; bits2:1 level; bits31:16 reasons |
| 0x0C4 | RISK_REQUIRED_MM | RO | 0 | computed stopping requirement |
| 0x0C8 | RISK_TS | RO | 0 | risk evaluation time |
| 0x0CC | RISK_META | RO | 0 | bit31 valid; bits15:0 seq |
| 0x0D0 | CMD_STATE | RO | 0 | bit0 forward request; bit1 request valid |
| 0x0D4 | CMD_TS | RO | 0 | last command write time |
| 0x100 | US_CTRL | RW | 1 | bit0 enable |
| 0x104 | US_PERIOD | RW | 6000000 | idle ticks |
| 0x108 | US_MAX_ECHO | RW | 3000000 | single wait timeout ticks |
| 0x10C | US_TRIG_TICKS | RW | 1000 | trigger high ticks |
| 0x110 | IR_FILTER | RW | 5000 | stable filter ticks |
| 0x120 | QEI0_DIR | RW | 0 | bit0 direction invert |
| 0x124 | QEI0_FILTER | RW | 0 | AB stable ticks |
| 0x128 | QEI0_SCALE | RW | 0 | Q16.16 mm per wheel x4 count |
| 0x12C | QEI0_ZERO | RW | 10000000 | zero observation ticks |
| 0x130 | QEI1_DIR | RW | 0 | bit0 direction invert |
| 0x134 | QEI1_FILTER | RW | 0 | AB stable ticks |
| 0x138 | QEI1_SCALE | RW | 0 | Q16.16 mm per wheel x4 count |
| 0x13C | QEI1_ZERO | RW | 10000000 | zero observation ticks |
| 0x140 | RISK_CMD | WO | 0 | bit0 forward; bit1 valid; every write renews PL command lease |
| 0x144 | RISK_ENABLE | RW | 1 | bit0 enable; zero forces stop |
