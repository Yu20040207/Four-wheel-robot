#ifndef __CONTROL_H
#define __CONTROL_H

#include "stm32f10x.h"

// 全局运动变量声明
extern float Move_X;
extern float Move_Y;
extern float Move_Z;

// 函数声明
void Motor_Control_Init(void);
void Motor_Control_Update(void);

#endif /* __CONTROL_H */
