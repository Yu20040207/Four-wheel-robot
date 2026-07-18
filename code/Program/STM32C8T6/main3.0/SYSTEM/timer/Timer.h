#ifndef __TIMER_H
#define __TIMER_H

#include "stm32f10x.h"

#define Trig_Port 		GPIOA
#define Trig_Pin 		GPIO_Pin_0
#define Trig_RCC		RCC_APB2Periph_GPIOA

#define Echo_Port 		GPIOA
#define Echo_Pin 		GPIO_Pin_1
#define Echo_RCC		RCC_APB2Periph_GPIOA

extern uint16_t Time;

void Timer_Init(void);
void TIM2_IRQHandler(void);

#endif /* __TIMER_H */
