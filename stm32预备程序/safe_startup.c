#include <stdint.h>
extern uint32_t _estack,_sidata,_sdata,_edata,_sbss,_ebss;
extern void SystemInit(void);
extern int main(void);
extern void SysTick_Handler(void);
extern void USART2_IRQHandler(void);
extern void USART1_IRQHandler(void);
extern void EXTI15_10_IRQHandler(void);
extern void safe_panic(void);
static void Default_Handler(void) { safe_panic(); }
void Reset_Handler(void) {
    uint32_t *src=&_sidata,*dst;
    for(dst=&_sdata;dst<&_edata;) *dst++=*src++;
    for(dst=&_sbss;dst<&_ebss;) *dst++=0;
    SystemInit();
    (void)main();
    safe_panic();
}
__attribute__((section(".isr_vector"),used))
const uintptr_t vectors[59]={
    [0]=(uintptr_t)&_estack,
    [1]=(uintptr_t)Reset_Handler,
    [2 ... 58]=(uintptr_t)Default_Handler,
    [15]=(uintptr_t)SysTick_Handler,
    [16+38]=(uintptr_t)USART2_IRQHandler,
    [16+37]=(uintptr_t)USART1_IRQHandler,
    [16+40]=(uintptr_t)EXTI15_10_IRQHandler
};
