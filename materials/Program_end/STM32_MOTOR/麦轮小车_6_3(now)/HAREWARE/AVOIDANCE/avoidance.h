#ifndef __AVOIDANCE_H
#define __AVOIDANCE_H

#include "stm32f10x.h"

// 避障模式状态
typedef enum {
    AVOIDANCE_IDLE = 0,      // 空闲状态
    AVOIDANCE_FORWARD,       // 前进状态
    AVOIDANCE_BACKWARD,      // 后退状态
    AVOIDANCE_TURN_LEFT,     // 左转状态
    AVOIDANCE_TURN_RIGHT,    // 右转状态
    AVOIDANCE_STRAFE_LEFT,   // 左平移状态
    AVOIDANCE_STRAFE_RIGHT   // 右平移状态
} AvoidanceState;

// 安全距离阈值 (单位: cm)
#define SAFE_DISTANCE 30
#define CRITICAL_DISTANCE 15
#define SIDE_SAFE_DISTANCE 25 // 侧面安全距离

// 运动速度参数
#define FORWARD_SPEED 0.4f      // 前进
#define BACKWARD_SPEED -0.3f    // 后退
#define TURN_LEFT_SPEED 0.5f    // 左转
#define TURN_RIGHT_SPEED -0.5f  // 右转
#define LEFT_SIDE_SPEED 2.5f    // 左平移
#define RIGHT_SIDE_SPEED -2.5f  // 右平移

// 超声波超时时间
#define ULTRASONIC_TIMEOUT_MS 500 // 500ms超时
#define BACKWARD_TIME_MS 800      // 后退时间
#define TURN_TIME_MS 1200         // 转向时间

// 函数声明
void Avoidance_Update(void);
uint8_t Is_Avoidance_Active(void);
AvoidanceState Get_Avoidance_State(void);
void Avoidance_Init(void);
void Avoidance_Force_Exit(void);
void Avoidance_TIM7_IRQHandler(void);

#endif /* __AVOIDANCE_H */
