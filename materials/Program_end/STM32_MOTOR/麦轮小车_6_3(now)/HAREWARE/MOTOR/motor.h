#ifndef __MOTOR_H
#define __MOTOR_H

#include "sys.h"

// 安全控制宏
#define MOTOR_EMERGENCY_STOP() do { \
    STBY = 0; /* 立即进入待机模式 */ \
    TIM8->CCR1 = 0; TIM8->CCR2 = 0; TIM8->CCR3 = 0; TIM8->CCR4 = 0; /* 清零PWM占空比 */ \
    AIN1 = 0; AIN2 = 0; BIN1 = 0; BIN2 = 0; CIN1 = 0; CIN2 = 0; DIN1 = 0; DIN2 = 0; /* 方向引脚置零 */ \
} while(0)

#define MOTOR_ENABLE() (STBY = 1)

#define STBY    PCout(2)
#define CIN2    PDout(2)    
#define CIN1    PCout(12)
#define DIN2    PBout(4)
#define DIN1    PBout(5)
#define AIN2    PCout(13)    
#define AIN1    PCout(14)
#define BIN2    PBout(8)
#define BIN1    PBout(9)

void Motor_Init(void);
void Motor_Safe_Start(void);
#endif
