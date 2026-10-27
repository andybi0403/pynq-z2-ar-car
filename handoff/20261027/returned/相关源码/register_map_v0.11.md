# 统一寄存器表 v0.11

由 `fpga/registers/register_map.json` 生成，禁止手工修改本表。

| 偏移 | 名称 | 访问 | 复位 | 说明 |
|---:|---|---|---:|---|
| 0x000 | ID_VERSION | RO | 0xC425100A | magic/type=integrated/version=0A; STM32 sensor injection supported |
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
| 0x0C0 | RISK_STATE | RO | 0 | bit0 stop; bits2:1 distance/control risk level; bits31:16 reasons. v0.11: reason bits5/7 are IR advisory-only; IR invalid/obstacle never affect stop, level or manual release |
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
| 0x148 | ODOM_CTRL | WO | 0 | bit0 reset both wheel odometers; starts new epochs |
| 0x200 | ODOM0_DISP_LO | RO | 0 | global snapshot signed 64-bit Q16.16 mm displacement low |
| 0x204 | ODOM0_DISP_HI | RO | 0 | global snapshot signed displacement high |
| 0x208 | ODOM0_PATH_LO | RO | 0 | global snapshot unsigned 64-bit Q16.16 mm travelled low |
| 0x20C | ODOM0_PATH_HI | RO | 0 | global snapshot travelled high |
| 0x210 | ODOM0_TS | RO | 0 | global snapshot last edge/reset/fault timestamp; stationary does not age |
| 0x214 | ODOM0_META | RO | 0 | global snapshot bit31 valid; bit30 sticky fault; bits15:0 sequence |
| 0x218 | ODOM0_EPOCH | RO | 0 | global snapshot bits15:0 reset/calibration/phase epoch |
| 0x220 | ODOM1_DISP_LO | RO | 0 | global snapshot signed 64-bit Q16.16 mm displacement low |
| 0x224 | ODOM1_DISP_HI | RO | 0 | global snapshot signed displacement high |
| 0x228 | ODOM1_PATH_LO | RO | 0 | global snapshot unsigned 64-bit Q16.16 mm travelled low |
| 0x22C | ODOM1_PATH_HI | RO | 0 | global snapshot travelled high |
| 0x230 | ODOM1_TS | RO | 0 | global snapshot last edge/reset/fault timestamp; stationary does not age |
| 0x234 | ODOM1_META | RO | 0 | global snapshot bit31 valid; bit30 sticky fault; bits15:0 sequence |
| 0x238 | ODOM1_EPOCH | RO | 0 | global snapshot bits15:0 reset/calibration/phase epoch |
| 0x280 | OSD_ERRORS | RO | 0 | OSD malformed SOF/EOL count, saturated |
| 0x284 | DISPLAY_CAR_STATE | RW | 0 | bit0 actual STM32 LOCK; bit1 received valid; bits31:16 STM32 fault; write commits age and time |
| 0x288 | DISPLAY_CAR_AGE | RW | 0 | UART reception age in 100MHz ticks, staged before STATE; display expires after total 700ms |
| 0x28C | DISPLAY_CAR_TS | RO | 0 | last STATE publication tick; publication must not renew same UART reception |
| 0x290 | DISPLAY_FRAMES | RO | 0 | accepted HDMI SOF count, wraps uint32; not decoded-camera frame identity |
| 0x2A0 | DISPLAY_FRAME_ID | RO | 0 | last metadata SOF accepted before OSD: decoded camera frame id |
| 0x2A4 | DISPLAY_FRAME_STATE | RO | 0 | bit0 valid metadata; bit1 age below 200ms and not future; bits31:16 associated snapshot epoch |
| 0x2A8 | DISPLAY_FRAME_TS_LO | RO | 0 | estimated decoded reception PL ticks low32, committed on metadata SOF |
| 0x2AC | DISPLAY_FRAME_TS_HI | RO | 0 | estimated decoded reception PL ticks high32 |
| 0x2B0 | DISPLAY_HEADER_ERRORS | RO | 0 | saturated malformed/missing metadata prefix count |
| 0x2B4 | DISPLAY_REPEATS | RO | 0 | uint32 repeated valid frame id plus reception timestamp count |
| 0x2B8 | DISPLAY_TAG_COUNT | RO | 0 | all accepted metadata-parser SOFs, diagnostic coherence counter |
| 0x2BC | DISPLAY_FRAME_AGE | RO | 0 | live age of committed reception in 100MHz ticks; uint32 saturation including future time |
| 0x2C0 | DISPLAY_FRAME_SOF_LO | RO | 0 | actual PL ticks when base OSD accepted last tagged SOF, low32 |
| 0x2C4 | DISPLAY_FRAME_SOF_HI | RO | 0 | actual PL tagged SOF acceptance ticks high32; not HDMI scanout |
| 0x300 | EXT_SENSOR_MODE | RW | 0 | bit0 selects STM32 UART sensors; mode writes revoke staged/live samples |
| 0x304 | EXT_US_DATA | RW | 0 | staged US distance low12, fault bits15:12 |
| 0x308 | EXT_US_AGE | RW | 0 | staged conservative US age at EXT_SENSOR_ANCHOR, 100MHz ticks |
| 0x30C | EXT_US_META | RW | 0 | staged valid bit31 and sample sequence low16 |
| 0x310 | EXT_IR_STATUS | RW | 0 | staged obstacle bits1:0, stable bit2 |
| 0x314 | EXT_IR_AGE | RW | 0 | staged IR periodic observation age at EXT_SENSOR_ANCHOR, 100MHz ticks |
| 0x318 | EXT_IR_META | RW | 0 | staged valid bit31 and observation sequence low16 |
| 0x31C | EXT_SENSOR_COMMIT | WO | 0 | full-strobe increasing transaction ID; all eight staged fields required, including 64-bit PL anchor |
| 0x320 | EXT_SENSOR_SEQUENCE | RO | 0 | last accepted atomic transaction ID |
| 0x324 | EXT_SENSOR_STATUS | RO | 0 | bit0 external mode, bit1 live US valid, bit2 live IR valid; sticky expiry |
| 0x328 | EXT_SENSOR_ANCHOR_LO | RW | 0 | staged PL time latch low32 taken BEFORE host calculates sample ages |
| 0x32C | EXT_SENSOR_ANCHOR_HI | RW | 0 | staged PL time latch high32; delayed or wrapped commits cannot rejuvenate samples |
