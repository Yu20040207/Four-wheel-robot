#include "engine.h"

// 定义舵机ID（对应机械臂的12个关节）
uint8_t id1 = 1;   // 右�2�关节1
uint8_t id2 = 2;   // 右臂关节2
uint8_t id3 = 3;   // 右臂关节3
uint8_t id4 = 4;   // 右臂关节4
uint8_t id5 = 5;   // 右臂手腕
uint8_t id6 = 6;   // 右臂夹爪
uint8_t id7 = 7;   // 左臂关节1
uint8_t id8 = 8;   // 左臂关节2
uint8_t id9 = 9;   // 左臂关节3
uint8_t id10 = 10; // 左臂关节4
uint8_t id11 = 11; // 左臂手腕
uint8_t id12 = 12; // 左臂夹爪

int8_t direction;
int i;
int j; // 提前声明变量 j

// 定义每个舵机的当前目标位置（右臂和左臂）
uint16_t targetPositionsRight[6] = {RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION};
uint16_t targetPositionsLeft[6] = {RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION};

void performReset() {
    // 复位机械臂（右臂和左臂）
    bus_servo_control(id1, RESET_POSITION_ID1, RESET_DELAY_TIME/2);
    bus_servo_control(id2, RESET_POSITION_ID2, RESET_DELAY_TIME/2);
    bus_servo_control(id3, RESET_POSITION, RESET_DELAY_TIME/2);
    bus_servo_control(id4, RESET_POSITION, RESET_DELAY_TIME/2);
    bus_servo_control(id5, RESET_POSITION_ID5, RESET_DELAY_TIME/2);
    bus_servo_control(id6, RESET_POSITION_ID6, RESET_DELAY_TIME/2);
    bus_servo_control(id7, RESET_POSITION_ID7, RESET_DELAY_TIME/2);
    bus_servo_control(id8, RESET_POSITION_ID8, RESET_DELAY_TIME/2);
    bus_servo_control(id9, RESET_POSITION, RESET_DELAY_TIME/2);
    bus_servo_control(id10, RESET_POSITION, RESET_DELAY_TIME/2);
    bus_servo_control(id11, RESET_POSITION_ID11, RESET_DELAY_TIME/2);
    bus_servo_control(id12, RESET_POSITION_ID12, RESET_DELAY_TIME/2);
}

// 控制单个关节
void controlArmJoints(uint8_t armJointId, uint16_t position) {
    uint8_t leftArmJointId = armJointId + 6; // 左臂关节ID = 右臂关节ID +6
    bus_servo_control(armJointId, position, DELAY_TIME / 4);
    // 左臂跟随右臂动作，除了id7关节方向相反
    if (armJointId == id1) { // 对于id7关节（左臂关节1），方向相反
        uint16_t leftPosition = SWING_MIN_POSITION + (SWING_MAX_POSITION - position);
        bus_servo_control(leftArmJointId, leftPosition, DELAY_TIME / 4);
    } else {
        bus_servo_control(leftArmJointId, position, DELAY_TIME / 4);
    }
}

// 控制手腕
void controlWrist(uint8_t wristId, uint16_t position) {
    // 左臂手腕（id11）方向相反
    uint16_t leftWristPosition = (wristId == id5) ? WRIST_SWING_MAX_POSITION : WRIST_SWING_MIN_POSITION;
    bus_servo_control(wristId, position, DELAY_TIME / 2);
    bus_servo_control(id11, leftWristPosition, DELAY_TIME / 2);
}

// 控制夹爪
void controlClaw(uint8_t clawId, uint16_t position) {
    // 左右臂夹爪同步
    bus_servo_control(clawId, position, DELAY_TIME / 2);
    bus_servo_control(id12, position, DELAY_TIME / 2);
}

