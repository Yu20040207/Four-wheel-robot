#ifndef _USART_H_
#define _USART_H_
#include "stdio.h"
#include "bsp.h"

void USART1_Init(u32 baud_rate);
void NVIC_Configuration(void);
void Usart_SendStr_length(uint8_t *str, uint32_t strlen);
void Usart_SendString(uint8_t *str);
int fputc(int ch, FILE *f);
int fgetc(FILE *f);
void Serial_SetRxData(uint8_t data);
void Serial_SetRxFlag(bool flag);
// bsp.h
/* 添加以下函数声明 */
void Usart_SendStr_length(uint8_t *str, uint32_t strlen);
void Usart_SendString(uint8_t *str);

#endif /* _USART_H_ */
