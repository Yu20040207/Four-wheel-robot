#ifndef __LINEFOLLOW_H__
#define __LINEFOLLOW_H__

#include "stm32f10x.h"
#include "sys.h"

// 定义八路传感器数量
#define SENSOR_COUNT 8

// 通信协议定义
#define LINEFOLLOW_HEADER1 0x55
#define LINEFOLLOW_HEADER2 0xAA

// 声明外部变量
extern volatile uint8_t line_follow_enabled;

// 运动控制变量
extern float Move_X;
extern float Move_Y;
extern float Move_Z;

// 函数声明
void LineFollow_Init(void);
void LineFollow_ResetController(void);
void LineFollow_Process(void);
void USART3_IRQHandler(void);

#endif /* __LINEFOLLOW_H__ */
