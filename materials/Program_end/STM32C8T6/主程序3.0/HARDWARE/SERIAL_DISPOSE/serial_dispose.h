#ifndef __SERIAL_DISPOSE_H
#define __SERIAL_DISPOSE_H

#include "stm32f10x.h"

// 添加超声波开关状态声明
extern volatile uint8_t ultrasonic_enabled;

// 初始化串口处理模块
void SerialDispose_Init(void);

// 处理串口数据
void SerialDispose_Process(void);

// 检查是否有新的语音命令
uint8_t SerialDispose_HasCommand(void);

// 获取当前语音命令
uint8_t SerialDispose_GetCommand(void);
void USART2_IRQHandler(void);

#endif /* __SERIAL_DISPOSE_H */
