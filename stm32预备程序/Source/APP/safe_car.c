/* BST-4WD safety runtime.
 * Reuses Yahboom BSP pin definitions and ST's supplied standard peripheral
 * library. Legacy autonomous applications and blocking drivers are not linked.
 */
#include "stm32f10x.h"
#include "stm32f10x_exti.h"
#include "bsp_motor.h"
#include "bsp_iravoid.h"
#include "bsp_ultrasonic.h"
#include "bsp_servo.h"
#include "safe_control.h"
#include "safe_car.h"
#include <stdio.h>
#include <string.h>

static SafeControl control;
static volatile uint32_t millis;
static volatile uint8_t rx_head, rx_tail, rx_error, rx_handover, rx_handover_head;
static uint8_t rx[128];
static char frame[80];
static unsigned frame_len;
static uint32_t frame_start;
static volatile uint8_t echo_phase, echo_valid;
static volatile uint16_t echo_rise, echo_mm;
static volatile uint32_t echo_sample_ms;
static uint32_t trigger_ms;
static char tx[120];
static unsigned tx_pos, tx_len;
static uint32_t report_ms;
static char tx2[80];
static unsigned tx2_pos, tx2_len;
static uint32_t car_ms;
/* USB 首次接收后独占控制，断线也不自动退回蓝牙；复位后恢复蓝牙。
 * usb_byte_ms 是“最近一次 USB ISR 读到字节”的时间，只由 USB ISR 更新，
 * 专用于空闲自动释放判断；不得与运动租约或有效帧时间混用。 */
static volatile uint8_t usb_owner;
static volatile uint32_t usb_byte_ms;
/* DAP诊断：接管、UART错误、溢出、帧超时、重复帧头、超长、坏格式、ARM、IDLE、最后SR。 */
volatile uint32_t rx_diag[10];
volatile uint32_t rx_bad[16]; /* 错误字节快照：USB标志、SR、接收字节 */

/*
 * 这个文件是“硬件适配层”：把 GPIO、定时器、USART 和中断得到的数据，
 * 转成 safe_control 能理解的快照；再把 safe_outputs 的结果写入电机 PWM。
 * IRQ-masked sections are short; no polling/delay/formatting inside them.
 */
static uint32_t irq_save(void) {
    uint32_t p;
    __asm volatile("mrs %0, primask\ncpsid i" : "=r"(p) :: "memory");
    return p;
}
static void irq_restore(uint32_t p) {
    __asm volatile("msr primask, %0" :: "r"(p) : "memory");
}
void SysTick_Handler(void) { millis++; }

