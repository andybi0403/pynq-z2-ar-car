/**
* @par Copyright (C): 2010-2019, Shenzhen Yahboom Tech
* @file         bsp_iravoid.h
* @author       liusen
* @version      V1.0
* @date         2015.01.03
* @brief        红外避障驱动头文件
* @details      
* @par History  见如下说明
*                 
* version:	liusen_20170717
*/

/*

	从车身后面往前看： 左侧到右边	  对应原理图 IN5(PB12) || IN7(PB14)

*/

#ifndef __BSP_IRAVOID_H__
#define __BSP_IRAVOID_H__	




#define IRAvoid_L1_RCC		RCC_APB2Periph_GPIOA
#define IRAvoid_R1_RCC		RCC_APB2Periph_GPIOA

#define IRAvoid_L1_PIN		GPIO_Pin_6
#define IRAvoid_R1_PIN		GPIO_Pin_4

#define IRAvoid_L1_PORT		GPIOA
#define IRAvoid_R1_PORT		GPIOA



void bsp_GetIRavoid(int *p_iL1, int *p_iR1);
int bsp_GetIRavoid_Data(void);



#endif
