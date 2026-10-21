/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         app_ultrasonic.C
* @author       liusen
* @version      V1.0
* @date         2017.07.21
* @brief        超声波传感器头文件
* @details      
* @par History  见如下说明
*                 
* version:	liusen_20170717
*/

#include "bsp_ultrasonic.h"
#include "stm32f10x.h"
#include "delay.h"


/*记录定时器溢出次数*/
unsigned int overcount = 0;


/**
* Function       bsp_getUltrasonicDistance
* @author        liusen
* @date          2017.07.20    
* @brief         获取超声距离
* @param[in]     void
* @param[out]    void
* @return        距离浮点值
* @par History   无
*/

float bsp_getUltrasonicDistance(void)
{
	float length = 0, sum = 0;
	u16 tim,count;
	unsigned int  i = 0;

	/*测5次数据计算一次平均值*/
	while(i != 5)
	{
		GPIO_SetBits(TRIG_PORT, TRIG_PIN);  //拉高信号，作为触发信号
		delay_us(20);  						//高电平信号超过10us
		GPIO_ResetBits(TRIG_PORT, TRIG_PIN);

		/*等待回响信号*/
		while(GPIO_ReadInputDataBit(ECHO_PORT, ECHO_PIN) == RESET);
		TIM_Cmd(TIM2,ENABLE);//回响信号到来，开启定时器计数
		
		i+=1; //每收到一次回响信号+1，收到5次就计算均值
		while(GPIO_ReadInputDataBit(ECHO_PORT, ECHO_PIN) == SET)//回响信号消失
	{		//等待回响信号，如果超过一定时间未收到，则必须退出，重新获取数据 fix liusen 20200810
		count = overcount;
		if(count >= 40)   //
		{
			TIM_Cmd(TIM2, DISABLE);//关闭定时器
			TIM2->CNT = 0;  //将TIM2计数寄存器的计数值清零
			overcount = 0;  //中断溢出次数清零
			return 0;	
		}
	}
		TIM_Cmd(TIM2, DISABLE);//关闭定时器
		
		tim = TIM_GetCounter(TIM2);//获取计TIM2数寄存器中的计数值，一边计算回响信号时间
		
		length = (tim + overcount * 1000) / 58.0;//通过回响信号计算距离
		
		sum = length + sum;
		TIM2->CNT = 0;  //将TIM2计数寄存器的计数值清零
		overcount = 0;  //中断溢出次数清零
		delay_ms(1);
	}
	length = sum / 5;
	return length;		//距离作为函数返回值
}

/**
* Function       bsp_Ultrasonic_Timer2_Init
* @author        liusen
* @date          2017.07.21    
* @brief         初始化定时器TIM2
* @param[in]     void
* @param[out]    void
* @return        距离浮点值
* @par History   无
*/

void bsp_Ultrasonic_Timer2_Init(void)
{
	TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructer;
	NVIC_InitTypeDef NVIC_InitStructer;


	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2, ENABLE);
	
	/*定时器TIM2初始化*/
	TIM_DeInit(TIM2);
	TIM_TimeBaseInitStructer.TIM_Period = 999;//定时周期为1000
	TIM_TimeBaseInitStructer.TIM_Prescaler = 71; //分频系数72
	TIM_TimeBaseInitStructer.TIM_ClockDivision = TIM_CKD_DIV1;//不分频
	TIM_TimeBaseInitStructer.TIM_CounterMode = TIM_CounterMode_Up;
	TIM_TimeBaseInit(TIM2, &TIM_TimeBaseInitStructer);
	
	TIM_ITConfig(TIM2, TIM_IT_Update, ENABLE);//开启更新中断

	/*定时器中断初始化*/
	NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
	
	NVIC_InitStructer.NVIC_IRQChannelPreemptionPriority = 0;
	NVIC_InitStructer.NVIC_IRQChannelSubPriority = 0;
	NVIC_InitStructer.NVIC_IRQChannel = TIM2_IRQn;
	NVIC_InitStructer.NVIC_IRQChannelCmd = ENABLE;
	
	NVIC_Init(&NVIC_InitStructer);
	TIM_Cmd(TIM2, DISABLE);//关闭定时器使能

} 

void TIM2_IRQHandler(void) //中断，当回响信号很长是，计数值溢出后重复计数，用中断来保存溢出次数
{
	if(TIM_GetITStatus(TIM2,TIM_IT_Update) != RESET)
	{
		TIM_ClearITPendingBit(TIM2, TIM_IT_Update);//清除中断标志
		overcount++;	
	}
}
