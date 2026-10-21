/*
 * STM32F103C8T6 最小串口诊断固件
 *
 * 目的：把“USART1 报文错误”与原小车程序的传感器、PWM、舵机和协议解析
 * 完全分开。这个固件不接受任何行驶指令，四个电机方向脚保持制动电平，
 * TIM4 也不会启动，因此烧录和运行期间不会让车轮转动。
 *
 * USART1：PA9 = TX，PA10 = RX，115200 8N1。
 * 每 500 ms 发送一次固定文本；收到的数据和硬件错误只记在 RAM 计数器中。
 * 计数器可以通过 DAP/OpenOCD 读取，不依赖上位机协议是否正确。
 */
#include "stm32f10x.h"
#include "stm32f10x_rcc.h"
#include "stm32f10x_gpio.h"
#include "stm32f10x_usart.h"
#include <stdint.h>

/* 这些变量会留在 RAM 中，供 DAP 读取。不要改动顺序后再使用旧地址。 */
volatile uint32_t mini_magic = 0x4D494E49u; /* ASCII: MINI */
volatile uint32_t mini_rx_count;
volatile uint32_t mini_error_count;
volatile uint32_t mini_tx_count;
volatile uint32_t mini_heartbeat_count;
volatile uint32_t mini_last_sr;
volatile uint32_t mini_last_byte;
volatile uint32_t mini_ms;

static void gpio_init_safe(void)
{
    /* 只打开 GPIOA/GPIOB 时钟；不打开电机定时器和其他传感器外设。 */
    RCC->APB2ENR |= RCC_APB2Periph_GPIOA | RCC_APB2Periph_GPIOB |
                    RCC_APB2Periph_AFIO | RCC_APB2Periph_USART1;

    /* PB4/PB5/PB8/PB9：原车四个电机方向脚，推挽输出并置高=停止/制动。 */
    GPIOB->CRL = (GPIOB->CRL & ~((uint32_t)0xFu << 16) &
                               ~((uint32_t)0xFu << 20)) |
                 ((uint32_t)0x3u << 16) | ((uint32_t)0x3u << 20);
    GPIOB->CRH = (GPIOB->CRH & ~((uint32_t)0xFu << 0) &
                               ~((uint32_t)0xFu << 4)) |
                 ((uint32_t)0x3u << 0) | ((uint32_t)0x3u << 4);
    GPIOB->BSRR = GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_8 | GPIO_Pin_9;

    /* PA9 复用推挽 TX，PA10 上拉输入 RX。没有任何其他 PA 外设初始化。 */
    GPIOA->CRH = (GPIOA->CRH & ~((uint32_t)0xFu << 4) &
                               ~((uint32_t)0xFu << 8)) |
                 ((uint32_t)0xBu << 4) | ((uint32_t)0x8u << 8);
    GPIOA->BSRR = GPIO_Pin_10;
}

static void usart1_init(void)
{
    /* 72 MHz / 115200 = 625 = 0x271，8 数据位、1 停止位、无校验。 */
    USART1->CR1 = 0;
    USART1->CR2 = 0;
    USART1->CR3 = 0;
    USART1->BRR = 625u;
    USART1->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE |
                  USART_CR1_RXNEIE;

    NVIC_SetPriority(USART1_IRQn, 1);
    NVIC_EnableIRQ(USART1_IRQn);
}

void SysTick_Handler(void)
{
    ++mini_ms;
}

void USART1_IRQHandler(void)
{
    uint32_t sr = USART1->SR;
    uint8_t byte = 0;

    /* 错误和 RXNE 必须读取 DR 才能清除；每个中断只读一次。 */
    if (sr & (USART_SR_RXNE | USART_SR_ORE | USART_SR_FE |
              USART_SR_NE | USART_SR_PE)) {
        byte = (uint8_t)USART1->DR;
        mini_last_sr = sr;
        mini_last_byte = byte;
        if (sr & (USART_SR_ORE | USART_SR_FE | USART_SR_NE | USART_SR_PE)) {
            ++mini_error_count;
        } else {
            ++mini_rx_count;
        }
    }
}

static void send_text(const char *text)
{
    while (*text) {
        while (!(USART1->SR & USART_SR_TXE)) {
            /* 文本很短，只等待发送寄存器空；不涉及电机控制。 */
        }
        USART1->DR = (uint16_t)(uint8_t)*text++;
        ++mini_tx_count;
    }
}

void USART2_IRQHandler(void) { /* 最小固件不启用 USART2。 */ }
void EXTI15_10_IRQHandler(void) { /* 最小固件不启用超声波中断。 */ }

void safe_panic(void)
{
    /* 发生异常时再次确保电机脚为停止电平，然后停在这里。 */
    RCC->APB2ENR |= RCC_APB2Periph_GPIOB;
    GPIOB->BSRR = GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_8 | GPIO_Pin_9;
    for (;;) {
    }
}

int main(void)
{
    uint32_t last_heartbeat = 0;

    SystemCoreClockUpdate();
    gpio_init_safe();
    usart1_init();

    SysTick->LOAD = SystemCoreClock / 1000u - 1u;
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE_Msk |
                    SysTick_CTRL_TICKINT_Msk |
                    SysTick_CTRL_ENABLE_Msk;

    for (;;) {
        uint32_t now = mini_ms;
        if ((uint32_t)(now - last_heartbeat) >= 500u) {
            last_heartbeat = now;
            ++mini_heartbeat_count;
            send_text("$MINI,OK,STOP#\r\n");
        }
    }
}
