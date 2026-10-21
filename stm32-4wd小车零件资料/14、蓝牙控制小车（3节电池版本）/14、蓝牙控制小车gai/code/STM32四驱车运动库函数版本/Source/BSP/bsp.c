/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         bsp.c
* @author       liusen
* @version      V1.0
* @date         2015.01.03
* @brief        驱动总入口
* @details      
* @par History  见如下说明
*                 
* version:	liusen_20170717
*/


#include "bsp.h"
#include "stdio.h"
#include "bsp_buzzer.h"
/**
* Function       bsp_init
* @author        liusen
* @date          2015.01.03    
* @brief         硬件设备初始化
* @param[in]     void
* @param[out]    void
* @retval        void
* @par History   无
*/
void bsp_init(void)
{
	delay_init();
	Ultrasonic_GPIO_Init();				/*超声波GPIO初始化*/
	bsp_Ultrasonic_Timer2_Init();		/*超声波TIM2初始化*/
	
	Colorful_GPIO_Init();				/*七彩探照灯*/
	Colorful_PWM_Init(1000,0, 1000,0, 1000,0); /*RGB PWM*/
	MOTOR_GPIO_Init();  				/*电机GPIO初始化*/
	Motor_PWM_Init(7200, 0, 7200, 0);	/*不分频。PWM频率 72000000/7200=10khz	  */
	Servo_GPIO_Init();				    /*舵机接口GPIO初始化*/	
	TIM1_Int_Init(9, 72);				/*100Khz的计数频率，计数到10为10us  */ 
	LineWalking_GPIO_Init();			/*巡线传感器GPIO初始化*/
	IRAvoid_GPIO_Init();				/*红外避障传感器GPIO初始化*/
	LightSeeking_GPIO_Init();			/*寻光GPIO初始化*/
	
	//Uart1_init(9600);					/*调试接口串口 */
	Uart2_init(9600);					/*协议处理接口 */
	Adc_Init();	   						/*电压测量ADC初始化*/
	Buzzer_GPIO_Init();					/*蜂鸣器GPIO初始化*/
	Buzzer_Control(OFF); 				/*先关闭蜂鸣器*/
	Fire_GPIO_Init();					/*灭火GPIO初始化*/
	Fire_Control(OFF);				    /*灭火关闭*/
	bsp_GS_Init();						/*灰度传感器初始化*/
	Angle_J1 = 90;						/*初始化舵机云台到向前*/
	printf("init ok!");
}
