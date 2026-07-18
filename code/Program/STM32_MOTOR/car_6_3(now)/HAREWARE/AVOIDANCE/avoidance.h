#ifndef __AVOIDANCE_H
#define __AVOIDANCE_H

#include "stm32f10x.h"

// ����ģʽ״̬
typedef enum {
    AVOIDANCE_IDLE = 0,      // ����״̬
    AVOIDANCE_FORWARD,       // ǰ��״̬
    AVOIDANCE_BACKWARD,      // ����״̬
    AVOIDANCE_TURN_LEFT,     // ��ת״̬
    AVOIDANCE_TURN_RIGHT,    // ��ת״̬
    AVOIDANCE_STRAFE_LEFT,   // ��ƽ��״̬
    AVOIDANCE_STRAFE_RIGHT   // ��ƽ��״̬
} AvoidanceState;

// ��ȫ������ֵ (��λ: cm)
#define SAFE_DISTANCE 30
#define CRITICAL_DISTANCE 15
#define SIDE_SAFE_DISTANCE 25 // ���氲ȫ����

// �˶��ٶȲ���
#define FORWARD_SPEED 0.4f      // ǰ��
#define BACKWARD_SPEED -0.3f    // ����
#define TURN_LEFT_SPEED 0.5f    // ��ת
#define TURN_RIGHT_SPEED -0.5f  // ��ת
#define LEFT_SIDE_SPEED 2.5f    // ��ƽ��
#define RIGHT_SIDE_SPEED -2.5f  // ��ƽ��

// ��������ʱʱ��
#define ULTRASONIC_TIMEOUT_MS 500 // 500ms��ʱ
#define BACKWARD_TIME_MS 800      // ����ʱ��
#define TURN_TIME_MS 1200         // ת��ʱ��

// ��������
void Avoidance_Update(void);
uint8_t Is_Avoidance_Active(void);
uint8_t Is_Autonomous_Avoidance_Enabled(void);
void Avoidance_SetAutonomousMode(uint8_t enabled);
AvoidanceState Get_Avoidance_State(void);
void Avoidance_Init(void);
void Avoidance_Force_Exit(void);
void Avoidance_TIM7_IRQHandler(void);

#endif /* __AVOIDANCE_H */
