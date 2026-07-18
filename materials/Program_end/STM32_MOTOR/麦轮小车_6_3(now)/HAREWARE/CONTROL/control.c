#include "control.h"
#include "usart2_handler.h"
#include "avoidance.h"
#include <string.h>

// 全局运动变量
float Move_X = 0.0f;
float Move_Y = 0.0f;
float Move_Z = 0.0f;
int i;

// 命令处理结构
typedef struct {
    char cmd[3]; // 存储2字符命令+结束符
    float move_x;
    float move_y;
    float move_z;
} Command;

// 预初始化命令表
static const Command cmd_table[] = {
    {"G1",  0.5,  0.0,  0.0}, {"G2",  0.55,  0.0,  0.0}, {"G3",  0.6,  0.0,  0.0}, 
    {"G4",  0.65,  0.0,  0.0}, {"G5",  0.7,  0.0,  0.0},//前进
    {"B1", -0.5,  0.0,  0.0}, {"B2", -0.55,  0.0,  0.0}, {"B3", -0.6,  0.0,  0.0},
    {"B4", -0.65,  0.0,  0.0}, {"B5", -0.7,  0.0,  0.0},//后退
    
    {"L1",  0.0,  0.2,  0.0}, {"L2",  0.0,  0.25,  0.0}, {"L3",  0.0,  0.3,  0.0},
    {"L4",  0.0,  0.35,  0.0}, {"L5",  0.0,  0.4,  0.0},//左转
    {"R1",  0.0, -0.2,  0.0}, {"R2",  0.0, -0.25,  0.0}, {"R3",  0.0, -0.3,  0.0},
    {"R4",  0.0, -0.35,  0.0}, {"R5",  0.0, -0.4,  0.0},//右转
    
    {"TL",  0.0,  0.0,  2.5}, {"TR",  0.0,  0.0, -2.5},//左平移右平移
    {"S",   0.0,  0.0,  0.0}  // 停止命令
};

#define CMD_COUNT (sizeof(cmd_table) / sizeof(cmd_table[0]))

// 查找命令并设置速度
static void Set_Motor_Speed_From_Command(const char* cmd_str)
{
    for (i = 0; i < CMD_COUNT; i++) {
        if (strcmp(cmd_str, cmd_table[i].cmd) == 0) {
            // 强制退出避障模式
            Avoidance_Force_Exit();
            
            Move_X = cmd_table[i].move_x;
            Move_Y = cmd_table[i].move_y;
            Move_Z = cmd_table[i].move_z;
            return;
        }
    }
    
    // 如果未找到匹配命令，停止小车
    Move_X = 0;
    Move_Y = 0;
    Move_Z = 0;
}

// 底轮控制更新函数
void Motor_Control_Update(void) {
    // 检查是否有新的底盘指令
    if(USART2_ChassisCmdUpdated()) {
        ChassisCmdData cmd = USART2_GetChassisCmd();
        
        // 应用新的控制指令
        Set_Motor_Speed_From_Command(cmd.cmd_str);
    }
}

// 初始化函数
void Motor_Control_Init(void) {
    // 初始化运动变量
    Move_X = 0.0f;
    Move_Y = 0.0f;
    Move_Z = 0.0f;
}
