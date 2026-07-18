#ifndef __TIM_H
#define __TIM_H

#include "sys.h"


#define		PWMA		TIM8->CCR3
#define 	PWMB		TIM8->CCR4
#define 	PWMC		TIM8->CCR1
#define		PWMD		TIM8->CCR2


void TIM6_Init(u16 arr, u16 psc);
void TIM8_Init(u16 arr, u16 psc);


#endif
