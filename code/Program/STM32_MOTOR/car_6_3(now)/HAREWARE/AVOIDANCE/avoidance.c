#include "avoidance.h"
#include "usart2_handler.h"
#include "control.h"
#include <stdio.h>

// ??????
static uint8_t avoidance_active = 0;
static uint8_t autonomous_avoidance_enabled = 0;
static AvoidanceState avoidance_state = AVOIDANCE_IDLE;

// ?????7?????????????????????
static volatile uint32_t ultrasonic_timeout_count = 0;
static volatile uint32_t state_timer = 0;

// ??????????
void Avoidance_Update(void) {
    if (!autonomous_avoidance_enabled) {
        return;
    }

    if(!line_follow_enabled) {
        // ????????????????????
        if (USART2_UltrasonicUpdated()) {
            UltrasonicData data = USART2_GetUltrasonicData();
            
            // ?????????????
            ultrasonic_timeout_count = 0;
            
            // ???????????????????????????
            if (!avoidance_active) {
                // ??????????????????????
                if (data.front < SAFE_DISTANCE || 
                    data.front_left < SAFE_DISTANCE || 
                    data.front_right < SAFE_DISTANCE) {
                    avoidance_active = 1;
                    avoidance_state = AVOIDANCE_BACKWARD;
                    state_timer = 0; // ???????????
                    
                    // ???????????
                    Move_X = BACKWARD_SPEED;
                    Move_Y = 0.0f;
                    Move_Z = 0.0f;
                } else {
                    // ???????????????
                    Move_X = FORWARD_SPEED;
                    Move_Y = 0.0f;
                    Move_Z = 0.0f;
                }
            } 
            // ???????????????
            else {
                // ????????????
                switch(avoidance_state) {
                    case AVOIDANCE_BACKWARD:
                        // ????????????????????????
                        if (state_timer >= BACKWARD_TIME_MS) {
                            // ??????????????????
                            // ?????????????????????????????
                            if (data.front_left > data.front_right) {
                                avoidance_state = AVOIDANCE_TURN_LEFT;
                            } else {
                                avoidance_state = AVOIDANCE_TURN_RIGHT;
                            }
                            state_timer = 0; // ???????????
                        }
                        break;
                        
                    case AVOIDANCE_TURN_LEFT:
                    case AVOIDANCE_TURN_RIGHT:
                        // ??????????????????????
                        if (state_timer >= TURN_TIME_MS) {
                            // ????????????????????????
                            if (data.front > SAFE_DISTANCE && 
                                data.front_left > SAFE_DISTANCE && 
                                data.front_right > SAFE_DISTANCE) {
                                // ??????????????????
                                avoidance_active = 0;
                                avoidance_state = AVOIDANCE_IDLE;
                                Move_X = FORWARD_SPEED;
                                Move_Y = 0.0f;
                                Move_Z = 0.0f;
                            } else {
                                // ????????????????????
                                avoidance_state = AVOIDANCE_BACKWARD;
                                state_timer = 0;
                                Move_X = BACKWARD_SPEED;
                                Move_Y = 0.0f;
                                Move_Z = 0.0f;
                            }
                        } else {
                            // ???????
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
                        // ????????????????????
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
        // ?????????????????????
        if (avoidance_active) {
            Avoidance_Force_Exit();
        }
    }
}

// ?????7???????????
void Avoidance_TIM7_IRQHandler(void) {
    if (TIM_GetITStatus(TIM7, TIM_IT_Update) != RESET) {
        TIM_ClearITPendingBit(TIM7, TIM_IT_Update);
        
        // ?????????????
        ultrasonic_timeout_count++;
        
        // ???????????
        if (avoidance_active) {
            state_timer++;
        }
        
        // ???????
        if (ultrasonic_timeout_count >= ULTRASONIC_TIMEOUT_MS) {
            // ??????????????
            if (avoidance_active) {
                avoidance_active = 0;
                avoidance_state = AVOIDANCE_IDLE;
                // ?????????????????
                Move_X = 0.0f;
                Move_Y = 0.0f;
                Move_Z = 0.0f;
            }
        }
    }
}

// ??????????
uint8_t Is_Avoidance_Active(void) {
    return avoidance_active;
}

// ????????????
uint8_t Is_Autonomous_Avoidance_Enabled(void) {
    return autonomous_avoidance_enabled;
}

void Avoidance_SetAutonomousMode(uint8_t enabled) {
    autonomous_avoidance_enabled = enabled ? 1 : 0;
    if (!autonomous_avoidance_enabled) {
        Avoidance_Force_Exit();
    }
}

AvoidanceState Get_Avoidance_State(void) {
    return avoidance_state;
}

// ????????
void Avoidance_Init(void) {
    TIM_TimeBaseInitTypeDef TIM_TimeBaseStructure;
    NVIC_InitTypeDef NVIC_InitStructure;
    
    avoidance_active = 0;
    avoidance_state = AVOIDANCE_IDLE;
    autonomous_avoidance_enabled = 0;
    ultrasonic_timeout_count = ULTRASONIC_TIMEOUT_MS; // ???????????
    state_timer = 0;
    
    // ???TIM7???
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM7, ENABLE);
    
    // ?????7???????1ms???????
    TIM_TimeBaseStructure.TIM_Period = 1000 - 1; // ?????????
    TIM_TimeBaseStructure.TIM_Prescaler = 72 - 1; // 72MHz/72 = 1MHz??1MHz/1000 = 1kHz -> 1ms
    TIM_TimeBaseStructure.TIM_ClockDivision = 0;
    TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM7, &TIM_TimeBaseStructure);
    
    // ???????7????????
    TIM_ITConfig(TIM7, TIM_IT_Update, ENABLE);
    
    // ????????7????
    NVIC_InitStructure.NVIC_IRQChannel = TIM7_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 1;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
    
    // ?????????7
    TIM_Cmd(TIM7, ENABLE);
}

// ????????????
void Avoidance_Force_Exit(void) {
    if (avoidance_active) {
        avoidance_active = 0;
        avoidance_state = AVOIDANCE_IDLE;
        // ?????????????????
        Move_X = 0.0f;
        Move_Y = 0.0f;
        Move_Z = 0.0f;
    }
}