static void gpio(GPIO_TypeDef *port, uint16_t pins, GPIOMode_TypeDef mode) {
    GPIO_InitTypeDef g;
    g.GPIO_Pin=pins; g.GPIO_Mode=mode; g.GPIO_Speed=GPIO_Speed_50MHz;
    GPIO_Init(port,&g);
}
static void brake(void) {
    /* TB6612: IN1=IN2=H gives short brake for either PWM level, STBY=H.
     * Do not change these to both LOW: that is a different stop mode. */
    GPIO_SetBits(Motor_Port,Left_MotoA_Pin|Left_MotoB_Pin|
                            Right_MotoA_Pin|Right_MotoB_Pin);
    TIM_SetCompare1(TIM4,0); TIM_SetCompare2(TIM4,0);
}
void safe_panic(void) {
    /* Works even before clocks/PWM setup; reset defaults are zero PWM. */
    RCC->APB2ENR |= RCC_APB2Periph_GPIOB;
    GPIOB->BSRR=Left_MotoA_Pin|Left_MotoB_Pin|Right_MotoA_Pin|Right_MotoB_Pin;
    TIM4->CCR1=0; TIM4->CCR2=0;
    for(;;) { /* If already active, IWDG resets to the locked boot state. */ }
}
static void channel(int value, uint16_t a, uint16_t b, unsigned channel_no) {
    /* value 的符号表示方向，绝对值表示 PWM 占空比。 */
    if(value==0) GPIO_SetBits(Motor_Port,a|b);
    else if(value>0) {
        GPIO_SetBits(Motor_Port,a); GPIO_ResetBits(Motor_Port,b);
    } else {
        GPIO_ResetBits(Motor_Port,a); GPIO_SetBits(Motor_Port,b);
    }
    if(value<0) value=-value;
    if(value>SAFE_MAX_PWM) value=SAFE_MAX_PWM;
    if(channel_no==1) TIM_SetCompare1(TIM4,(uint16_t)value);
    else TIM_SetCompare2(TIM4,(uint16_t)value);
}
static void motors(int left, int right) {
    /*
     * 先把 PWM 设为 0，再改变 H 桥方向，避免方向切换瞬间仍有大电流。
     * 这里没有使用定时器预装载，所以顺序必须由软件明确保证。
     */
    TIM_SetCompare1(TIM4,0); TIM_SetCompare2(TIM4,0);
    channel(left,Left_MotoA_Pin,Left_MotoB_Pin,2);
    channel(right,Right_MotoA_Pin,Right_MotoB_Pin,1);
}
static void timer_init(TIM_TypeDef *t, uint16_t period) {
    TIM_TimeBaseInitTypeDef tb;
    TIM_TimeBaseStructInit(&tb);
    tb.TIM_Prescaler=(uint16_t)(SystemCoreClock/1000000u-1u);
    tb.TIM_Period=period;
    TIM_TimeBaseInit(t,&tb);
}
static void serial_init(USART_TypeDef *u, uint32_t baud) {
    USART_InitTypeDef s;
    USART_StructInit(&s);
    s.USART_BaudRate=baud;
    USART_Init(u,&s); USART_Cmd(u,ENABLE);
}
static void serial_irq(USART_TypeDef *u, uint8_t usb) {
    /*
     * 中断只负责“收字节并放入环形缓冲区”，不在中断里解析完整协议。
     * 这样中断执行时间短，主循环可以在合适的上下文中处理安全状态。
     */
    uint32_t sr=u->SR;
    if(sr & (USART_SR_RXNE|USART_SR_ORE|USART_SR_FE|USART_SR_NE|USART_SR_PE)) {
        uint8_t c=(uint8_t)u->DR;
        if(usb) usb_byte_ms=millis; /* 任何字节（含错误字节）都是线路活动。 */
        if(!usb && usb_owner) return;
        if(usb && !usb_owner) {
            rx_diag[0]++;
            usb_owner=1;
            /*
             * USB 接管本身不是串口错误。丢弃尚未处理的蓝牙字节，并让
             * 主循环清除可能正在拼接的蓝牙帧、回到人工锁定状态；当前
             * USB 字节仍会在下面入队，因此首个 $HALT# 可以完整解析。
             * 中断不改 rx_tail，避免与主循环同时消费缓冲区发生竞争。
             */
            rx_handover_head=rx_head;
            rx_handover=1;
        }
        uint8_t next=(uint8_t)((rx_head+1u)&127u);
        if(sr & (USART_SR_ORE|USART_SR_FE|USART_SR_NE|USART_SR_PE)) {
            rx_bad[rx_diag[1]&15u]=((uint32_t)usb<<24)|(sr<<8)|c;
            rx_diag[1]++; rx_diag[9]=sr;
            rx_error=1; return;
        }
        if(next==rx_tail) { rx_diag[2]++; rx_error=1; return; }
        rx[rx_head]=c;
        __asm volatile("" ::: "memory");
        rx_head=next;
    }
}
void USART1_IRQHandler(void) { serial_irq(USART1,1); }
void USART2_IRQHandler(void) { serial_irq(USART2,0); }
void EXTI15_10_IRQHandler(void) {
    /*
     * 超声波 Echo 的上升沿记录起点，下降沿计算高电平宽度。
     * TIM2 以微秒为单位计数，因此 width 近似就是声波往返时间。
     */
    if(EXTI_GetITStatus(EXTI_Line12)!=RESET) {
        uint16_t now=(uint16_t)TIM2->CNT;
        EXTI_ClearITPendingBit(EXTI_Line12);
        if(GPIO_ReadInputDataBit(ECHO_PORT,ECHO_PIN)) {
            if(echo_phase==1) { echo_rise=now; echo_phase=2; }
        } else if(echo_phase==2) {
            uint16_t width=(uint16_t)(now-echo_rise);
            /* HC-SR04-like conversion: 58 us/cm. Actual module to verify. */
            echo_valid=(width>=116u && width<=23200u);
            echo_mm=(uint16_t)(((uint32_t)width*10u)/58u);
            echo_sample_ms=millis;
            echo_phase=0;
        }
    }
}
static void ultrasonic(uint32_t now) {
    uint32_t key=irq_save();
    /* 超过等待窗口仍没有下降沿，认为本次测量失效，不能当成安全距离。 */
    if(echo_phase && (uint32_t)(now-trigger_ms)>=30u) {
        echo_phase=0; echo_valid=0; echo_sample_ms=now;
    }
    /* 两次触发至少间隔 60 ms，避免 Echo 回波与下一次触发混在一起。 */
    if(!echo_phase && (uint32_t)(now-trigger_ms)>=60u) {
        trigger_ms=now;
        if(GPIO_ReadInputDataBit(ECHO_PORT,ECHO_PIN)) {
            echo_valid=0; echo_sample_ms=now;
            irq_restore(key); return;
        }
        EXTI_ClearITPendingBit(EXTI_Line12);
        echo_phase=1;
        irq_restore(key);
        GPIO_SetBits(TRIG_PORT,TRIG_PIN);
        {
            uint16_t start=(uint16_t)TIM2->CNT;
            /* 只同步等待约 12 us 的 Trig 脉冲，绝不阻塞等待 Echo。 */
            while((uint16_t)((uint16_t)TIM2->CNT-start)<12u) {}
        }
        GPIO_ResetBits(TRIG_PORT,TRIG_PIN);
        return;
    }
    irq_restore(key);
}
static void sensors(uint32_t now) {
    uint8_t valid,ir;
    uint16_t mm;
    uint32_t sample,key=irq_save();
    valid=echo_valid; mm=echo_mm; sample=echo_sample_ms;
    /* 重新读取时间，确保用“当前时刻”判断采样是否过期。 */
    now=millis;
    irq_restore(key);
    ir=(GPIO_ReadInputDataBit(IRAvoid_L1_PORT,IRAvoid_L1_PIN)==0 ? 1u:0u) |
       (GPIO_ReadInputDataBit(IRAvoid_R1_PORT,IRAvoid_R1_PIN)==0 ? 2u:0u);
    /*
     * PYNQ 模式下超声波已物理迁移到 PYNQ PL，本机的距离快照不再有效，
     * 只更新红外；距离与有效性由 $P 帧经 safe_pframe 写入。
     */
    if(control.dist_source) safe_sensors_dist_ext(&control,now,ir);
    else safe_sensors(&control,now,ir,valid,mm,sample);
}
static void accept_usb_handover(void) {
    uint8_t handover,boundary;
    uint32_t key=irq_save();
    handover=rx_handover;
    boundary=rx_handover_head;
    rx_handover=0;
    /* 丢弃接管前排队的蓝牙数据，保留 boundary 处的首个 USB 字节。 */
    if(handover) rx_tail=boundary;
    irq_restore(key);
    if(handover) {
        frame_len=0;
        safe_fault(&control,FAULT_START);
    }
}
static void release_to_bluetooth(void) {
    uint32_t key=irq_save();
    /* USB 已不再是控制源；清除它排队的残留字节后才接收 USART2。 */
    rx_tail=rx_head;
    usb_owner=0;
    rx_handover=0;
    irq_restore(key);
    frame_len=0;
    /* 切换控制源永远从锁车开始，蓝牙不能继承 USB 的运动命令。
     * 距离源同步回到本地超声波：蓝牙模式下 PYNQ 不再上报 $P 帧。 */
    control.dist_source=0;
    safe_fault(&control,FAULT_START);
}
static void receive(uint32_t now) {
    unsigned budget=64;
    uint32_t key;
    /* USB 首次接管与真正的坏帧分开处理，不能产生 FAULT_FRAME。 */
    accept_usb_handover();
    /* 缓冲区溢出或 UART 帧错误时，丢弃当前残帧并锁车。 */
    if(rx_error) {
        key=irq_save();
        rx_tail=rx_head; rx_error=0;
        irq_restore(key);
        frame_len=0; safe_fault(&control,FAULT_FRAME);
    }
    if(frame_len && (uint32_t)(now-frame_start)>=150u) {
        rx_diag[3]++;
        frame_len=0; safe_fault(&control,FAULT_FRAME);
    }
    /* 每次最多处理 64 字节，避免串口大量数据长期占满主循环。 */
    while(rx_tail!=rx_head && budget--) {
        char c=(char)rx[rx_tail];
        rx_tail=(uint8_t)((rx_tail+1u)&127u);
        if(c=='$') {
            if(frame_len) { rx_diag[4]++; safe_fault(&control,FAULT_FRAME); }
            frame_len=0; frame_start=now;
            frame[frame_len++]=c;
        } else if(frame_len) {
            if(frame_len>=sizeof(frame)-1u) {
                rx_diag[5]++;
                frame_len=0; safe_fault(&control,FAULT_FRAME); continue;
            }
            frame[frame_len++]=c;
                if(c=='#') {
                    if(usb_owner && frame_len==6 && !memcmp(frame,"$HALT#",6)) {
                        safe_fault(&control,FAULT_START);
                    } else if(usb_owner && frame_len==6 && !memcmp(frame,"$IDLE#",6)) {
                        rx_diag[8]++;
                        control.command=STOP; /* 停止但不解除故障锁存 */
                    } else if(usb_owner && frame_len==5 && !memcmp(frame,"$ARM#",5)) {
                        rx_diag[7]++;
                        (void)safe_frame(&control,"$0,0,0,0,0,0,0,0,0,0#",21,now);
                    } else if(usb_owner && frame_len==4 && !memcmp(frame,"$BT#",4)) {
                        /* 控制台发送后会立即关闭串口，避免 USB 再次自动接管。 */
                        release_to_bluetooth();
                    } else if(!usb_owner && frame_len>=13 && !memcmp(frame,"$P,",3)) {
                        /* PYNQ 驱动帧：带距离上报与校验和，进入 RAW 驱动模式。 */
                        if(!safe_pframe(&control,frame,frame_len,now)) rx_diag[6]++;
                    } else if(!usb_owner && frame_len==7 && !memcmp(frame,"$PSTOP#",7)) {
                        /* PYNQ 判定高风险：立即锁存停车，需重新解锁。 */
                        safe_fault(&control,FAULT_START);
                    } else if(!usb_owner && frame_len==6 && !memcmp(frame,"$PREL#",6)) {
                        /* PYNQ 请求解锁：与蓝牙停止帧同一条安全路径，
                         * 只有红外清除、距离足够且数据新鲜时才真正解锁。 */
                        (void)safe_frame(&control,"$0,0,0,0,0,0,0,0,0,0#",21,now);
                    } else {
                        if(!safe_frame(&control,frame,frame_len,now)) rx_diag[6]++;
                    }
                    frame_len=0;
                }
        } /* Bytes outside a frame never refresh the movement lease. */
    }
    /* 若接管发生在本轮解析中，输出电机前仍会重新锁车。 */
    accept_usb_handover();
}
static void report(uint32_t now) {
    if(tx_pos==tx_len && (uint32_t)(now-report_ms)>=250u) {
        int n;
        report_ms=now;
        n=snprintf(tx,sizeof(tx),
          "$SAFE,MS%lu,IR%u,MM%u,VALID%u,LOCK%u,FAULT%u,CMD%u,PWM%d,USB%u#\r\n",
          (unsigned long)now,control.ir,control.distance_mm,control.valid,
          control.latched,control.reason,control.command,control.speed,usb_owner);
        tx_pos=0; tx_len=(n>0 && (unsigned)n<sizeof(tx))?(unsigned)n:0;
    }
    /*
     * 诊断串口采用非阻塞发送：发送器忙时本轮跳过，下一轮继续。
     * 这样调试信息不会因为电脑未打开串口而拖住电机安全控制。
     */
    if(tx_pos<tx_len && (USART1->SR & USART_SR_TXE))
        USART1->DR=(uint8_t)tx[tx_pos++];
}
/*
 * PYNQ 状态回传：经 USART2 发给 PYNQ，作为 AR 界面和日志的 STM32 侧数据源。
 * 参数 left/right 为本轮 safe_outputs() 的实际执行 PWM（锁存/短刹为 0，
 * 近障屏蔽后正向分量已清零），不是 $P 帧的请求值；真实轮速由编码器测量。
 * 内容还含锁存状态、故障原因、PYNQ 上报距离的本地复检值、
 * 红外位图和 $P 帧校验失败计数；300 ms 周期，同样非阻塞。
 */
