#ifndef _ENGINE_H_
#define _ENGINE_H_

#include "timer_delay.h"
#include "bsp.h"

// 定义延时时间（单位：毫秒）
#define DELAY_TIME 1500
#define RESET_DELAY_TIME 3000 // 复位时每个舵机的运行时间（3秒）
#define POST_RESET_DELAY 2000 // 复位后停顿时间（2秒）

// 定义舵机ID（对应机械臂的12个关节）
extern uint8_t id1;   // 右臂关节1
extern uint8_t id2;   // 右臂关节2
extern uint8_t id3;   // 右臂关节3
extern uint8_t id4;   // 右臂关节4
extern uint8_t id5;   // 右臂手腕
extern uint8_t id6;   // 右臂夹爪

extern uint8_t id7;   // 左臂关节1
extern uint8_t id8;   // 左臂关节2
extern uint8_t id9;   // 左臂关节3
extern uint8_t id10;  // 左臂关节4
extern uint8_t id11;  // 左臂手腕
extern uint8_t id12;  // 左臂夹爪

// 定义复位位置和摇摆动作的位置范围（根据实际舵机角度调整）
#define RESET_POSITION_ID1  1850  // id1复位位置

#define RESET_POSITION_ID2  3070  // id2复位位置
#define RESET_POSITION_ID5  1400  // id2复位位置
#define RESET_POSITION_ID6  1500  // id2复位位置

#define RESET_POSITION_ID7  1600  // id7复位位置
#define RESET_POSITION_ID8  3000  // id8复位位置
#define RESET_POSITION_ID11 3450  // id11复位位置
#define RESET_POSITION_ID12 2000  // id11复位位置

#define RESET_POSITION 2000       // 其他舵机复位位置
#define SWING_MIN_POSITION 1500   // 摇摆动作的最小角度
#define SWING_MAX_POSITION 2100   // 摇摆动作的最大角度

// 定义手腕和夹爪的动作范围
#define WRIST_SWING_MIN_POSITION 1500 // 手腕最小位置
#define WRIST_SWING_MAX_POSITION 3500 // 手腕最大位置
#define CLAW_OPEN_POSITION 1500   // 夹爪打开位置
#define CLAW_CLOSE_POSITION 3500  // 夹爪闭合位置

// 定义每个舵机的当前目标位置（右臂和左臂）
extern uint16_t targetPositionsRight[6];
extern uint16_t targetPositionsLeft[6];

// 函数声明
void performReset(void);
void performSwingAction(void);
void performHandAction(void);
void performHandshake(void);
void uplift_hand(void);
void uplift_doublehand(void);
void alimbo_hand(void);
void uphand_adjust(void);
void dance_hand(void);

void controlArmJoints(uint8_t armJointId, uint16_t position);
void controlWrist(uint8_t wristId, uint16_t position);
void controlClaw(uint8_t clawId, uint16_t position);

#endif
