#ifndef __CONCTRL_H
#define __CONCTRL_H

#include "sys.h"

#define MOTOR_PWM_MAX 7200
#define MOTOR_STALL_PWM_THRESHOLD 1200
#define MOTOR_STALL_TICKS 25

//Motor speed control related parameters of the structure
//����ٶȿ�����ز����ṹ??
typedef struct  
{
	float Encoder;     //Read the real time speed of the motor by encoder //��������ֵ����ȡ���ʵʱ�ٶ�
	float Motor_Pwm;   //Motor PWM value, control the real-time speed of the motor //���PWM��ֵ�����Ƶ��ʵʱ�ٶ�
	float Target;      //Control the target speed of the motor //���??���ٶ�ֵ�����Ƶ��??���ٶ�
}Motor_parameter;

//�������ṹ��
typedef struct  
{
  int A;      
  int B;
	int C;
	int D;
}Encoder;

//Smoothed the speed of the three axes
//ƽ��������������ٶ�
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
void Set_Open_Loop_Motor(u8 enable);
void Reset_Velocity_PI(void);
void Reset_Smooth_Control(void);
void Chassis_Stop_All(void);
void Motor_Safety_Check(void);

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