void performSwingAction() {
    int8_t direction = 1;       // 摇摆方向
    uint8_t wristState = 0;     // 手腕状态
    uint8_t clawState = 0;      // 夹爪状态
    int cycle;                  // 循环计数器

    // 执行五次循环
    for (cycle = 0; cycle < 40; cycle++) {
        int i; // 将变量声明移到循环外面
        // 控制机械臂的四个舵机进行摇摆动作（右臂和左臂）
        for (i = 0; i < 4; ++i) {
            // 根据当前方向更新目标位置（右臂）
            if (direction > 0) {
                if (targetPositionsRight[i] < SWING_MAX_POSITION) {
                    targetPositionsRight[i] += 100; // 每次增加100的角度
                } else {
                    direction = -1; // 到达最大角度，改变方向
                }
            } else {
                if (targetPositionsRight[i] > SWING_MIN_POSITION) {
                    targetPositionsRight[i] -= 100;
                } else {
                    direction = 1; // 到达最小角度，改变方向
                }
            }

            // 控制关节舵机
            controlArmJoints(id1 + i, targetPositionsRight[i]);
        }

        // 控制手腕舵机进行转动（右臂和左臂）
        if (wristState == 0) {
            controlWrist(id5, WRIST_SWING_MAX_POSITION);
            wristState = 1;
        } else {
            controlWrist(id5, WRIST_SWING_MIN_POSITION);
            wristState = 0;
        }

        // 控制夹爪舵机进行往复运动（右臂和左臂）
        if (clawState == 0) {
            controlClaw(id6, CLAW_OPEN_POSITION);
            clawState = 1;
        } else {
            controlClaw(id6, CLAW_CLOSE_POSITION);
            clawState = 0;
        }

        // 延时，控制整体摇摆速度
        timer_delay_ms(DELAY_TIME / 10);
    }
	// 所有挥手动作完成后复位机械臂
    performReset();
}



void performHandAction() {
	//LED_Turn();               //调试
    int8_t direction = 1;       // 摇摆方向
    uint8_t clawState = 0;      // 夹爪状态
    uint16_t targetPositions[4] = {RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION}; // 定义目标位置数组
    int cycle;                  // 循环计数器
    int i;                      // 循环变量
    int wave;                   // 挥手次数计数器

    // 执行动作循环三次
    for (wave = 0; wave < 3; wave++) { // 外层循环控制挥手次数
        for (cycle = 0; cycle < 20; cycle++) { // 内层循环控制每次挥手的摆动次数
            for (i = 0; i < 4; ++i) {
                // 根据当前方向更新目标位置
                if (direction > 0) {
                    if (targetPositions[i] < SWING_MAX_POSITION) {
                        targetPositions[i] += 50; // 每次增加50的角度
                    } else {
                        direction = -1; // 到达最大角度，改变方向
                    }
                } else {
                    if (targetPositions[i] > SWING_MIN_POSITION) {
                        targetPositions[i] -= 50; // 每次减少50的角度
                    } else {
                        direction = 1; // 到达最小角度，改变方向
                    }
                }

                // 发送控制指令
                bus_servo_control((uint8_t)(id1 + i), targetPositions[i], DELAY_TIME / 4);
            }

            // 控制夹爪舵机进行往复运动
            if (clawState == 0) {
                controlClaw(id6, CLAW_OPEN_POSITION);
                clawState = 1;
            } else {
                controlClaw(id6, CLAW_CLOSE_POSITION);
                clawState = 0;
            }

            // 延时，控制整体摇摆速度
            timer_delay_ms(DELAY_TIME / 20);
        }
        // 每次挥手结束后，重置方向和位置数组，准备下一次挥手
        direction = 1;
        for (i = 0; i < 4; ++i) {
            targetPositions[i] = RESET_POSITION;
            bus_servo_control((uint8_t)(id1 + i), targetPositions[i], DELAY_TIME / 4);
        }
        //timer_delay_ms(DELAY_TIME); // 短暂延时，使动作更分明
    }
    // 所有挥手动作完成后复位机械臂
    performReset();
}




void controlServo(uint8_t servoId, uint16_t angle, uint16_t time) {
    bus_servo_control(servoId, angle, time);
}

void performHandshake() {
    int i;  // 将变量声明移到函数开始处

    // 执行握手动作
    for (i = 0; i < 2; i++) {  // 循环执行五次
        controlServo(id1, 3200, DELAY_TIME / 2); // 第一关节转动到1100度
        controlServo(id2, 3100, DELAY_TIME / 2); // 第二关节转动100度
        controlServo(id3, RESET_POSITION, DELAY_TIME / 2);
        controlServo(id4, RESET_POSITION, DELAY_TIME / 2);
        controlServo(id5, 1600, DELAY_TIME / 2);
        controlServo(id6, 2700, DELAY_TIME / 2); // 夹爪闭合
        timer_delay_ms(DELAY_TIME);
        
        controlServo(id1, 3000, DELAY_TIME / 6);// 第一关节转动到1100度
        
        // 松开夹爪
        controlServo(id6, 1500, DELAY_TIME / 2);
        timer_delay_ms(DELAY_TIME);
		performReset();
		
    }
}




