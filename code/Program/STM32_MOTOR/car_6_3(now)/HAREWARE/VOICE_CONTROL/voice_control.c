#include "voice_control.h"
#include "usart2_handler.h"
#include "control.h"
#include <string.h>

static uint8_t voice_control_enabled = 0;
static VoiceDirection voice_direction = VOICE_DIR_NONE;

static uint8_t is_distance_too_close(uint16_t distance_cm)
{
    return (distance_cm > 0 && distance_cm < VOICE_OBSTACLE_DISTANCE_CM);
}

void Voice_Control_Init(void)
{
    voice_control_enabled = 0;
    voice_direction = VOICE_DIR_NONE;
}

void Voice_Control_Enable(void)
{
    voice_control_enabled = 1;
    voice_direction = VOICE_DIR_NONE;
}

void Voice_Control_Disable(void)
{
    voice_control_enabled = 0;
    voice_direction = VOICE_DIR_NONE;
    Move_X = 0.0f;
    Move_Y = 0.0f;
    Move_Z = 0.0f;
}

uint8_t Is_Voice_Control_Enabled(void)
{
    return voice_control_enabled;
}

void Voice_Control_SetDirection(const char* cmd_str)
{
    if (cmd_str == 0) {
        return;
    }

    if (cmd_str[0] == 'G') {
        voice_direction = VOICE_DIR_FORWARD;
    } else if (cmd_str[0] == 'B') {
        voice_direction = VOICE_DIR_BACKWARD;
    } else if (strcmp(cmd_str, "TL") == 0) {
        voice_direction = VOICE_DIR_TURN_LEFT;
    } else if (strcmp(cmd_str, "TR") == 0) {
        voice_direction = VOICE_DIR_TURN_RIGHT;
    } else if (cmd_str[0] == 'L') {
        voice_direction = VOICE_DIR_LEFT;
    } else if (cmd_str[0] == 'R') {
        voice_direction = VOICE_DIR_RIGHT;
    } else if (cmd_str[0] == 'S') {
        voice_direction = VOICE_DIR_NONE;
    }
}

void Voice_Control_ClearDirection(void)
{
    voice_direction = VOICE_DIR_NONE;
}

void Voice_Control_Update(void)
{
    UltrasonicData data;
    uint8_t blocked = 0;

    if (!voice_control_enabled || voice_direction == VOICE_DIR_NONE) {
        return;
    }

    data = USART2_GetUltrasonicData();

    switch (voice_direction) {
        case VOICE_DIR_FORWARD:
            // 前进：正前 + 左前 + 右前，任一 < 15cm 则停止
            blocked = is_distance_too_close(data.front) ||
                      is_distance_too_close(data.front_left) ||
                      is_distance_too_close(data.front_right);
            break;
        case VOICE_DIR_BACKWARD:
            blocked = is_distance_too_close(data.rear);
            break;
        case VOICE_DIR_LEFT:
            blocked = is_distance_too_close(data.front_left);
            break;
        case VOICE_DIR_RIGHT:
            blocked = is_distance_too_close(data.front_right);
            break;
        case VOICE_DIR_TURN_LEFT:
            blocked = is_distance_too_close(data.front_left);
            break;
        case VOICE_DIR_TURN_RIGHT:
            blocked = is_distance_too_close(data.front_right);
            break;
        default:
            break;
    }

    if (blocked) {
        Move_X = 0.0f;
        Move_Y = 0.0f;
        Move_Z = 0.0f;
        voice_direction = VOICE_DIR_NONE;
    }
}
