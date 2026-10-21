/* Hybrid v3: STM32 samples ultrasound/IR; PYNQ retains PL QEI/risk/video. */
#include "stm32f10x.h"
#include "bsp_motor.h"
#include "bsp_iravoid.h"
#include "bsp_ultrasonic.h"
#include "safe_control.h"
#include "hybrid_protocol.h"
#include "stm32f10x_exti.h"
#include "safe_car.h"
#include <stdio.h>
#include <string.h>

static SafeControl control;
static volatile uint32_t millis;
/* ISR queues and parser state are independent for USART1 and USART2. */
static volatile uint8_t rx_head[2], rx_tail[2], rx_error[2];
static uint8_t rx[2][128];
static char frame[2][80];
static unsigned frame_len[2];
static uint32_t frame_start[2];
/* First CRC-valid Q1 binds one data UART until reset. Noise cannot bind. */
static volatile uint8_t hybrid_uart;
static char tx[120];
static unsigned tx_pos, tx_len;
static uint32_t report_ms;
static char tx2[180];
static HybridSession hybrid;
static uint8_t reply_pending;
static uint32_t reply_seq;
static volatile uint8_t echo_phase, echo_valid;
static volatile uint16_t echo_rise, echo_mm;
static volatile uint32_t echo_sample_ms, echo_seq;
static uint32_t trigger_ms, ir_sample_ms, ir_seq;
static uint8_t ir_mask, ir_candidate, ir_count, ir_valid;
/* Retain original BSP mapping: PA6=left, PA4=right; verify by separate occlusion. */
static unsigned tx2_pos, tx2_len;

/* Diagnostics never own the data UART; explicit STOP remains unconditional.
 * rx_diag: bindings, UART errors, overflow, frame timeout, nested start,
 * length error, bad data format, ARM rejection, IDLE, last SR. */
volatile uint32_t rx_diag[10];
volatile uint32_t rx_bad[16]; /* 错误字节快照：USB标志、SR、接收字节 */

/*
 * 硬件适配层：把 USART 中断得到的数据转成 safe_control 能理解的帧；
 * 再把 safe_outputs 的结果写入电机 PWM。
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
static void serial_init(USART_TypeDef *u, uint32_t baud) {
    USART_InitTypeDef s;
    USART_StructInit(&s);
    s.USART_BaudRate=baud;
    USART_Init(u,&s); USART_Cmd(u,ENABLE);
}
static void serial_irq(USART_TypeDef *u, unsigned port) {
    /*
     * 中断只负责“收字节并放入环形缓冲区”，不在中断里解析完整协议。
     * 这样中断执行时间短，主循环可以在合适的上下文中处理安全状态。
     */
    uint32_t sr=u->SR;
    if(sr & (USART_SR_RXNE|USART_SR_ORE|USART_SR_FE|USART_SR_NE|USART_SR_PE)) {
        uint8_t c=(uint8_t)u->DR;
        uint8_t next=(uint8_t)((rx_head[port]+1u)&127u);
        if(sr & (USART_SR_ORE|USART_SR_FE|USART_SR_NE|USART_SR_PE)) {
            rx_bad[rx_diag[1]&15u]=((uint32_t)(port+1u)<<24)|(sr<<8)|c;
            rx_diag[1]++; rx_diag[9]=sr;
            rx_error[port]=1; return;
        }
        if(next==rx_tail[port]) { rx_diag[2]++; rx_error[port]=1; return; }
        rx[port][rx_head[port]]=c;
        __asm volatile("" ::: "memory");
        rx_head[port]=next;
    }
}
void USART1_IRQHandler(void) { serial_irq(USART1,0); }
void USART2_IRQHandler(void) { serial_irq(USART2,1); }
void EXTI15_10_IRQHandler(void) {
    if(EXTI_GetITStatus(EXTI_Line12)!=RESET) {
        uint16_t stamp=(uint16_t)TIM2->CNT;
        EXTI_ClearITPendingBit(EXTI_Line12);
        if(GPIO_ReadInputDataBit(ECHO_PORT,ECHO_PIN)) {
            if(echo_phase==1) { echo_rise=stamp; echo_phase=2; }
        } else if(echo_phase==2) {
            uint16_t width=(uint16_t)(stamp-echo_rise);
            echo_valid=(uint8_t)(width>=116u && width<=23200u);
            echo_mm=echo_valid?(uint16_t)(((uint32_t)width*10u)/58u):0u;
            echo_sample_ms=millis; echo_seq++; echo_phase=0;
        }
    }
}
/* Transplanted from stm32预备程序/Source/APP/safe_car.c ultrasonic().
 * Only additions: real observation sequence increments for UART freshness. */
