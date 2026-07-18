#ifndef __USART3_H
#define __USART3_H

#include "stm32f10x.h"
#include <stdint.h>

void USART3_Init(uint32_t baud);
void USART3_SendChar(char c);
void USART3_SendString(char *str);

#endif
