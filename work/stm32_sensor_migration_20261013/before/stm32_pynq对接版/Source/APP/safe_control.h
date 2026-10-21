#ifndef SAFE_CONTROL_H
#define SAFE_CONTROL_H
#include <stdint.h>
#include <stddef.h>

/*
 * PYNQ 完整对接版：超声波与红外全部接在 PYNQ 板上，STM32 不再直接
 * 测量任何传感器。距离、距离有效性和红外位图都由 PYNQ 的 $P 驱动帧
 * 上报，STM32 只负责执行驱动输出和独立安全兜底。
 *
 * 所有距离单位是 mm，时间单位是 ms，PWM 是底盘原程序使用的比较值。
 * STOP 和 RELEASE 不取同一个值，是为了形成“回差”：
 * 距离小于 200 mm 时只禁止前进，恢复到 250 mm 以上才解除前进限制，
 * 避免物体刚好在临界值附近时前进输出反复启停。后退和转向仍可用于脱离障碍。
 */
#define SAFE_STOP_MM 200u
#define SAFE_RELEASE_MM 250u
#define SAFE_CLEAR_MS 300u
/*
 * PYNQ 按 100 ms 周期发送 $P 帧。两个阈值构成双保险：
 *   数据年龄 200 ms（约 2 帧）内没有“距离有效”的新数据 → 传感器故障锁车；
 *   运动租约 250 ms（约 2.5 帧）内没有任何有效 $P 帧 → 通信故障锁车。
 * 数据年龄先于租约触发，因此任一通道静默都会在 250 ms 内停车。
 */
#define SAFE_SENSOR_AGE_MS 200u
#define SAFE_COMMAND_MS 250u
#define SAFE_MAX_PWM 2400
/*
 * USB 诊断口接管后的自动释放时限：接管期间且处于停止状态、连续
 * 1000 ms 没有任何 USB 字节，则自动交还 USART2（交还动作本身锁车，
 * 新控制源必须重新走解锁流程，因此不会产生意外运动）。
 * 没有这条规则时，PC 调试后拔掉 USB 线，USART2 的字节会被永久丢弃，
 * 小车表现为"没有任何反应"，且 $BT# 只能从 USB 端发出，无法自救。
 */
#define SAFE_USB_RELEASE_MS 1000u

/* 蓝牙协议中的运动命令。数值顺序与原车协议保持一致。 */
enum { STOP=0, FORWARD, BACKWARD, LEFT, RIGHT, SPIN_LEFT, SPIN_RIGHT };

/* PYNQ $P 帧直接给定左右轮 PWM，跳过方向命令映射。 */
enum { DRIVE_RAW=7 };

/*
 * reason 是一个位掩码，一个字节可以同时记录多个故障来源。
 * 例如 FAULT_IR | FAULT_LINK 表示既检测到红外障碍，又失去了通信。
 */
enum { FAULT_START=1, FAULT_IR=2, FAULT_DISTANCE=4, FAULT_SENSOR=8,
       FAULT_LINK=16, FAULT_FRAME=32, FAULT_MODE=64 };

typedef struct {
    uint32_t sample_ms;    /* 最近一次 PYNQ 上报“距离有效”的时间 */
    uint32_t command_ms;   /* 最近一次有效运动指令的时间 */
    uint32_t clear_ms;     /* 障碍消失后开始连续确认的时间 */
    uint16_t distance_mm;  /* 最近一次 PYNQ 上报的前向距离 */
    uint8_t ir;            /* 红外位图：bit0 左，bit1 右，1 表示检测到障碍；来自 $P 帧 */
    uint8_t valid;         /* 最近一次 $P 帧的距离有效性标志 */
    uint8_t clear_tracking;/* 是否正在等待安全距离保持稳定 */
    uint8_t latched;       /* 锁存停车标志，1 时任何运动命令都输出为停止 */
    uint8_t distance_blocked; /* 前方过近时为 1，只屏蔽正向输出 */
    uint8_t command;       /* 当前请求的运动方向 */
    uint8_t reason;        /* 故障位图，供串口报告和屏幕显示 */
    int speed;              /* 当前 PWM 幅值，仍需经过上下限保护 */
    int left_req;          /* $P 帧请求的左轮 PWM */
    int right_req;         /* $P 帧请求的右轮 PWM */
    uint16_t drop_count;   /* $P 帧校验失败累计，经 $CAR 帧回传 PYNQ */
} SafeControl;

/* 以下函数只处理数据和状态，不直接操作 GPIO，便于仿真和单元测试。 */
void safe_init(SafeControl *s);
void safe_tick(SafeControl *s, uint32_t now);
void safe_fault(SafeControl *s, uint8_t reason);
/* 控制源切换必须废弃旧源的传感器快照与待执行请求。 */
void safe_source_handover(SafeControl *s);
/* 原车十字段蓝牙帧：仅保留给 USB 诊断口的 $ARM# 路径和兼容测试。 */
int safe_frame(SafeControl *s, const char *p, size_t n, uint32_t now);
/* PYNQ 驱动帧：本固件唯一的常规控制入口。 */
int safe_pframe(SafeControl *s, const char *p, size_t n, uint32_t now);
void safe_outputs(const SafeControl *s, int *left, int *right);
#endif