static void car_report(uint32_t now, int left, int right) {
    if(tx2_pos==tx2_len && (uint32_t)(now-car_ms)>=300u) {
        int n;
        car_ms=now;
        n=snprintf(tx2,sizeof(tx2),
          "$CAR,%d,%d,%u,%u,%u,%u,%u#\r\n",
          left,right,control.latched,control.reason,
          control.distance_mm,control.ir,control.drop_count);
        tx2_pos=0; tx2_len=(n>0 && (unsigned)n<sizeof(tx2))?(unsigned)n:0;
    }
    if(tx2_pos<tx2_len && (USART2->SR & USART_SR_TXE))
        USART2->DR=(uint8_t)tx2[tx2_pos++];
}
void safe_car_init(void) {
    TIM_OCInitTypeDef oc;
    EXTI_InitTypeDef ex;
    NVIC_InitTypeDef ni;
    /* 初始化顺序：先进入安全锁车，再配置硬件，最后打开中断和看门狗。 */
    SystemCoreClockUpdate();
    safe_init(&control);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA|RCC_APB2Periph_GPIOB|
                           RCC_APB2Periph_AFIO|RCC_APB2Periph_TIM1|
                           RCC_APB2Periph_USART1,ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2|RCC_APB1Periph_TIM4|
                           RCC_APB1Periph_USART2,ENABLE);
    GPIO_PinRemapConfig(GPIO_Remap_SWJ_JTAGDisable,ENABLE);
    gpio(Motor_Port,Left_MotoA_Pin|Left_MotoB_Pin|
                    Right_MotoA_Pin|Right_MotoB_Pin,GPIO_Mode_Out_PP);
    brake();
    /* 原车时钟假定 8 MHz 外部晶振倍频到 72 MHz；不满足就安全停机。 */
    if(SystemCoreClock!=72000000u || !(RCC->CR & RCC_CR_HSERDY)) safe_panic();
    gpio(GPIOB,GPIO_Pin_6|GPIO_Pin_7,GPIO_Mode_AF_PP);
    timer_init(TIM4,7199);
    /* 电机定时器保持原车约 10 kHz PWM，避免改变已有 speed/PWM 单位。 */
    TIM_PrescalerConfig(TIM4,0,TIM_PSCReloadMode_Immediate);
    TIM_OCStructInit(&oc);
    oc.TIM_OCMode=TIM_OCMode_PWM1; oc.TIM_OutputState=TIM_OutputState_Enable;
    oc.TIM_Pulse=0;
    TIM_OC1Init(TIM4,&oc); TIM_OC2Init(TIM4,&oc);
    TIM_Cmd(TIM4,ENABLE);
    gpio(IRAvoid_L1_PORT,IRAvoid_L1_PIN,GPIO_Mode_IPU);
    gpio(IRAvoid_R1_PORT,IRAvoid_R1_PIN,GPIO_Mode_IPU);
    gpio(TRIG_PORT,TRIG_PIN,GPIO_Mode_Out_PP);
    GPIO_ResetBits(TRIG_PORT,TRIG_PIN);
    gpio(ECHO_PORT,ECHO_PIN,GPIO_Mode_IPD);
    timer_init(TIM2,65535); TIM_Cmd(TIM2,ENABLE);
    /* PA12 接 Echo，双边沿中断；PA15 接 Trig，具体定义来自原车 BSP。 */
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA,GPIO_PinSource12);
    EXTI_StructInit(&ex); ex.EXTI_Line=EXTI_Line12;
    ex.EXTI_Mode=EXTI_Mode_Interrupt;
    ex.EXTI_Trigger=EXTI_Trigger_Rising_Falling;
    ex.EXTI_LineCmd=ENABLE; EXTI_Init(&ex);
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
    ni.NVIC_IRQChannel=EXTI15_10_IRQn;
    ni.NVIC_IRQChannelPreemptionPriority=0; ni.NVIC_IRQChannelSubPriority=0;
    ni.NVIC_IRQChannelCmd=ENABLE; NVIC_Init(&ni);
    /* 舵机固定朝前，使用硬件 PWM，不在主循环里软件抖动输出。 */
    gpio(Servo_J1_PORT,Servo_J1_PIN,GPIO_Mode_AF_PP);
    timer_init(TIM1,19999);
    oc.TIM_Pulse=1500;
    TIM_OC4Init(TIM1,&oc); TIM_CtrlPWMOutputs(TIM1,ENABLE); TIM_Cmd(TIM1,ENABLE);
    gpio(GPIOA,GPIO_Pin_2|GPIO_Pin_9,GPIO_Mode_AF_PP);
    gpio(GPIOA,GPIO_Pin_3|GPIO_Pin_10,GPIO_Mode_IPU);
    serial_init(USART2,9600); serial_init(USART1,115200);
    ni.NVIC_IRQChannel=USART2_IRQn;
    ni.NVIC_IRQChannelPreemptionPriority=1; NVIC_Init(&ni);
    USART_ITConfig(USART2,USART_IT_RXNE,ENABLE);
    ni.NVIC_IRQChannel=USART1_IRQn; NVIC_Init(&ni);
    USART_ITConfig(USART1,USART_IT_RXNE,ENABLE);
    SysTick->LOAD=SystemCoreClock/1000u-1u;
    SysTick->VAL=0; SysTick->CTRL=7;
    /* 独立看门狗约 0.5 s；若主循环卡死，硬件会复位并回到上电锁车状态。 */
    IWDG->KR=0x5555; IWDG->PR=4; IWDG->RLR=312;
    IWDG->KR=0xAAAA; IWDG->KR=0xCCCC;
}
void safe_car_poll(void) {
    uint32_t now=millis;
    int left,right;
    /* 一次轮询周期：采集 → 解析 → 再确认传感器 → 决策 → 输出 → 喂狗。 */
    /* PYNQ 模式下超声波物理上已接到 PYNQ，本机不再触发本地测量。 */
    if(!control.dist_source) ultrasonic(now);
    /* USB 接管且已停止、1 s 内无任何 USB 字节：自动交还 USART2。
     * release_to_bluetooth() 内部会锁车，新控制源必须重新解锁，安全不变。 */
    {
        /* Capture time/activity and release atomically: an RX interrupt between
         * the idle decision and release must not discard a new USB takeover.
         * The nested release helper preserves the already-masked PRIMASK. */
        uint32_t key=irq_save();
        if(usb_owner && control.command==STOP &&
           (uint32_t)(millis-usb_byte_ms)>=SAFE_USB_RELEASE_MS)
            release_to_bluetooth();
        irq_restore(key);
    }
    sensors(now);
    receive(millis);
    /* 电机写入前再读一次传感器，缩短“传感器发现危险到停车”的窗口。 */
    sensors(millis);
    safe_outputs(&control,&left,&right);
    if(control.latched) brake(); else motors(left,right);
    report(millis);
    car_report(millis,left,right);
    IWDG->KR=0xAAAA;
}
