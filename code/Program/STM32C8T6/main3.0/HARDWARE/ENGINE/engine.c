#include "engine.h"

// ??????????ID???????????????12?????????
uint8_t id1 = 1;   // ??1
uint8_t id2 = 2;   // ??????????2
uint8_t id3 = 3;   // ??????????3
uint8_t id4 = 4;   // ??????????4
uint8_t id5 = 5;   // ??????????
uint8_t id6 = 6;   // ????????
uint8_t id7 = 7;   // ??????????1
uint8_t id8 = 8;   // ??????????2
uint8_t id9 = 9;   // ??????????3
uint8_t id10 = 10; // ??????????4
uint8_t id11 = 11; // ??????????
uint8_t id12 = 12; // ????????

int8_t direction;
int i;
int j; // ????????????? j

// ??????????????????????????????????????????
uint16_t targetPositionsRight[6] = {RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION};
uint16_t targetPositionsLeft[6] = {RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION};

void resetClaws(void) {
    bus_servo_control(id6, right_claw_high_angle, RESET_DELAY_TIME);
    bus_servo_control(id12, left_claw_high_angle, RESET_DELAY_TIME);
    timer_delay_ms(RESET_DELAY_TIME);
}

void performReset() {
    resetClaws();

    bus_servo_control(id1, RESET_POSITION_ID1, RESET_DELAY_TIME);
    bus_servo_control(id2, RESET_POSITION_ID2, RESET_DELAY_TIME);
    bus_servo_control(id3, RESET_POSITION_ID3, RESET_DELAY_TIME);
    bus_servo_control(id4, RESET_POSITION_ID4, RESET_DELAY_TIME);
    bus_servo_control(id5, RESET_POSITION_ID5, RESET_DELAY_TIME);
    bus_servo_control(id7, RESET_POSITION_ID7, RESET_DELAY_TIME);
    bus_servo_control(id8, RESET_POSITION_ID8, RESET_DELAY_TIME);
    bus_servo_control(id9, RESET_POSITION_ID9, RESET_DELAY_TIME);
    bus_servo_control(id10, RESET_POSITION_ID10, RESET_DELAY_TIME);
    bus_servo_control(id11, RESET_POSITION_ID11, RESET_DELAY_TIME);
    timer_delay_ms(RESET_DELAY_TIME);
}

// ???????????????
void controlArmJoints(uint8_t armJointId, uint16_t position) {
    uint8_t leftArmJointId = armJointId + 6; // ??????????ID = ??????????ID +6
    bus_servo_control(armJointId, position, DELAY_TIME / 4);
    // ?????????????????????????id7???????????????
    if (armJointId == id1) { // ???id7??????????????????1?????????????
        uint16_t leftPosition = SWING_MIN_POSITION + (SWING_MAX_POSITION - position);
        bus_servo_control(leftArmJointId, leftPosition, DELAY_TIME / 4);
    } else {
        bus_servo_control(leftArmJointId, position, DELAY_TIME / 4);
    }
}

// ????????????
void controlWrist(uint8_t wristId, uint16_t position) {
    // ????????????id11???????????
    uint16_t leftWristPosition = (wristId == id5) ? WRIST_SWING_MAX_POSITION : WRIST_SWING_MIN_POSITION;
    bus_servo_control(wristId, position, DELAY_TIME / 2);
    bus_servo_control(id11, leftWristPosition, DELAY_TIME / 2);
}

// ??????????
void controlClawOpen(void) {
    bus_servo_control(id6, right_claw_high_angle, DELAY_TIME / 2);
    bus_servo_control(id12, left_claw_high_angle, DELAY_TIME / 2);
}

void controlClawClose(void) {
    bus_servo_control(id6, right_claw_low_angle, DELAY_TIME / 2);
    bus_servo_control(id12, left_claw_low_angle, DELAY_TIME / 2);
}

void controlClaw(uint8_t clawId, uint16_t position) {
    (void)clawId;
    if (position <= right_claw_high_angle + 200) {
        controlClawOpen();
    } else {
        controlClawClose();
    }
}

void performSwingAction() {
    int8_t direction = 1;       // ???????????
    uint8_t wristState = 0;     // ????????????
    uint8_t clawState = 0;      // ??????????
    int cycle;                  // ???????????

    // ????????????
    for (cycle = 0; cycle < 40; cycle++) {
        int i; // ??????????????????????
        // ????????????????????????????????????????????????????????
        for (i = 0; i < 4; ++i) {
            // ?????????????????????????????????
            if (direction > 0) {
                if (targetPositionsRight[i] < SWING_MAX_POSITION) {
                    targetPositionsRight[i] += 100; // ???????100??????
                } else {
                    direction = -1; // ???????????????????????
                }
            } else {
                if (targetPositionsRight[i] > SWING_MIN_POSITION) {
                    targetPositionsRight[i] -= 100;
                } else {
                    direction = 1; // ???????????????????????
                }
            }

            // ??????????????????
            controlArmJoints(id1 + i, targetPositionsRight[i]);
        }

        // ?????????????????????????????????????????
        if (wristState == 0) {
            controlWrist(id5, WRIST_SWING_MAX_POSITION);
            wristState = 1;
        } else {
            controlWrist(id5, WRIST_SWING_MIN_POSITION);
            wristState = 0;
        }

        // ??????????????????????????????????????????
        if (clawState == 0) {
            controlClawOpen();
            clawState = 1;
        } else {
            controlClawClose();
            clawState = 0;
        }

        // ???????????????????????????
        timer_delay_ms(DELAY_TIME / 10);
    }
	// ?????????????????????????????????
    performReset();
}