static void ultrasonic(uint32_t now) {
    uint32_t key=irq_save();
    if(echo_phase && (uint32_t)(now-trigger_ms)>=30u) {
        echo_phase=0; echo_valid=0; echo_sample_ms=now; echo_seq++;
    }
    if(!echo_phase && (uint32_t)(now-trigger_ms)>=60u) {
        trigger_ms=now;
        if(GPIO_ReadInputDataBit(ECHO_PORT,ECHO_PIN)) {
            echo_valid=0; echo_sample_ms=now; echo_seq++;
            irq_restore(key); return;
        }
        EXTI_ClearITPendingBit(EXTI_Line12);
        echo_phase=1;
        irq_restore(key);
        GPIO_SetBits(TRIG_PORT,TRIG_PIN);
        {
            uint16_t start=(uint16_t)TIM2->CNT;
            /* Keep the existing bounded Trig pulse; never wait for Echo. */
            while((uint16_t)((uint16_t)TIM2->CNT-start)<12u) {}
        }
        GPIO_ResetBits(TRIG_PORT,TRIG_PIN);
        return;
    }
    irq_restore(key);
}
static void local_sensors(void) {
    uint32_t now=millis,key;
    uint16_t mm; uint8_t valid,raw;
    uint32_t sample;
    ultrasonic(now);
    key=irq_save();
    valid=echo_valid; mm=echo_mm; sample=echo_sample_ms;
    irq_restore(key);
    now=millis;
    if((uint32_t)(now-ir_sample_ms)>=1u) {
        if((uint32_t)(now-ir_sample_ms)>5u) { ir_count=0; ir_valid=0; }
        raw=(uint8_t)((GPIO_ReadInputDataBit(IRAvoid_L1_PORT,IRAvoid_L1_PIN)==0?1u:0u)|
                     (GPIO_ReadInputDataBit(IRAvoid_R1_PORT,IRAvoid_R1_PIN)==0?2u:0u));
        if(raw!=ir_candidate) { ir_candidate=raw; ir_count=1; ir_valid=0; }
        else if(ir_count<3u) ir_count++;
        if(ir_count>=3u) { ir_mask=raw; ir_valid=1; }
        ir_sample_ms=now; ir_seq++;
    }
    safe_local_sample(&control,mm,valid,sample,ir_mask,
                      (uint8_t)(ir_valid && (uint32_t)(now-ir_sample_ms)<10u),now);
}
static void receive_port(uint32_t now, unsigned port) {
    unsigned budget=64;
    uint32_t key;
    if(rx_error[port]) {
        key=irq_save();
        rx_tail[port]=rx_head[port]; rx_error[port]=0;
        irq_restore(key);
        frame_len[port]=0; safe_fault(&control,FAULT_FRAME);
    }
    if(frame_len[port] && (uint32_t)(now-frame_start[port])>=150u) {
        rx_diag[3]++;
        frame_len[port]=0; safe_fault(&control,FAULT_FRAME);
    }
    while(rx_tail[port]!=rx_head[port] && budget--) {
        char c=(char)rx[port][rx_tail[port]];
        rx_tail[port]=(uint8_t)((rx_tail[port]+1u)&127u);
        if(c=='$') {
            if(frame_len[port]) { rx_diag[4]++; safe_fault(&control,FAULT_FRAME); }
            frame_len[port]=0; frame_start[port]=now;
            frame[port][frame_len[port]++]=c;
        } else if(frame_len[port]) {
            if(frame_len[port]>=sizeof(frame[port])-1u) {
                rx_diag[5]++; frame_len[port]=0;
                safe_fault(&control,FAULT_FRAME); continue;
            }
            frame[port][frame_len[port]++]=c;
            if(c=='#') {
                const char *packet=frame[port]; unsigned length=frame_len[port];
                /* Both channels can stop, neither can claim ownership by noise. */
                if((length==6u && !memcmp(packet,"$HALT#",6)) ||
                   (length==7u && !memcmp(packet,"$PSTOP#",7))) {
                    safe_fault(&control,FAULT_START);
                } else if(length==6u && !memcmp(packet,"$IDLE#",6)) {
                    rx_diag[8]++; control.command=STOP;
                } else if(length==5u && !memcmp(packet,"$ARM#",5)) {
                    rx_diag[7]++; safe_fault(&control,FAULT_START);
                } else if(length==4u && !memcmp(packet,"$BT#",4)) {
                    /* Legacy diagnostic command stays a stop, never a release. */
                    safe_fault(&control,FAULT_START);
                } else if(!hybrid_uart || hybrid_uart==port+1u) {
                    int result=hybrid_receive(&control,&hybrid,packet,length,now);
                    if(result==2) {
                        if(!hybrid_uart) {
                            hybrid_uart=(uint8_t)(port+1u); rx_diag[0]++;
                            /* Prevent SAFE diagnostics sharing the S1 data TX. */
                            tx_pos=tx_len=0;
                        }
                        reply_seq=hybrid.query_seq; reply_pending=1;
                    } else if(!result) rx_diag[6]++;
                }
                /* The non-data UART cannot change session, leases or PWM. */
                frame_len[port]=0;
            }
        }
    }
}
static void receive(uint32_t now) {
    receive_port(now,0); receive_port(now,1);
}
static void report(uint32_t now) {
    USART_TypeDef *diagnostic=hybrid_uart==1u?USART2:USART1;
    if(tx_pos==tx_len && (uint32_t)(now-report_ms)>=250u) {
        int n;
        report_ms=now;
        n=snprintf(tx,sizeof(tx),
          "$SAFE,MS%lu,IR%u,MM%u,VALID%u,LOCK%u,FAULT%u,CMD%u,PWM%d,USB%u#\r\n",
          (unsigned long)now,control.ir,control.distance_mm,control.valid,
          control.latched,control.reason,control.command,control.speed,0u);
        tx_pos=0; tx_len=(n>0 && (unsigned)n<sizeof(tx))?(unsigned)n:0;
    }
    /*
     * 诊断串口采用非阻塞发送：发送器忙时本轮跳过，下一轮继续。
     * 这样调试信息不会因为电脑未打开串口而拖住电机安全控制。
     */
    if(tx_pos<tx_len && (diagnostic->SR & USART_SR_TXE))
        diagnostic->DR=(uint8_t)tx[tx_pos++];
}
/* Reply only to a fresh Q1. Local sample sequences/timestamps are independent
 * of query or command traffic. Actual motor output is included in this batch. */
