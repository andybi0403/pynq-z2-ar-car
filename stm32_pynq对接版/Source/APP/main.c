/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         main.c	
* @author       liusen
* @version      V1.0
* @date         2017.07.17
* @brief        主函数
* @details      
* @par History  
*                 
* version:		liusen_20170717
*/
#include "safe_car.h"

int main(void)
{		
	/*
	 * 程序入口只有两件事：初始化一次，然后不断轮询。
	 *
	 * 初始化阶段会配置时钟、GPIO、PWM、串口、定时器和中断。
	 * 轮询阶段不使用 delay，而是快速重复检查传感器、蓝牙数据和
	 * 安全状态。这样即使没有收到新的蓝牙指令，超时停车逻辑也能继续运行。
	 */
	safe_car_init();

	while (1)
	{
		/* 每次循环都会重新计算“现在是否允许电机转动”。 */
		safe_car_poll();
	}
}
