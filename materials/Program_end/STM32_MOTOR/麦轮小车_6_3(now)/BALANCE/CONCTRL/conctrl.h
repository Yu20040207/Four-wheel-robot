#ifndef __CONCTRL_H
#define __CONCTRL_H

#include "sys.h"

//Motor speed control related parameters of the structure
//电机速度控制相关参数结构体
typedef struct  
{
	float Encoder;     //Read the real time speed of the motor by encoder //编码器数值，读取电机实时速度
	float Motor_Pwm;   //Motor PWM value, control the real-time speed of the motor //电机PWM数值，控制电机实时速度
	float Target;      //Control the target speed of the motor //电机目标速度值，控制电机目标速度
}Motor_parameter;

//编码器结构体
typedef struct  
{
  int A;      
  int B;
	int C;
	int D;
}Encoder;

//Smoothed the speed of the three axes
//平滑处理后的三轴速度
typedef struct  
{
	float VX;
	float VY;
	float VZ;
}Smooth_Control;

extern Motor_parameter MOTOR_A, MOTOR_B, MOTOR_C, MOTOR_D;
extern Encoder OriginalEncoder;
extern Smooth_Control smooth_control;

void Drive_Motor(float Vx,float Vy,float Vz);

void TIM2_Init(u16 arr, u16 psc);
void Set_Pwm(int motor_a,int motor_b,int motor_c,int motor_d);
void Get_RC(void);
void Lidar_Avoid_RC(void);
void Lidar_Along_RC(void);
void Lidar_Follow_RC(void);
void Get_Velocity_Form_Encoder(void);
int Incremental_PI_A (float Encoder,float Target);
int Incremental_PI_B (float Encoder,float Target);
int Incremental_PI_C (float Encoder,float Target);
int Incremental_PI_D (float Encoder,float Target);
float Along_Adjust_PID(float Current_Distance,float Target_Distance);
float Follow_Turn_PID(float Current_Angle,float Target_Angle);
float Distance_Adjust_PID(float Current_Distance,float Target_Distance);
void Smooth_control(float vx,float vy,float vz);
u8 Turn_Off( int voltage);
float float_abs(float insert);
float target_limit_float(float insert,float low,float high);
int target_limit_int(int insert,int low,int high);
void Key_Scan(void);
void data_transition(void);


#endif
