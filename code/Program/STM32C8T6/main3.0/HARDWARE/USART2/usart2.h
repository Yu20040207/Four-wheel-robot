#ifndef _USART2_H_
#define _USART2_H_
#include "stdio.h"
#include "bsp.h"

// 串口2初始化函数
void USART2_Configuration(u32 baud_rate);

// NVIC配置函数
void NVIC_Configuration(void);

// 发送指定长度的字符串
void Usart2_SendStr_length(uint8_t *str, uint32_t strlen);

// 发送字符串
void Usart2_SendString(uint8_t *str);

// 重定义fputc函数，用于支持printf
//int fputc(int ch, FILE *f);

// 重定义fgetc函数，用于支持scanf
int fgetc(FILE *f);

// 串口2接收中断服务程序
void USART2_IRQHandler(void);
uint8_t Serial_GetRxData(void);
void USART2_Init(uint32_t baud);
void Serial_SendString(char *String);
uint8_t Serial_GetRxFlag(void);

#endif /* _USART2_H_ */
