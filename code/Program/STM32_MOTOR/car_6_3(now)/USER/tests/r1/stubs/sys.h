#ifndef __SYS_H
#define __SYS_H
#include "stm32f10x.h"
extern uint32_t host_gpio_bits[4][16];
#define PAout(n) host_gpio_bits[0][n]
#define PBout(n) host_gpio_bits[1][n]
#define PCout(n) host_gpio_bits[2][n]
#define PDout(n) host_gpio_bits[3][n]
#define PWMA (TIM8->CCR1)
#define PWMB (TIM8->CCR2)
#define PWMC (TIM8->CCR3)
#define PWMD (TIM8->CCR4)
#define Normal_Mode 0
#define Lidar_Mode 1
#define ROS_Mode 0
#define APP_Mode 1
#define Lidar_Avoid_Mode 0
#define Lidar_Follow_Mode 1
#define Lidar_Along_Mode 2
#define Pi 3.14159265358979f
/* Artificial host values: no wheel/encoder calibration is inferred or tested. */
#define CONTROL_FREQUENCY 100
#define Wheel_perimeter 1.0f
#define Encoder_precision 1.0f
#define Keep_Follow_Distance 400
#define Follow_Distance 1600
#define Avoid_Min_Distance 300
#define Avoid_Distance 450
#define forward_velocity 0.3f
#define corner_velocity 0.5f
#define other_corner_velocity 1.0f
#define amplitude_limiting 0.6f
#define limit_distance 100
extern u32 voltage;
extern u8 Car_Mode, Mode, Flag_Direction, PID_Send, Flag_Left, Flag_Right;
extern u8 Receive_Data[12], Lidar_Success_Receive_flag;
extern float Axle_spacing, Wheel_spacing, Velocity_KP, Velocity_KI;
extern float Along_Distance_KP, Along_Distance_KI, Along_Distance_KD;
extern float Distance_KP, Distance_KI, Distance_KD;
extern float Follow_KP, Follow_KI, Follow_KD, RC_Velocity;
extern volatile uint32_t system_tick;
typedef struct { float x, y, z; } HostVector;
typedef struct { HostVector accel, gyro; } HostImu;
extern HostImu imu;
void delay_ms(u32);
void delay_us(u32);
int Read_Encoder(u8);
u8 click_N_Double(u8);
void LED_TURN(void);
#include "control.h"
#include "conctrl.h"
#include "motor.h"
#include "usart_x.h"
#include "avoidance.h"
#endif