static unsigned age16(uint32_t now,uint32_t stamp) {
    uint32_t age=now-stamp; return age>65535u?65535u:(unsigned)age;
}
static void car_report(uint32_t now, int left, int right) {
    USART_TypeDef *data_uart;
    if(!hybrid_uart) return;
    data_uart=hybrid_uart==1u?USART1:USART2;
    if(reply_pending && tx2_pos==tx2_len) {
        uint32_t key=irq_save();
        uint32_t sample=echo_sample_ms,sequence=echo_seq;
        uint16_t mm=echo_mm; uint8_t valid=echo_valid;
        now=millis; irq_restore(key);
        reply_pending=0; tx2_pos=0;
        tx2_len=(unsigned)hybrid_report(tx2,sizeof(tx2),&control,&hybrid,reply_seq,
            sequence,age16(now,sample),valid,mm,ir_seq,age16(now,ir_sample_ms),
            ir_valid,ir_mask,left,right);
    }
    if(tx2_pos<tx2_len && (data_uart->SR & USART_SR_TXE))
        data_uart->DR=(uint8_t)tx2[tx2_pos++];
}
void safe_car_init(void) {
    TIM_OCInitTypeDef oc;
    NVIC_InitTypeDef ni;
    EXTI_InitTypeDef ex;
    /* 初始化顺序：先进入安全锁车，再配置硬件，最后打开中断和看门狗。 */
    SystemCoreClockUpdate();
    safe_init(&control);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA|RCC_APB2Periph_GPIOB|
                           RCC_APB2Periph_AFIO|RCC_APB2Periph_USART1|
                           IRAvoid_L1_RCC|IRAvoid_R1_RCC|TRIG_RCC|ECHO_RCC,ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2|RCC_APB1Periph_TIM4|RCC_APB1Periph_USART2,ENABLE);
    GPIO_PinRemapConfig(GPIO_Remap_SWJ_JTAGDisable,ENABLE);
    gpio(Motor_Port,Left_MotoA_Pin|Left_MotoB_Pin|
                    Right_MotoA_Pin|Right_MotoB_Pin,GPIO_Mode_Out_PP);
    brake();
    /* 原车时钟假定 8 MHz 外部晶振倍频到 72 MHz；不满足就安全停机。 */
    if(SystemCoreClock!=72000000u || !(RCC->CR & RCC_CR_HSERDY)) safe_panic();
    gpio(GPIOB,GPIO_Pin_6|GPIO_Pin_7,GPIO_Mode_AF_PP);
    {
        TIM_TimeBaseInitTypeDef tb;
        TIM_TimeBaseStructInit(&tb);
        tb.TIM_Prescaler=(uint16_t)(SystemCoreClock/1000000u-1u);
        tb.TIM_Period=7199;
        TIM_TimeBaseInit(TIM4,&tb);
    }
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
    gpio(ECHO_PORT,ECHO_PIN,GPIO_Mode_IN_FLOATING);
    {
        TIM_TimeBaseInitTypeDef tb; TIM_TimeBaseStructInit(&tb);
        tb.TIM_Prescaler=(uint16_t)(SystemCoreClock/1000000u-1u);
        tb.TIM_Period=65535; TIM_TimeBaseInit(TIM2,&tb); TIM_Cmd(TIM2,ENABLE);
    }
    GPIO_EXTILineConfig(GPIO_PortSourceGPIOA,GPIO_PinSource12);
    EXTI_StructInit(&ex); ex.EXTI_Line=EXTI_Line12;
    ex.EXTI_Mode=EXTI_Mode_Interrupt; ex.EXTI_Trigger=EXTI_Trigger_Rising_Falling;
    ex.EXTI_LineCmd=ENABLE; EXTI_Init(&ex);
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
    ni.NVIC_IRQChannel=EXTI15_10_IRQn; ni.NVIC_IRQChannelPreemptionPriority=0;
    ni.NVIC_IRQChannelSubPriority=0; ni.NVIC_IRQChannelCmd=ENABLE; NVIC_Init(&ni);
    gpio(GPIOA,GPIO_Pin_2|GPIO_Pin_9,GPIO_Mode_AF_PP);
    gpio(GPIOA,GPIO_Pin_3|GPIO_Pin_10,GPIO_Mode_IPU);
    serial_init(USART2,115200); serial_init(USART1,115200);
    ni.NVIC_IRQChannel=USART2_IRQn;
    ni.NVIC_IRQChannelPreemptionPriority=1; ni.NVIC_IRQChannelSubPriority=0;
    ni.NVIC_IRQChannelCmd=ENABLE; NVIC_Init(&ni);
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
    int left,right;
    /* 一次轮询周期：解析 → 状态检查 → 输出 → 回传 → 喂狗。
     * Local acquisition is independent of queries and driving commands. */
    local_sensors();
    receive(millis);
    local_sensors();
    safe_tick(&control,millis);
    safe_outputs(&control,&left,&right);
    if(control.latched) brake(); else motors(left,right);
    report(millis);
    car_report(millis,left,right);
    IWDG->KR=0xAAAA;
}
