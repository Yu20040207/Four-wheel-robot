#include "host_hal.h"
#include "usart2_handler.h"
#include "voice_control.h"
#include "LineFollow.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #condition); exit(1); \
} } while (0)
static void near_zero(float value) { CHECK(fabsf(value) < 0.00001f); }
static void pwm_and_directions_zero(void) {
    CHECK(PWMA == 0 && PWMB == 0 && PWMC == 0 && PWMD == 0);
    CHECK(AIN1 == 0 && AIN2 == 0 && BIN1 == 0 && BIN2 == 0);
    CHECK(CIN1 == 0 && CIN2 == 0 && DIN1 == 0 && DIN2 == 0);
}
static void electrical_zero(void) {
    pwm_and_directions_zero();
    CHECK(STBY == 0);
    CHECK(host_enable_while_stopped() == 0);
}
static void state_zero(void) {
    near_zero(Move_X); near_zero(Move_Y); near_zero(Move_Z);
    near_zero(MOTOR_A.Target); near_zero(MOTOR_B.Target);
    near_zero(MOTOR_C.Target); near_zero(MOTOR_D.Target);
    near_zero(MOTOR_A.Motor_Pwm); near_zero(MOTOR_B.Motor_Pwm);
    near_zero(MOTOR_C.Motor_Pwm); near_zero(MOTOR_D.Motor_Pwm);
    near_zero(smooth_control.VX); near_zero(smooth_control.VY); near_zero(smooth_control.VZ);
    CHECK(host_pi_is_zero());
}
static void stopped_clean(void) {
    CHECK(Chassis_IsStopped()); CHECK(!Chassis_StopPending());
    CHECK(!line_follow_enabled && !Is_Autonomous_Avoidance_Enabled());
    CHECK(!Is_Avoidance_Active() && !Is_Voice_Control_Enabled());
    CHECK(Mode == Normal_Mode && Car_Mode == ROS_Mode);
    CHECK(Flag_Direction == 0 && Flag_Left == 0 && Flag_Right == 0);
    CHECK(host_lf_is_clean() && host_uart2_is_clean());
    state_zero(); electrical_zero();
}
static void initialize(void) {
    host_reset_hal(); host_set_fault(0);
    Avoidance_Init(); Voice_Control_Init(); LineFollow_ResetController();
    Chassis_RequestStop(); Chassis_ServiceStop();
    stopped_clean();
}
static void process(void) { USART2_ProcessData(); Motor_Control_Update(); }
static void start(void) {
    host_feed_text("START\r\n"); process();
    CHECK(!Chassis_IsStopped()); CHECK(!Chassis_StopPending()); state_zero();
}
static void moving(void) {
    start(); host_feed_text("G1\r\n"); process(); host_tick();
    CHECK(Move_X > 0.0f); CHECK(PWMA || PWMB || PWMC || PWMD); CHECK(STBY);
}
static void ros_frame(uint8_t frame[11]) {
    unsigned i;
    memset(frame, 0, 11); frame[0] = FRAME_HEADER;
    frame[3] = 0x01; frame[4] = 0xF4; /* Arbitrary +500 protocol value, not measured speed. */
    for (i = 0; i < 9; ++i) frame[9] ^= frame[i];
    frame[10] = FRAME_TAIL;
}
static void stop_same_burst(void) {
    moving(); host_feed_text("S\r\nG1\r\n");
    CHECK(Chassis_IsStopped() && Chassis_StopPending()); electrical_zero();
    host_tick(); electrical_zero(); process(); stopped_clean();
    host_tick(); state_zero(); electrical_zero();
}
static void stop_old_enables(void) {
    const char *bursts[] = {"6\r\nS\r\n", "8\r\nS\r\n", "A\r\nS\r\n",
        "S\r\n6\r\n", "S\r\n8\r\n", "S\r\nA\r\n"};
    unsigned i;
    for (i = 0; i < sizeof bursts / sizeof bursts[0]; ++i) {
        start(); host_feed_text(bursts[i]); CHECK(Chassis_IsStopped());
        process(); stopped_clean();
    }
}
static void stop_all_modes(void) {
    const char *enables[] = {"6\r\n", "8\r\n", "A\r\n"};
    unsigned i;
    for (i = 0; i < 3; ++i) {
        start(); host_feed_text(enables[i]); process();
        host_feed_text(i == 1 ? "stop\r\n" : "S\r\n");
        CHECK(Chassis_IsStopped()); electrical_zero(); process(); stopped_clean();
    }
    start(); Mode = Lidar_Mode; Car_Mode = Lidar_Avoid_Mode;
    host_tick(); host_feed_text("stop\r\n"); process(); stopped_clean();
}
static void feed_distances(const char *csv) {
    host_feed_text(csv); USART2_ProcessData(); Avoidance_Update();
}
static void stop_and_probe_producers(const char *stop_command) {
    uint8_t line_byte = 0x40;
    host_feed_text(stop_command); CHECK(Chassis_IsStopped()); electrical_zero();
    process(); stopped_clean();
    feed_distances("100,100,100,100,100,100\r\n");
    host_feed_uart(3, &line_byte, 1);
    LineFollow_Process(); Voice_Control_Update(); host_tick(); stopped_clean();
    start(); Avoidance_Update(); LineFollow_Process(); Voice_Control_Update();
    host_tick(); CHECK(!Chassis_IsStopped()); state_zero(); pwm_and_directions_zero();
}
static void actual_producers_stop(void) {
    const char *stops[] = {"S\r\n", "stop\r\n"};
    const char *near_csv[] = {"40,10,20,100,100,100\r\n", "20,10,40,100,100,100\r\n"};
    unsigned s, side, tick;
    uint8_t line_byte = 0x40;
    for (s = 0; s < 2; ++s) {
        start(); host_feed_text("6\r\n"); process();
        feed_distances("100,100,100,100,100,100\r\n");
        CHECK(Move_X > 0 && !Is_Avoidance_Active()); host_tick(); CHECK(PWMA != 0);
        stop_and_probe_producers(stops[s]);
        host_feed_text("6\r\n"); process(); feed_distances(near_csv[0]);
        CHECK(Is_Avoidance_Active() && Get_Avoidance_State() == AVOIDANCE_BACKWARD);
        CHECK(Move_X < 0); host_tick(); CHECK(PWMA != 0);
        stop_and_probe_producers(stops[s]);
        for (side = 0; side < 2; ++side) {
            host_feed_text("6\r\n"); process(); feed_distances(near_csv[side]);
            CHECK(Get_Avoidance_State() == AVOIDANCE_BACKWARD);
            for (tick = 1; tick <= BACKWARD_TIME_MS; ++tick) {
                host_avoidance_tick();
                /* Fresh frames prevent the existing 500 ms sensor timeout. */
                if (tick % 100 == 0) feed_distances(near_csv[side]);
            }
            CHECK(Get_Avoidance_State() == (side == 0 ? AVOIDANCE_TURN_LEFT : AVOIDANCE_TURN_RIGHT));
            feed_distances(near_csv[side]);
            CHECK(Move_X > 0 && (side == 0 ? Move_Y > 0 : Move_Y < 0)); near_zero(Move_Z);
            host_tick(); CHECK(PWMA || PWMB || PWMC || PWMD);
            stop_and_probe_producers(stops[s]);
        }
        host_feed_text("8\r\n"); process(); host_feed_uart(3, &line_byte, 1);
        LineFollow_Process(); CHECK(Move_X > 0 && fabsf(Move_Z) > 0);
        CHECK(!host_lf_is_clean()); host_tick(); CHECK(PWMA || PWMB || PWMC || PWMD);
        stop_and_probe_producers(stops[s]);
        host_feed_text("A\r\n"); process(); feed_distances("100,100,100,100,100,100\r\n");
        host_feed_text("G1\r\n"); process(); Voice_Control_Update();
        CHECK(Is_Voice_Control_Enabled() && Move_X > 0); host_tick(); CHECK(PWMA != 0);
        stop_and_probe_producers(stops[s]);
        host_feed_text("S\r\n"); process(); stopped_clean();
    }
}
static void pending_command_cancelled(void) {
    start(); host_feed_text("G1\r\n"); USART2_ProcessData();
    host_feed_text("S\r\n"); Motor_Control_Update();
    CHECK(Chassis_IsStopped()); electrical_zero(); process(); stopped_clean();
}
static void start_requires_consumed_stop(void) {
    moving(); host_feed_text("S\r\nSTART\r\nG1\r\n");
    CHECK(!Chassis_Start()); CHECK(Chassis_IsStopped());
    process(); stopped_clean();
    host_feed_text("G1\r\n6\r\n8\r\nA\r\n"); process(); stopped_clean();
    start(); host_tick(); state_zero();
    host_feed_text("G1\r\n"); process(); host_tick(); CHECK(PWMA != 0);
}
static void old_sensors_do_not_resume(void) {
    moving(); host_feed_text("S\r\n"); process();
    host_feed_text("100,100,100,100,100,100\r\n");
    { uint8_t byte = 0x18; host_feed_uart(3, &byte, 1); }
    USART2_ProcessData(); Avoidance_Update(); Voice_Control_Update(); LineFollow_Process();
    host_tick(); CHECK(Chassis_IsStopped()); state_zero(); electrical_zero();
    start(); host_tick(); state_zero();
}
static void fresh_modes_require_start(void) {
    const char *enables[] = {"6\r\n", "8\r\n", "A\r\n"};
    unsigned i;
    for (i = 0; i < 3; ++i) {
        host_feed_text(enables[i]); process(); CHECK(Chassis_IsStopped());
        CHECK(!line_follow_enabled && !Is_Autonomous_Avoidance_Enabled() && !Is_Voice_Control_Enabled());
    }
    start(); host_feed_text("6\r\n"); process(); CHECK(Is_Autonomous_Avoidance_Enabled());
    host_feed_text("S\r\n"); process(); start();
    host_feed_text("8\r\n"); process(); CHECK(line_follow_enabled);
    host_feed_text("S\r\n"); process(); start();
    host_feed_text("A\r\n"); process(); CHECK(Is_Voice_Control_Enabled());
}
static void disable_is_global_stop(void) {
    const char *disables[] = {"7\r\n", "9\r\n", "B\r\n"};
    unsigned i;
    for (i = 0; i < 3; ++i) {
        moving(); host_feed_text(disables[i]); CHECK(Chassis_IsStopped());
        electrical_zero(); process(); stopped_clean();
    }
}
static void ros_cannot_bypass(void) {
    uint8_t frame[11]; ros_frame(frame);
    host_feed_uart(1, frame, sizeof frame); host_tick(); stopped_clean();
    start(); host_feed_uart(1, frame, 5);
    host_feed_text("S\r\n"); process(); start();
    host_feed_uart(1, frame + 5, 6); host_tick(); state_zero();
    host_feed_uart(1, frame, sizeof frame); host_tick(); CHECK(PWMA != 0);
    host_feed_text("S\r\n"); process();
    host_feed_uart(1, frame, sizeof frame); host_tick(); stopped_clean();
}
static void radar_key_openloop_cannot_bypass(void) {
    unsigned mode;
    host_set_key(2); host_tick(); CHECK(host_key_reads() == 0); stopped_clean();
    for (mode = 0; mode < 3; ++mode) {
        Mode = Lidar_Mode; Car_Mode = (u8)mode;
        Set_Open_Loop_Motor(1); host_tick(); electrical_zero();
    }
    /* Service a repeated STOP to cancel the deliberately injected mode flags. */
    Chassis_RequestStop(); Chassis_ServiceStop(); stopped_clean();
}
static void direct_outputs_cannot_bypass(void) {
    Drive_Motor(1, 1, 1); Set_Pwm(100, -100, 100, -100);
    state_zero(); electrical_zero();
    Set_Open_Loop_Motor(1); host_tick(); state_zero(); electrical_zero();
}
static void stop_clears_history_preserves_fault(void) {
    uint8_t byte = 0x40;
    moving(); host_seed_pi(2345, 1); smooth_control.VX = 2; smooth_control.VY = 1;
    Flag_Direction = 3; Flag_Left = Flag_Right = 1;
    host_feed_uart(3, &byte, 1); host_feed_text("100,100,100,100,100,100\r\nG");
    MOTOR_A.Encoder = 101; MOTOR_B.Encoder = -102; MOTOR_C.Encoder = 103; MOTOR_D.Encoder = -104;
    OriginalEncoder.A = 11; OriginalEncoder.B = -12; OriginalEncoder.C = 13; OriginalEncoder.D = -14;
    host_set_fault(1); host_feed_text("\r\nS\r\n");
    CHECK(Chassis_IsStopped()); electrical_zero(); process(); stopped_clean();
    CHECK(MOTOR_A.Encoder == 101 && MOTOR_B.Encoder == -102 && MOTOR_C.Encoder == 103 && MOTOR_D.Encoder == -104);
    CHECK(OriginalEncoder.A == 11 && OriginalEncoder.B == -12 && OriginalEncoder.C == 13 && OriginalEncoder.D == -14);
    CHECK(host_get_fault()); Chassis_Stop_All(); CHECK(host_get_fault());
    start(); host_feed_text("G1\r\n"); process(); host_tick();
    CHECK(host_get_fault()); CHECK(PWMA == 0 && PWMB == 0 && PWMC == 0 && PWMD == 0);
}
static void partial_uart2_discarded(void) {
    moving(); host_feed_text("S\r\nSTA"); process(); stopped_clean();
    host_feed_text("RT\r\n"); process(); CHECK(Chassis_IsStopped());
    start(); host_feed_text("G1\r\n"); process(); CHECK(Move_X > 0);
}
static void fragmented_start_survives_main_loop(void) {
    host_feed_text("STA"); process(); CHECK(Chassis_IsStopped());
    host_tick(); electrical_zero();
    host_feed_text("RT\r\n"); process(); CHECK(!Chassis_IsStopped()); state_zero();
    host_feed_text("S\r\n"); process(); stopped_clean();
    host_feed_text("S"); process(); CHECK(Chassis_IsStopped());
    host_feed_text("T"); process(); CHECK(Chassis_IsStopped());
    host_feed_text("A"); process(); CHECK(Chassis_IsStopped());
    host_feed_text("R"); process(); CHECK(Chassis_IsStopped());
    host_feed_text("T\r\n"); process(); CHECK(!Chassis_IsStopped()); state_zero();
}
static void authorization_is_exact(void) {
    const char *invalid[] = {"STAR$T\r\n", "STARTx\r\n", "S TART\r\n", "START!\r\n", "start\r\n"};
    char overlong[96];
    unsigned i;
    for (i = 0; i < sizeof invalid / sizeof invalid[0]; ++i) {
        host_feed_text(invalid[i]); process(); stopped_clean();
    }
    memcpy(overlong, "START", 5); memset(overlong + 5, 'x', 88);
    overlong[93] = '\r'; overlong[94] = '\n'; overlong[95] = '\0';
    host_feed_text(overlong); process(); stopped_clean();
    host_feed_text("START\r\nS\r\n"); process(); stopped_clean();
    start(); host_feed_text("START\r\nS\r\n"); process(); stopped_clean();
    start(); host_feed_text("S\r"); CHECK(Chassis_IsStopped()); process(); stopped_clean();
    start(); host_feed_text("S\n"); CHECK(Chassis_IsStopped()); process(); stopped_clean();
}
static void delayed_stop_during_consume(void) {
    start(); host_feed_text("G1\r\n");
    /* Unmask 1 is ServiceStop; unmask 2 follows the real command-slot consume. */
    host_schedule_text_after_unmasks("S\r\n", 2); USART2_ProcessData();
    CHECK(host_scheduled_deliveries() == 1); CHECK(Chassis_IsStopped()); electrical_zero();
    Motor_Control_Update(); process(); stopped_clean();
}
static void delayed_stop_during_start(void) {
    host_feed_text("START\r\n");
    /* Deliver STOP only after Chassis_Start's nested mask returns to the caller. */
    host_schedule_text_after_unmasks("S\r\n", 2); USART2_ProcessData();
    CHECK(host_scheduled_deliveries() == 1); CHECK(Chassis_IsStopped()); electrical_zero();
    process(); stopped_clean();
}
static void stop_interrupts_control_output(void) {
    moving(); host_schedule_stop_on_encoder(); host_tick();
    CHECK(Chassis_IsStopped()); electrical_zero(); process(); stopped_clean();
    moving(); host_schedule_stop_on_pwm(); Set_Pwm(100, 100, 100, 100);
    CHECK(Chassis_IsStopped()); electrical_zero(); process(); stopped_clean();
}
static void zero_unknown_not_global_stop(void) {
    start(); host_feed_text("V000N00\r\n"); process(); CHECK(!Chassis_IsStopped()); state_zero();
    host_feed_text("unknown\r\n"); process(); CHECK(!Chassis_IsStopped()); state_zero();
    host_feed_text("G1\r\n"); process(); CHECK(Move_X > 0);
}
struct Test { const char *name; void (*run)(void); };
static const struct Test tests[] = {
    {"stop_same_burst", stop_same_burst}, {"stop_old_enables", stop_old_enables},
    {"stop_all_modes", stop_all_modes}, {"pending_command_cancelled", pending_command_cancelled},
    {"actual_producers_stop", actual_producers_stop},
    {"start_requires_consumed_stop", start_requires_consumed_stop},
    {"old_sensors_do_not_resume", old_sensors_do_not_resume},
    {"fresh_modes_require_start", fresh_modes_require_start},
    {"disable_is_global_stop", disable_is_global_stop}, {"ros_cannot_bypass", ros_cannot_bypass},
    {"radar_key_openloop_cannot_bypass", radar_key_openloop_cannot_bypass},
    {"direct_outputs_cannot_bypass", direct_outputs_cannot_bypass},
    {"stop_clears_history_preserves_fault", stop_clears_history_preserves_fault},
    {"partial_uart2_discarded", partial_uart2_discarded},
    {"fragmented_start_survives_main_loop", fragmented_start_survives_main_loop},
    {"authorization_is_exact", authorization_is_exact},
    {"delayed_stop_during_consume", delayed_stop_during_consume},
    {"delayed_stop_during_start", delayed_stop_during_start},
    {"stop_interrupts_control_output", stop_interrupts_control_output},
    {"zero_unknown_not_global_stop", zero_unknown_not_global_stop}
};
int main(int argc, char **argv) {
    unsigned i;
    if (argc != 2) return 2;
    if (strcmp(argv[1], "--list") == 0) {
        for (i = 0; i < sizeof tests / sizeof tests[0]; ++i) puts(tests[i].name);
        return 0;
    }
    for (i = 0; i < sizeof tests / sizeof tests[0]; ++i) if (strcmp(argv[1], tests[i].name) == 0) {
        initialize(); tests[i].run(); printf("PASS %s\n", tests[i].name); return 0;
    }
    fprintf(stderr, "Unknown test: %s\n", argv[1]); return 2;
}
