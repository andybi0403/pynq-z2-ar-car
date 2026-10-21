#ifndef SAFE_CONTROL_H
#define SAFE_CONTROL_H
#include <stdint.h>
#include <stddef.h>

/*
 * 所有距离单位是 mm，时间单位是 ms，PWM 是底盘原程序使用的比较值。
 * STOP 和 RELEASE 不取同一个值，是为了形成“回差”：
 * 距离小于 200 mm 时只禁止前进，恢复到 250 mm 以上才解除前进限制，
 * 避免物体刚好在临界值附近时前进输出反复启停。后退和转向仍可用于脱离障碍。
 */
#define SAFE_STOP_MM 200u
#define SAFE_RELEASE_MM 250u
#define SAFE_CLEAR_MS 300u
#define SAFE_SENSOR_AGE_MS 200u
#define SAFE_COMMAND_MS 500u
#define SAFE_MAX_PWM 2400
/*
 * PYNQ 按固定周期发送 $P 驱动帧，链路是板上短距离有线 UART，
 * 租约超时收紧到 2.5 个帧周期；蓝牙 App 的发包行为未完全验证，
 * 仍沿用 500 ms。
 */
#define SAFE_COMMAND_MS_PYNQ 250u
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
    uint32_t sample_ms;    /* 最近一次超声波采样产生的时间 */
    uint32_t command_ms;   /* 最近一次有效运动指令的时间 */
    uint32_t clear_ms;     /* 障碍消失后开始连续确认的时间 */
    uint16_t distance_mm;  /* 当前测得的前向距离 */
    uint8_t ir;            /* 红外位图：bit0 左，bit1 右，1 表示检测到障碍 */
    uint8_t valid;         /* 超声波数据是否有效 */
    uint8_t clear_tracking;/* 是否正在等待安全距离保持稳定 */
    uint8_t latched;       /* 锁存停车标志，1 时任何运动命令都输出为停止 */
    uint8_t distance_blocked; /* 前方过近时为 1，只屏蔽 FORWARD 输出 */
    uint8_t command;       /* 当前请求的运动方向 */
    uint8_t reason;        /* 故障位图，供串口报告和屏幕显示 */
    int speed;              /* 当前 PWM 幅值，仍需经过上下限保护 */
    /*
     * 以下字段服务 PYNQ 协作模式：
     * dist_source 0=距离来自本地超声波，1=距离来自 PYNQ $P 帧上报；
     * left_req/right_req 是 $P 帧请求的左右轮 PWM；
     * drop_count 统计 $P 帧校验失败次数，经 $CAR 帧回传给 PYNQ。
     */
    uint8_t dist_source;
    int left_req;
    int right_req;
    uint16_t drop_count;
} SafeControl;

/* 以下函数只处理数据和状态，不直接操作 GPIO，便于仿真和单元测试。 */
void safe_init(SafeControl *s);
void safe_sensors(SafeControl *s, uint32_t now, uint8_t ir,
                  uint8_t valid, uint16_t mm, uint32_t sample_ms);
/* PYNQ 模式下距离不由本机测量：只更新红外快照，距离字段交给 $P 帧。 */
void safe_sensors_dist_ext(SafeControl *s, uint32_t now, uint8_t ir);
void safe_tick(SafeControl *s, uint32_t now);
void safe_fault(SafeControl *s, uint8_t reason);
int safe_frame(SafeControl *s, const char *p, size_t n, uint32_t now);
int safe_pframe(SafeControl *s, const char *p, size_t n, uint32_t now);
void safe_outputs(const SafeControl *s, int *left, int *right);
#endif
