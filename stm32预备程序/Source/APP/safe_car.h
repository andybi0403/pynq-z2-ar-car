#ifndef SAFE_CAR_H
#define SAFE_CAR_H

/*
 * safe_car 是硬件适配层的两个公开接口：
 *   safe_car_init()：上电时调用一次，完成外设初始化；
 *   safe_car_poll()：主循环中反复调用，执行一次控制周期。
 *
 * 具体的安全规则放在 safe_control.c 中，这样规则可以脱离 STM32
 * 硬件单独做电脑测试。
 */
void safe_car_init(void);
void safe_car_poll(void);
#endif
