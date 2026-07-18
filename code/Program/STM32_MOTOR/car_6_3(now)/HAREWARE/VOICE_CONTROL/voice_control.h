#ifndef __VOICE_CONTROL_H
#define __VOICE_CONTROL_H

#include "stm32f10x.h"

#define VOICE_OBSTACLE_DISTANCE_CM 15

typedef enum {
    VOICE_DIR_NONE = 0,
    VOICE_DIR_FORWARD,
    VOICE_DIR_BACKWARD,
    VOICE_DIR_LEFT,
    VOICE_DIR_RIGHT,
    VOICE_DIR_TURN_LEFT,
    VOICE_DIR_TURN_RIGHT
} VoiceDirection;

void Voice_Control_Init(void);
void Voice_Control_Enable(void);
void Voice_Control_Disable(void);
uint8_t Is_Voice_Control_Enabled(void);
void Voice_Control_SetDirection(const char* cmd_str);
void Voice_Control_ClearDirection(void);
void Voice_Control_Update(void);

#endif /* __VOICE_CONTROL_H */
