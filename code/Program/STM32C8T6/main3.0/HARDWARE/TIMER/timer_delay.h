#ifndef _TIMER_DELAY_H_
#define _TIMER_DELAY_H_

#include "bsp.h"

#define TIM_DELAY                       TIM3
#define TIM_DELAY_CLOCK_CMD             RCC_APB1PeriphClockCmd
#define TIM_DELAY_CLK                   RCC_APB1Periph_TIM3
#define TIM_DELAY_IRQ                   TIM3_IRQn  
#define TIM_DELAY_IRQHandler            TIM3_IRQHandler

extern __IO u32 timer_delay_count;

void TIM_Delay_Configuration(void);
void timer_delay_ms(u16 t);

#endif /* _TIMER_DELAY_H_ */
