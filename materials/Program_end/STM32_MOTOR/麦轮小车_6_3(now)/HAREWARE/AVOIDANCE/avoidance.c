#include "avoidance.h"
#include "usart2_handler.h"
#include "control.h"
#include <stdio.h>

// 避障状态
static uint8_t avoidance_active = 0;
static AvoidanceState avoidance_state = AVOIDANCE_IDLE;

// 定时器7用于超声波超时检测和状态计时
static volatile uint32_t ultrasonic_timeout_count = 0;
static volatile uint32_t state_timer = 0;

// 避障更新函数
void Avoidance_Update(void) {
    if(!line_follow_enabled) {
        // 检查是否有新的超声波数据
        if (USART2_UltrasonicUpdated()) {
            UltrasonicData data = USART2_GetUltrasonicData();
            
            // 重置超时计数器
            ultrasonic_timeout_count = 0;
            
            // 如果没有激活避障，检查是否需要激活
            if (!avoidance_active) {
                // 如果前方有障碍物，激活避障模式
                if (data.front < SAFE_DISTANCE || 
                    data.front_left < SAFE_DISTANCE || 
                    data.front_right < SAFE_DISTANCE) {
                    avoidance_active = 1;
                    avoidance_state = AVOIDANCE_BACKWARD;
                    state_timer = 0; // 重置状态计时器
                    
                    // 设置后退速度
                    Move_X = BACKWARD_SPEED;
                    Move_Y = 0.0f;
                    Move_Z = 0.0f;
                } else {
                    // 没有障碍物，正常前进
                    Move_X = FORWARD_SPEED;
                    Move_Y = 0.0f;
                    Move_Z = 0.0f;
                }
            } 
            // 如果已经激活避障模式
            else {
                // 根据当前状态处理
                switch(avoidance_state) {
                    case AVOIDANCE_BACKWARD:
                        // 后退状态，检查是否应该结束后退
                        if (state_timer >= BACKWARD_TIME_MS) {
                            // 后退结束，决定转向方向
                            // 比较左右前侧距离，选择距离更大的一侧转向
                            if (data.front_left > data.front_right) {
                                avoidance_state = AVOIDANCE_TURN_LEFT;
                            } else {
                                avoidance_state = AVOIDANCE_TURN_RIGHT;
                            }
                            state_timer = 0; // 重置状态计时器
                        }
                        break;
                        
                    case AVOIDANCE_TURN_LEFT:
                    case AVOIDANCE_TURN_RIGHT:
                        // 转向状态，检查是否应该结束转向
                        if (state_timer >= TURN_TIME_MS) {
                            // 转向结束，检查前方是否还有障碍物
                            if (data.front > SAFE_DISTANCE && 
                                data.front_left > SAFE_DISTANCE && 
                                data.front_right > SAFE_DISTANCE) {
                                // 前方安全，恢复正常前进
                                avoidance_active = 0;
                                avoidance_state = AVOIDANCE_IDLE;
                                Move_X = FORWARD_SPEED;
                                Move_Y = 0.0f;
                                Move_Z = 0.0f;
                            } else {
                                // 前方仍有障碍物，继续后退
                                avoidance_state = AVOIDANCE_BACKWARD;
                                state_timer = 0;
                                Move_X = BACKWARD_SPEED;
                                Move_Y = 0.0f;
                                Move_Z = 0.0f;
                            }
                        } else {
                            // 继续转向
                            if (avoidance_state == AVOIDANCE_TURN_LEFT) {
                                Move_X = 0.2f;
                                Move_Y = TURN_LEFT_SPEED;
                                Move_Z = 0.0f;
                            } else {
                                Move_X = 0.2f;
                                Move_Y = TURN_RIGHT_SPEED;
                                Move_Z = 0.0f;
                            }
                        }
                        break;
                        
                    default:
                        // 其他状态，默认恢复正常前进
                        avoidance_active = 0;
                        avoidance_state = AVOIDANCE_IDLE;
                        Move_X = FORWARD_SPEED;
                        Move_Y = 0.0f;
                        Move_Z = 0.0f;
                        break;
                }
            }
        }
    } else {
        // 巡线模式启用时，退出避障模式
        if (avoidance_active) {
            Avoidance_Force_Exit();
        }
    }
}

// 定时器7中断处理函数
void Avoidance_TIM7_IRQHandler(void) {
    if (TIM_GetITStatus(TIM7, TIM_IT_Update) != RESET) {
        TIM_ClearITPendingBit(TIM7, TIM_IT_Update);
        
        // 超时计数器递增
        ultrasonic_timeout_count++;
        
        // 状态计时器递增
        if (avoidance_active) {
            state_timer++;
        }
        
        // 检查是否超时
        if (ultrasonic_timeout_count >= ULTRASONIC_TIMEOUT_MS) {
            // 超时，退出避障模式
            if (avoidance_active) {
                avoidance_active = 0;
                avoidance_state = AVOIDANCE_IDLE;
                // 恢复默认运动状态（停止）
                Move_X = 0.0f;
                Move_Y = 0.0f;
                Move_Z = 0.0f;
            }
        }
    }
}

// 检查避障是否激活
uint8_t Is_Avoidance_Active(void) {
    return avoidance_active;
}

// 获取当前避障状态
AvoidanceState Get_Avoidance_State(void) {
    return avoidance_state;
}

// 避障初始化
void Avoidance_Init(void) {
    TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
    NVIC_InitTypeDef NVIC_InitStructure;
    
    avoidance_active = 0;
    avoidance_state = AVOIDANCE_IDLE;
    ultrasonic_timeout_count = ULTRASONIC_TIMEOUT_MS; // 初始化为超时状态
    state_timer = 0;
    
    // 使能TIM7时钟
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM7, ENABLE);
    
    // 定时器7初始化，1ms中断一次
    TIM_TimeBaseStructure.TIM_Period = 1000 - 1; // 自动重装载值
    TIM_TimeBaseStructure.TIM_Prescaler = 72 - 1; // 72MHz/72 = 1MHz，1MHz/1000 = 1kHz -> 1ms
    TIM_TimeBaseStructure.TIM_ClockDivision = 0;
    TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM7, &TIM_TimeBaseStructure);
    
    // 使能定时器7更新中断
    TIM_ITConfig(TIM7, TIM_IT_Update, ENABLE);
    
    // 配置定时器7中断
    NVIC_InitStructure.NVIC_IRQChannel = TIM7_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 1;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
    
    // 启动定时器7
    TIM_Cmd(TIM7, ENABLE);
}

// 强制退出避障模式
void Avoidance_Force_Exit(void) {
    if (avoidance_active) {
        avoidance_active = 0;
        avoidance_state = AVOIDANCE_IDLE;
        // 恢复默认运动状态（停止）
        Move_X = 0.0f;
        Move_Y = 0.0f;
        Move_Z = 0.0f;
    }
}