void performHandAction() {
	//LED_Turn();               //????
    int8_t direction = 1;       // ???????????
    uint8_t clawState = 0;      // ??????????
    uint16_t targetPositions[4] = {RESET_POSITION, RESET_POSITION, RESET_POSITION, RESET_POSITION}; // ????????????????
    int cycle;                  // ???????????
    int i;                      // ?????????
    int wave;                   // ?????????????????

    // ?????????????????
    for (wave = 0; wave < 3; wave++) { // ????????????????????????
        for (cycle = 0; cycle < 20; cycle++) { // ????????????????????????????????????
            for (i = 0; i < 4; ++i) {
                // ?????????????????????????
                if (direction > 0) {
                    if (targetPositions[i] < SWING_MAX_POSITION) {
                        targetPositions[i] += 50; // ???????50??????
                    } else {
                        direction = -1; // ???????????????????????
                    }
                } else {
                    if (targetPositions[i] > SWING_MIN_POSITION) {
                        targetPositions[i] -= 50; // ???????50??????
                    } else {
                        direction = 1; // ???????????????????????
                    }
                }

                // ???????????????
                bus_servo_control((uint8_t)(id1 + i), targetPositions[i], DELAY_TIME / 4);
            }

            // ???????????????????????????
            if (clawState == 0) {
                controlClawOpen();
                clawState = 1;
            } else {
                controlClawClose();
                clawState = 0;
            }

            // ???????????????????????????
            timer_delay_ms(DELAY_TIME / 20);
        }
        // ?????????????????????????????????????????????????????
        direction = 1;
        for (i = 0; i < 4; ++i) {
            targetPositions[i] = RESET_POSITION;
            bus_servo_control((uint8_t)(id1 + i), targetPositions[i], DELAY_TIME / 4);
        }
        //timer_delay_ms(DELAY_TIME); // ???????????????????????????
    }
    // ?????????????????????????????????
    performReset();
}




void controlServo(uint8_t servoId, uint16_t angle, uint16_t time) {
    bus_servo_control(servoId, angle, time);
}

void performHandshake() {
    int i;

    // 1. ?????????????????
    controlServo(id1, 3200, DELAY_TIME / 2);
    controlServo(id2, 3100, DELAY_TIME / 2);
    controlServo(id3, RESET_POSITION_ID3, DELAY_TIME / 2);
    controlServo(id4, RESET_POSITION_ID4, DELAY_TIME / 2);
    controlServo(id5, 1600, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);

    // 2. ???????
    controlServo(id6, right_claw_half_angle, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME / 2);

    // 3. ???????id1 ????????
    for (i = 0; i < 2; i++) {
        controlServo(id1, 3000, DELAY_TIME / 6);
        timer_delay_ms(DELAY_TIME / 3);
        controlServo(id1, 3200, DELAY_TIME / 6);
        timer_delay_ms(DELAY_TIME / 3);
    }

    // 4. ??????????
    performReset();
}




void uplift_hand() {
        controlServo(id1, 3000, DELAY_TIME / 2); // ????????????????1100?
		timer_delay_ms(DELAY_TIME);
		controlServo(id6, right_claw_low_angle, DELAY_TIME / 2);
		timer_delay_ms(DELAY_TIME);
}

void uplift_doublehand() {
		controlServo(id1, 3000, DELAY_TIME / 2);
		controlServo(id7, 400, DELAY_TIME / 2);
		timer_delay_ms(2*DELAY_TIME);
		controlServo(id6, right_claw_low_angle, DELAY_TIME / 2);
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id12, left_claw_low_angle, DELAY_TIME / 2);
}

void alimbo_hand(){
		controlServo(id2, 2300, DELAY_TIME / 2); // ????????????????1100?
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id3, 3100, DELAY_TIME / 2); // ????????????????1100?
		timer_delay_ms(DELAY_TIME/30);
		controlServo(id8, 2300, DELAY_TIME / 2); // ????????????????1100?
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id9, 3100, DELAY_TIME / 2); // ????????????????1100?
}


void uphand_adjust(){
		controlServo(id1, 1700, DELAY_TIME / 2); // ???????????1100??
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id7, 1700, DELAY_TIME / 2); // ???????????1100??
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id2, 2500, DELAY_TIME / 2); // ???????????1100??  2800
		timer_delay_ms(DELAY_TIME/20);
		controlServo(id8, 2500, DELAY_TIME / 2); // ???????????1100??  2800

}