void uplift_hand() {
        controlServo(id1, 3000, DELAY_TIME / 2); // 第一关节转动到1100度
		timer_delay_ms(DELAY_TIME);
		controlServo(id6, 2700, DELAY_TIME / 2); // 夹爪闭合
		timer_delay_ms(DELAY_TIME);
}

void uplift_doublehand() {
		controlServo(id1, 3000, DELAY_TIME / 2); // 第一关节转动到1100度
		controlServo(id7, 550, DELAY_TIME / 2); // 第一关节转动到1100度
		timer_delay_ms(2*DELAY_TIME);
		controlServo(id6, 2700, DELAY_TIME / 2); // 夹爪闭合
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id12, 3400, DELAY_TIME / 2); // 夹爪闭合
}

void alimbo_hand(){
		controlServo(id2, 2300, DELAY_TIME / 2); // 第一关节转动到1100度
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id3, 3100, DELAY_TIME / 2); // 第一关节转动到1100度
		timer_delay_ms(DELAY_TIME/30);
		controlServo(id8, 2300, DELAY_TIME / 2); // 第一关节转动到1100度
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id9, 3100, DELAY_TIME / 2); // 第一关节转动到1100度
}


void uphand_adjust(){
		controlServo(id1, 1700, DELAY_TIME / 2); // ��һ�ؽ�ת����1100��
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id7, 1700, DELAY_TIME / 2); // ��һ�ؽ�ת����1100��
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id2, 2800, DELAY_TIME / 2); // ��һ�ؽ�ת����1100��
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id8, 2800, DELAY_TIME / 2); // ��һ�ؽ�ת����1100��

}






