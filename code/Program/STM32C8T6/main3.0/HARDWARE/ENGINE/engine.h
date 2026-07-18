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

// 各舵机复位位置（根据实际舵机角度调整）
#define RESET_POSITION_ID1   1800  // id1 右臂关节1
#define RESET_POSITION_ID2   3000  // id2 右臂关节2
#define RESET_POSITION_ID3   1950  // id3 右臂关节3
#define RESET_POSITION_ID4   2000  // id4 右臂关节4
#define RESET_POSITION_ID5   1400  // id5 右臂手腕
#define RESET_POSITION_ID7   1600  // id7 左臂关节1
#define RESET_POSITION_ID8   2950  // id8 左臂关节2
#define RESET_POSITION_ID9   2000  // id9 左臂关节3
#define RESET_POSITION_ID10  2000  // id10 左臂关节4
#define RESET_POSITION_ID11  3450  // id11 左臂手腕

#define RESET_POSITION       2000  // 通用默认（摇摆动作等未单独指定的关节）
#define SWING_MIN_POSITION 1500   // 摇摆动作的最小角度
#define SWING_MAX_POSITION 2100   // 摇摆动作的最大角度

// 夹爪角度（high=复位/张开，low=闭合）
#define right_claw_high_angle  1700  // id6 右手夹爪复位(张开)
#define right_claw_low_angle   3600  // id6 右手夹爪闭合
#define right_claw_half_angle  ((right_claw_high_angle + right_claw_low_angle) / 2)  // 半开 2650
#define left_claw_high_angle   2100  // id12 左手夹爪复位(张开)
#define left_claw_low_angle    3600  // id12 左手夹爪闭合

#define RESET_POSITION_ID6   right_claw_high_angle
#define RESET_POSITION_ID12  left_claw_high_angle

// 定义手腕的动作范围
#define WRIST_SWING_MIN_POSITION 1500 // 手腕最小位置
#define WRIST_SWING_MAX_POSITION 3500 // 手腕最大位置

// ---------- 捡垃圾动作可调参数（后期调试修改） ----------
#define PICK_ID1_POSITION  3300   // 右臂关节1角度，伸手捡垃圾
#define PICK_ID2_POSITION  3200   // 右臂关节2角度
#define PICK_ID3_POSITION  2400   // 右臂关节3角度
#define PICK_ID4_POSITION  1800   // 右臂关节4角度
#define PICK_ID5_POSITION  1400   // 右臂手腕角度
#define PICK_CLAW_OPEN     right_claw_high_angle
#define PICK_CLAW_CLOSE    right_claw_low_angle

#define PLACE_ID1_POSITION 2800   // 放入体内时关节1角度
#define PLACE_ID2_POSITION 2600   // 放入体内时关节2角度
#define PLACE_ID3_POSITION 2200   // 放入体内时关节3角度
#define PLACE_ID4_POSITION RESET_POSITION_ID4
#define PLACE_ID5_POSITION 1600   // 放入体内时手腕角度
// --------------------------------------------------------

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
void test_hand(void);
void performPickGarbage(void);          // 右手捡取前方垃圾
void performPlaceGarbageInternal(void); // 将垃圾放入底盘机器人内部

void controlArmJoints(uint8_t armJointId, uint16_t position);
void controlWrist(uint8_t wristId, uint16_t position);
void controlClawOpen(void);
void controlClawClose(void);
void resetClaws(void);
void controlClaw(uint8_t clawId, uint16_t position);  // 兼容旧接口，建议使用 Open/Close

#endif
