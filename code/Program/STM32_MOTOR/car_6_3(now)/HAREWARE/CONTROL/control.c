#include "control.h"
#include "usart2_handler.h"
#include "avoidance.h"
#include "voice_control.h"
#include "conctrl.h"
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

float Move_X = 0.0f;
float Move_Y = 0.0f;
float Move_Z = 0.0f;
int i;

typedef struct {
    char cmd[3];
    float move_x;
    float move_y;
    float move_z;
} Command;

static const Command cmd_table[] = {
    {"G1",  0.5,  0.0,  0.0}, {"G2",  0.55,  0.0,  0.0}, {"G3",  0.6,  0.0,  0.0},
    {"G4",  0.65,  0.0,  0.0}, {"G5",  0.7,  0.0,  0.0},
    {"B1", -0.5,  0.0,  0.0}, {"B2", -0.55,  0.0,  0.0}, {"B3", -0.6,  0.0,  0.0},
    {"B4", -0.65,  0.0,  0.0}, {"B5", -0.7,  0.0,  0.0},

    {"L1",  0.0, -0.12,  0.0}, {"L2",  0.0, -0.16,  0.0}, {"L3",  0.0, -0.20,  0.0},
    {"L4",  0.0, -0.24,  0.0}, {"L5",  0.0, -0.28,  0.0},
    {"R1",  0.0,  0.12,  0.0}, {"R2",  0.0,  0.16,  0.0}, {"R3",  0.0,  0.20,  0.0},
    {"R4",  0.0,  0.24,  0.0}, {"R5",  0.0,  0.28,  0.0},

    {"TL",  0.0,  0.0,  2.5}, {"TR",  0.0,  0.0, -2.5},
    {"S",   0.0,  0.0,  0.0}
};

#define CMD_COUNT (sizeof(cmd_table) / sizeof(cmd_table[0]))

static int parse_digit3(const char *s, int *value)
{
    if (!s || !isdigit((unsigned char)s[0]) || !isdigit((unsigned char)s[1]) || !isdigit((unsigned char)s[2])) {
        return 0;
    }
    *value = (s[0] - '0') * 100 + (s[1] - '0') * 10 + (s[2] - '0');
    return 1;
}

static int parse_digit2(const char *s, int *value)
{
    if (!s || !isdigit((unsigned char)s[0]) || !isdigit((unsigned char)s[1])) {
        return 0;
    }
    *value = (s[0] - '0') * 10 + (s[1] - '0');
    return 1;
}

/* PID 连续调速: V025L08=前进0.25+左平移0.08, V000R05=仅右平移0.05, B020N00=后退0.20
 * 注: L/R 的 Move_Y 符号已按当前电机接线校正（左平移=L/负Vy映射） */
static int Set_Motor_Speed_From_Velocity_Command(const char *cmd_str)
{
    int x_centi = 0;
    int y_centi = 0;
    char lat;

    if (!cmd_str || (cmd_str[0] != 'V' && cmd_str[0] != 'B')) {
        return 0;
    }
    if (strlen(cmd_str) < 7) {
        return 0;
    }
    if (!parse_digit3(&cmd_str[1], &x_centi)) {
        return 0;
    }
    lat = cmd_str[4];
    if (!parse_digit2(&cmd_str[5], &y_centi)) {
        return 0;
    }

    Avoidance_Force_Exit();

    if (cmd_str[0] == 'B') {
        if (x_centi == 0) {
            Chassis_Stop_All();
            Voice_Control_SetDirection("S");
            return 1;
        }
        Move_X = -(x_centi / 100.0f);
        Move_Y = 0.0f;
        Move_Z = 0.0f;
        Voice_Control_SetDirection("B1");
        return 1;
    }

    Move_X = x_centi / 100.0f;
    if (lat == 'N' && x_centi == 0 && y_centi == 0) {
        Chassis_Stop_All();
        Voice_Control_SetDirection("S");
        return 1;
    }
    if (lat == 'L') {
        Move_Y = -(y_centi / 100.0f);
        Voice_Control_SetDirection("L1");
    } else if (lat == 'R') {
        Move_Y = y_centi / 100.0f;
        Voice_Control_SetDirection("R1");
    } else {
        Move_Y = 0.0f;
        if (Move_X > 0.01f) {
            Voice_Control_SetDirection("G1");
        } else {
            Voice_Control_SetDirection("S");
        }
    }
    Move_Z = 0.0f;
    return 1;
}

static void Set_Motor_Speed_From_Command(const char* cmd_str)
{
    if (cmd_str && (strcmp(cmd_str, "S") == 0 || strcmp(cmd_str, "stop") == 0)) {
        Chassis_Stop_All();
        Voice_Control_SetDirection("S");
        return;
    }

    if (Set_Motor_Speed_From_Velocity_Command(cmd_str)) {
        return;
    }

    for (i = 0; i < CMD_COUNT; i++) {
        if (strcmp(cmd_str, cmd_table[i].cmd) == 0) {
            Avoidance_Force_Exit();

            Move_X = cmd_table[i].move_x;
            Move_Y = cmd_table[i].move_y;
            Move_Z = cmd_table[i].move_z;
            Voice_Control_SetDirection(cmd_str);
            return;
        }
    }

    Chassis_Stop_All();
}

void Motor_Control_Update(void) {
    if(USART2_ChassisCmdUpdated()) {
        ChassisCmdData cmd = USART2_GetChassisCmd();
        Set_Motor_Speed_From_Command(cmd.cmd_str);
    }
}

void Motor_Control_Init(void) {
    Chassis_Stop_All();
    Voice_Control_Init();
}