void dance_hand() {
    // ��һ���֣���ֱ״̬
    uint16_t right_arm[] = {1900, 2000, 2000};
    uint16_t left_arm[] = {1800, 1900, 2050};
    uint8_t right_ids[] = {id2, id3, id4};
    uint8_t left_ids[] = {id8, id9, id10};
    
    for (int i = 0; i < 3; i++) {
        controlServo(right_ids[i], right_arm[i], DELAY_TIME / 2);
        controlServo(left_ids[i], left_arm[i], DELAY_TIME / 2);
    }
    timer_delay_ms(DELAY_TIME/3);
    
    // �ڶ����֣����ұ��෴�ڶ�
    int16_t amplitude = 300;
    uint32_t part1_time = 4000;      // ��һ���ְڶ�ʱ��
    uint32_t update_interval = 60;
    int16_t step_size = 20;
    
    uint32_t steps = part1_time / update_interval;
    int16_t right_offset = 0;
    int16_t left_offset = 0;
    int8_t right_direction = 1;
    int8_t left_direction = -1;
    
    for (uint32_t step = 0; step < steps; step++) {
        right_offset += right_direction * step_size;
        if (right_offset >= amplitude) {
            right_offset = amplitude;
            right_direction = -1;
        } else if (right_offset <= -amplitude) {
            right_offset = -amplitude;
            right_direction = 1;
        }
        
        left_offset += left_direction * step_size;
        if (left_offset >= amplitude) {
            left_offset = amplitude;
            left_direction = -1;
        } else if (left_offset <= -amplitude) {
            left_offset = -amplitude;
            left_direction = 1;
        }
        
        for (int i = 0; i < 3; i++) {
            controlServo(right_ids[i], right_arm[i] + right_offset, update_interval / 2);
            controlServo(left_ids[i], left_arm[i] + left_offset, update_interval / 2);
        }
        
        timer_delay_ms(update_interval);
    }
    
    // �������֣��ض����ת����ָ��λ��
    controlServo(id1, 3000, DELAY_TIME / 2);
    controlServo(id2, 3100, DELAY_TIME / 2);
    controlServo(id7, 550, DELAY_TIME / 2);
    controlServo(id8, 3000, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);
    
    // ���Ĳ��֣�ʣ�µĶ�������ڶ�
    uint16_t new_right_arm[] = {3100, 2000, 2000};
    uint16_t new_left_arm[] = {3000, 1900, 2050};
    uint8_t remaining_right_ids[] = {id3, id4};
    uint8_t remaining_left_ids[] = {id9, id10};
    
    uint32_t part2_time = 4000;      // �ڶ����ְڶ�ʱ��
    steps = part2_time / update_interval;
    
    right_offset = 0;
    left_offset = 0;
    right_direction = 1;
    left_direction = -1;
    
    for (uint32_t step = 0; step < steps; step++) {
        right_offset += right_direction * step_size;
        if (right_offset >= amplitude) {
            right_offset = amplitude;
            right_direction = -1;
        } else if (right_offset <= -amplitude) {
            right_offset = -amplitude;
            right_direction = 1;
        }
        
        left_offset += left_direction * step_size;
        if (left_offset >= amplitude) {
            left_offset = amplitude;
            left_direction = -1;
        } else if (left_offset <= -amplitude) {
            left_offset = -amplitude;
            left_direction = 1;
        }
        
        for (int i = 0; i < 2; i++) {
            controlServo(remaining_right_ids[i], new_right_arm[i+1] + right_offset, update_interval / 2);
            controlServo(remaining_left_ids[i], new_left_arm[i+1] + left_offset, update_interval / 2);
        }
        
        timer_delay_ms(update_interval);
    }
    
    // ���岿�֣��̶��ض������ʣ�µĶ���ڶ�
    controlServo(id1, 1900, DELAY_TIME / 2);
    controlServo(id7, 1600, DELAY_TIME / 2);
    controlServo(id2, 1000, DELAY_TIME / 2); 
    controlServo(id8, 900, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);
    
    // ����ʣ�µĶ�������׼�Ƕ�
    uint16_t right_remaining_angles[] = {2000, 2000};
    uint16_t left_remaining_angles[] = {1900, 2050};
    uint8_t right_remaining_ids[] = {id3, id4};  // ����ֻ��id3, id4
    uint8_t left_remaining_ids[] = {id9, id10};  // ����ֻ��id9, id10
    
    // ���岿�ְڶ�����
    uint32_t part3_time = 8000;      // ���岿�ְڶ�ʱ�䣺8��
    steps = part3_time / update_interval;  // ���¼��㲽��
    
    // ����ƫ�����ͷ���
    right_offset = 0;
    left_offset = 0;
    right_direction = 1;
    left_direction = -1;
    
    // ִ�аڶ�����
    for (uint32_t step = 0; step < steps; step++) {
        // �����ұ�ƫ����
        right_offset += right_direction * step_size;
        if (right_offset >= amplitude) {
            right_offset = amplitude;
            right_direction = -1;
        } else if (right_offset <= -amplitude) {
            right_offset = -amplitude;
            right_direction = 1;
        }
        
        // �������ƫ����
        left_offset += left_direction * step_size;
        if (left_offset >= amplitude) {
            left_offset = amplitude;
            left_direction = -1;
        } else if (left_offset <= -amplitude) {
            left_offset = -amplitude;
            left_direction = 1;
        }
        
        // ����ʣ�µĶ��ִ���෴�ڶ�
        for (int i = 0; i < 2; i++) {
            controlServo(right_remaining_ids[i], 
                        right_remaining_angles[i] + right_offset, 
                        update_interval / 2);
            controlServo(left_remaining_ids[i], 
                        left_remaining_angles[i] + left_offset, 
                        update_interval / 2);
        }
        
        timer_delay_ms(update_interval);
    }
    
    // �������֣�̤����
    performReset();
    timer_delay_ms(DELAY_TIME);
    
    int count = 0;
    while (count < 3) {
        controlServo(id1, 2600, DELAY_TIME / 2);
        controlServo(id7, 2100, DELAY_TIME / 2);
        timer_delay_ms(DELAY_TIME);
        controlServo(id1, 1500, DELAY_TIME / 2);
        controlServo(id7, 1000, DELAY_TIME / 2);
        
        count++;
        
        // ��ÿ��ѭ��֮�������ӳ�
        if (count < 3) {
            timer_delay_ms(1500);
        }
    }
    
    // ���ո�λ
    performReset();
}





