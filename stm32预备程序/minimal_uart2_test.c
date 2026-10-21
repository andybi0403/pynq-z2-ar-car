/*
 * STM32F103C8T6 USART2 临时旁路诊断固件
 *
 * 用于绕过底板上的 CH340：PA2=USART2_TX，PA3=USART2_RX，9600/8N1。
 * 运行时不启用 USART1、PWM、舵机、红外、超声波或蓝牙协议，四个电机
 * 方向脚固定为停止电平。DAP 右侧 TX/RX 可接到 PA3/PA2 观察心跳。
 */
#include "stm32f10x.h"
#include "stm32f10x_rcc.h"
#include "stm32f10x_gpio.h"
#include "stm32f10x_usart.h"
#include <stdint.h>

volatile uint32_t mini2_magic = 0x4D32494Eu; /* ASCII: M2IN */
volatile uint32_t mini2_ms;
volatile uint32_t mini2_last_byte;
volatile uint32_t mini2_last_sr;
volatile uint32_t mini2_heartbeat_count;
volatile uint32_t mini2_tx_count;
volatile uint32_t mini2_error_count;
volatile uint32_t mini2_rx_count;

static void gpio_init_safe(void)
{
    RCC->APB2ENR |= RCC_APB2Periph_GPIOA | RCC_APB2Periph_GPIOB |
                    RCC_APB2Periph_AFIO;
    RCC->APB1ENR |= RCC_APB1Periph_USART2;

    /* PB4/PB5/PB8/PB9：原车电机方向脚，全部置高为停止/制动。 */
    GPIOB->CRL = (GPIOB->CRL & ~((uint32_t)0xFu << 16) &
                               ~((uint32_t)0xFu << 20)) |
                 ((uint32_t)0x3u << 16) | ((uint32_t)0x3u << 20);
    GPIOB->CRH = (GPIOB->CRH & ~((uint32_t)0xFu << 0) &
                               ~((uint32_t)0xFu << 4)) |
                 ((uint32_t)0x3u << 0) | ((uint32_t)0x3u << 4);
    GPIOB->BSRR = GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_8 | GPIO_Pin_9;

    /* PA2 复用推挽 TX，PA3 上拉输入 RX。PA9/PA10 不作任何输出。 */
    GPIOA->CRL = (GPIOA->CRL & ~((uint32_t)0xFu << 8) &
                               ~((uint32_t)0xFu << 12)) |
                 ((uint32_t)0xBu << 8) | ((uint32_t)0x8u << 12);
    GPIOA->BSRR = GPIO_Pin_3;
}

static void usart2_init(void)
{
    /* USART2 时钟为 36 MHz：36,000,000 / 9600 = 3750 = 0xEA6。 */
    USART2->CR1 = 0;
    USART2->CR2 = 0;
    USART2->CR3 = 0;
    USART2->BRR = 3750u;
    USART2->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE |
                  USART_CR1_RXNEIE;
    NVIC_SetPriority(USART2_IRQn, 1);
    NVIC_EnableIRQ(USART2_IRQn);
}

void SysTick_Handler(void) { ++mini2_ms; }

void USART2_IRQHandler(void)
{
    uint32_t sr = USART2->SR;
    uint8_t byte = 0;
    if (sr & (USART_SR_RXNE | USART_SR_ORE | USART_SR_FE |
              USART_SR_NE | USART_SR_PE)) {
        byte = (uint8_t)USART2->DR;
        mini2_last_sr = sr;
        mini2_last_byte = byte;
        if (sr & (USART_SR_ORE | USART_SR_FE | USART_SR_NE | USART_SR_PE))
            ++mini2_error_count;
        else
            ++mini2_rx_count;
    }
}

void USART1_IRQHandler(void) { /* USART1/CH340 在本测试中完全不启用。 */ }
void EXTI15_10_IRQHandler(void) { /* 不启用传感器中断。 */ }

void safe_panic(void)
{
    RCC->APB2ENR |= RCC_APB2Periph_GPIOB;
    GPIOB->BSRR = GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_8 | GPIO_Pin_9;
    for (;;) {
    }
}

static void send_text(const char *text)
{
    while (*text) {
        while (!(USART2->SR & USART_SR_TXE)) {
        }
        USART2->DR = (uint16_t)(uint8_t)*text++;
        ++mini2_tx_count;
    }
}

int main(void)
{
    uint32_t last_heartbeat = 0;
    SystemCoreClockUpdate();
    gpio_init_safe();
    usart2_init();
    SysTick->LOAD = SystemCoreClock / 1000u - 1u;
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE_Msk |
                    SysTick_CTRL_TICKINT_Msk |
                    SysTick_CTRL_ENABLE_Msk;
    for (;;) {
        uint32_t now = mini2_ms;
        if ((uint32_t)(now - last_heartbeat) >= 500u) {
            last_heartbeat = now;
            ++mini2_heartbeat_count;
            send_text("$MINI2,OK,STOP#\r\n");
        }
    }
}