void performPickGarbage(void) {
    controlServo(id6, PICK_CLAW_OPEN, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME / 4);
    controlServo(id1, PICK_ID1_POSITION, DELAY_TIME / 2);
    controlServo(id2, PICK_ID2_POSITION, DELAY_TIME / 2);
    controlServo(id3, PICK_ID3_POSITION, DELAY_TIME / 2);
    controlServo(id4, PICK_ID4_POSITION, DELAY_TIME / 2);
    controlServo(id5, PICK_ID5_POSITION, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);
    controlServo(id6, PICK_CLAW_CLOSE, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME / 2);
    controlServo(id3, RESET_POSITION_ID3, DELAY_TIME / 2);
    controlServo(id4, RESET_POSITION_ID4, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME / 3);
}

void performPlaceGarbageInternal(void) {
    controlServo(id1, PLACE_ID1_POSITION, DELAY_TIME / 2);
    controlServo(id2, PLACE_ID2_POSITION, DELAY_TIME / 2);
    controlServo(id3, PLACE_ID3_POSITION, DELAY_TIME / 2);
    controlServo(id4, PLACE_ID4_POSITION, DELAY_TIME / 2);
    controlServo(id5, PLACE_ID5_POSITION, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);
    controlServo(id6, PICK_CLAW_OPEN, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME / 2);
    performReset();
}

void test_hand()
{
	controlServo(id1, 3000, DELAY_TIME / 2);
    controlServo(id2, 3100, DELAY_TIME / 2);
    controlServo(id7, 400, DELAY_TIME / 2);  //550
    controlServo(id8, 3000, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);
}

void dance_hand() {
    // ?????????????
    uint16_t right_arm[] = {1900, 2000, 2000};
    uint16_t left_arm[] = {1800, 1900, 2050};
    uint8_t right_ids[] = {id2, id3, id4};
    uint8_t left_ids[] = {id8, id9, id10};
    
    for (int i = 0; i < 3; i++) {
        controlServo(right_ids[i], right_arm[i], DELAY_TIME / 2);
        controlServo(left_ids[i], left_arm[i], DELAY_TIME / 2);
    }
    timer_delay_ms(DELAY_TIME/3);
    
    // ??????????????????
    int16_t amplitude = 300;
    uint32_t part1_time = 4000;      // ????????????
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
    
    // ??????????????????????????
    controlServo(id1, 3000, DELAY_TIME / 2);
    controlServo(id2, 3100, DELAY_TIME / 2);
    controlServo(id7, 400, DELAY_TIME / 2);  //550
    controlServo(id8, 3000, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);
    
//    // ?????????????????????
    uint16_t new_right_arm[] = {3100, 2000, 2000};
    uint16_t new_left_arm[] = {3000, 1900, 2050};
    uint8_t remaining_right_ids[] = {id3, id4};
    uint8_t remaining_left_ids[] = {id9, id10};
    
    uint32_t part2_time = 4000;      // ????????????
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
    
    // ???????????????????????????
    controlServo(id1, 1900, DELAY_TIME / 2);
    controlServo(id7, 1600, DELAY_TIME / 2);
    controlServo(id2, 1000, DELAY_TIME / 2); 
    controlServo(id8, 900, DELAY_TIME / 2);
    timer_delay_ms(DELAY_TIME);
    
    // ???????????????????
    uint16_t right_remaining_angles[] = {2000, 2000};
    uint16_t left_remaining_angles[] = {1900, 2050};
    uint8_t right_remaining_ids[] = {id3, id4};  // ???????id3, id4
    uint8_t left_remaining_ids[] = {id9, id10};  // ???????id9, id10
    
    // ????????????
    uint32_t part3_time = 8000;      // ???????????8??
    steps = part3_time / update_interval;  // ?????????
    
    // ??????????????
    right_offset = 0;
    left_offset = 0;
    right_direction = 1;
    left_direction = -1;
    
    // ?????????
    for (uint32_t step = 0; step < steps; step++) {
        // ????????????
        right_offset += right_direction * step_size;
        if (right_offset >= amplitude) {
            right_offset = amplitude;
            right_direction = -1;
        } else if (right_offset <= -amplitude) {
            right_offset = -amplitude;
            right_direction = 1;
        }
        
        // ????????????
        left_offset += left_direction * step_size;
        if (left_offset >= amplitude) {
            left_offset = amplitude;
            left_direction = -1;
        } else if (left_offset <= -amplitude) {
            left_offset = -amplitude;
            left_direction = 1;
        }
        
        // ??????????????????
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
    
//    // ??????????????
//    performReset();
//    timer_delay_ms(DELAY_TIME);
//    
//    int count = 0;
//    while (count < 3) {
//        controlServo(id1, 2600, DELAY_TIME / 2);
//        controlServo(id7, 2100, DELAY_TIME / 2);
//        timer_delay_ms(DELAY_TIME);
//        controlServo(id1, 1500, DELAY_TIME / 2);
//        controlServo(id7, 1000, DELAY_TIME / 2);
//        
//        count++;
//        
//        // ??????????????????
//        if (count < 3) {
//            timer_delay_ms(1500);
//        }
//    }
    
    // ??????
    performReset();
}





