#ifndef __USART2_HANDLER_H
#define __USART2_HANDLER_H

#include "stm32f10x.h"

// 超声波数据结构
typedef struct {
    uint16_t front_left;  // 前左超声波数据
    uint16_t front;       // 正前超声波数据
    uint16_t front_right; // 前右超声波数据
    uint16_t rear;        // 正后超声波数据
    uint16_t rear_left;   // 正左超声波数据
    uint16_t rear_right;  // 正右超声波数据
} UltrasonicData;

// 底盘命令数据结构
typedef struct {
    char cmd_str[4]; // 存储命令字符串，最大3个字符+结束符
} ChassisCmdData;

// 外部变量声明
extern volatile uint8_t line_follow_enabled;

// 函数声明
void USART2_Init(void);
void USART2_ProcessData(void);
uint8_t USART2_UltrasonicUpdated(void);
UltrasonicData USART2_GetUltrasonicData(void);
uint8_t USART2_ChassisCmdUpdated(void);
ChassisCmdData USART2_GetChassisCmd(void);

#endif

