#ifndef _BSP_H_
#define _BSP_H_

#include "stm32f10x.h"
#include "stm32f10x_it.h" 
#include "stm32f10x_i2c.h"
#include "stm32f10x_gpio.h"
#include "stm32f10x_rcc.h"

/* 宏定义 */
#define BITBAND(addr, bitnum) ((addr & 0xF0000000) + 0x2000000 + ((addr & 0xFFFFF) << 5) + (bitnum << 2))
#define MEM_ADDR(addr) *((volatile unsigned long *)(addr))
#define BIT_ADDR(addr, bitnum) MEM_ADDR(BITBAND(addr, bitnum))

#define PAout(n) BIT_ADDR(GPIOA_ODR_Addr, n) // 输出
#define PAin(n) BIT_ADDR(GPIOA_IDR_Addr, n)  // 输入

#define PBout(n) BIT_ADDR(GPIOB_ODR_Addr, n) // 输出
#define PBin(n) BIT_ADDR(GPIOB_IDR_Addr, n)  // 输入

#define PCout(n) BIT_ADDR(GPIOC_ODR_Addr, n) // 输出
#define PCin(n) BIT_ADDR(GPIOC_IDR_Addr, n)  // 输入

#define PDout(n) BIT_ADDR(GPIOD_ODR_Addr, n) // 输出
#define PDin(n) BIT_ADDR(GPIOD_IDR_Addr, n)  // 输入

#define PEout(n) BIT_ADDR(GPIOE_ODR_Addr, n) // 输出
#define PEin(n) BIT_ADDR(GPIOE_IDR_Addr, n)  // 输入

#define PFout(n) BIT_ADDR(GPIOF_ODR_Addr, n) // 输出
#define PFin(n) BIT_ADDR(GPIOF_IDR_Addr, n)  // 输入

#define PGout(n) BIT_ADDR(GPIOG_ODR_Addr, n) // 输出
#define PGin(n) BIT_ADDR(GPIOG_IDR_Addr, n)  // 输入

/* 导入头文件 */
#include <stdbool.h>        // 添加包含bool类型定义的头文件
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdio.h>
#include "led.h"            //LED
#include "Key.h"			//按键
#include "usart.h"          //1
#include "usart2.h"			//2
#include "usart3.h"			//3
#include "stdio.h"			//?
#include "i2c_ctl.h"		//i2c
#include "bus_servo.h"		//舵机
#include "timer_delay.h"    //延时
#include "Engine.h"			//舵机动作
#include "ranging.h"		//避障
#include "serial_dispose.h" //串口处理
/* 函数声明 */
void Delay_init(void);
void Delay_us(uint32_t nus);
void Delay_ms(uint32_t nms);  // 修改此处，使用 uint32_t 而不是 u16
void Delay_s(uint32_t ns);
void USART_Send(char *str);


#endif /* _BSP_H_ */
