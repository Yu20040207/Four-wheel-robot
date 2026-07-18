#include "conctrl.h"

Motor_parameter MOTOR_A, MOTOR_B, MOTOR_C, MOTOR_D;
Encoder OriginalEncoder;
Smooth_Control smooth_control;
u8 open_loop_motor_test = 0;
static u8 motor_stall_ticks[4];
static u8 motor_safety_latched = 0;

void Set_Open_Loop_Motor(u8 enable)
{
	open_loop_motor_test = enable ? 1 : 0;
	if (!open_loop_motor_test) {
		Reset_Velocity_PI();
	}
}

void Drive_Motor(float Vx,float Vy,float Vz)   //-1.5-1.5
{
	float amplitude=3.5; //Wheel target speed limit //����Ŀ���ٶ��޷�
	
	Smooth_control(Vx,Vy,Vz); //Smoothing the input speed //�������ٶȽ���ƽ������
  
	//Get the smoothed data 
	//��ȡƽ�������������			
	Vx=smooth_control.VX;     
	Vy=smooth_control.VY;
	Vz=smooth_control.VZ;
	
	//Inverse kinematics //�˶�ѧ���
	MOTOR_A.Target   = +Vy+Vx-Vz*(Axle_spacing+Wheel_spacing);
	MOTOR_B.Target   = -Vy+Vx-Vz*(Axle_spacing+Wheel_spacing);
	MOTOR_C.Target   = +Vy+Vx+Vz*(Axle_spacing+Wheel_spacing);
	MOTOR_D.Target   = -Vy+Vx+Vz*(Axle_spacing+Wheel_spacing);

	//Wheel (motor) target speed limit //����(���)Ŀ���ٶ��޷�
	MOTOR_A.Target=target_limit_float(MOTOR_A.Target,-amplitude,amplitude); 
	MOTOR_B.Target=target_limit_float(MOTOR_B.Target,-amplitude,amplitude); 
	MOTOR_C.Target=target_limit_float(MOTOR_C.Target,-amplitude,amplitude); 
	MOTOR_D.Target=target_limit_float(MOTOR_D.Target,-amplitude,amplitude); 
}

int TIM6_IRQHandler(void)
{
    static int tick = 0;  // ��̬��������¼�жϴ���

    if (TIM_GetITStatus(TIM6, TIM_IT_Update) != RESET)
    {
        TIM_ClearITPendingBit(TIM6, TIM_IT_Update);  // ����жϱ�־λ

        tick++;
        if (tick >= 100)  // ÿ 100 ���ж���˸һ�Σ�Լ 1 �룩
        {
            tick = 0;
            //LED = ~LED;  // ��ת LED ״̬   ���Դ���ʱ�ر���
        }

        // ԭ�еĿ����߼�
        Get_Velocity_Form_Encoder();
        Key_Scan();
        Motor_Safety_Check();

        if (Mode == Normal_Mode)
        {
//            if (Car_Mode == APP_Mode)
//                Get_RC();
//            else
                Drive_Motor(Move_X, Move_Y, Move_Z);
        }
        else if (Mode == Lidar_Mode)
        {
            if (Car_Mode == Lidar_Avoid_Mode)
                Lidar_Avoid_RC();
            else if (Car_Mode == Lidar_Along_Mode)
                Lidar_Along_RC();
            else if (Car_Mode == Lidar_Follow_Mode)
                Lidar_Follow_RC();
        }

        if (Turn_Off(voltage) == 0)
        {
            if (motor_safety_latched)
            {
                Set_Pwm(0, 0, 0, 0);
            }
            else if (open_loop_motor_test)
            {
                int test_pwm = 1500;
                if (MOTOR_A.Target < -0.01f || MOTOR_B.Target < -0.01f ||
                    MOTOR_C.Target < -0.01f || MOTOR_D.Target < -0.01f) {
                    test_pwm = -1500;
                } else if (MOTOR_A.Target > 0.01f || MOTOR_B.Target > 0.01f ||
                           MOTOR_C.Target > 0.01f || MOTOR_D.Target > 0.01f) {
                    test_pwm = 1500;
                } else {
                    test_pwm = 0;
                }
                MOTOR_A.Motor_Pwm = test_pwm;
                MOTOR_B.Motor_Pwm = test_pwm;
                MOTOR_C.Motor_Pwm = test_pwm;
                MOTOR_D.Motor_Pwm = test_pwm;
            }
            else
            {
                MOTOR_A.Motor_Pwm = Incremental_PI_A(MOTOR_A.Encoder, MOTOR_A.Target);
                MOTOR_B.Motor_Pwm = Incremental_PI_B(MOTOR_B.Encoder, MOTOR_B.Target);
                MOTOR_C.Motor_Pwm = Incremental_PI_C(MOTOR_C.Encoder, MOTOR_C.Target);
                MOTOR_D.Motor_Pwm = Incremental_PI_D(MOTOR_D.Encoder, MOTOR_D.Target);
            }
            Set_Pwm(MOTOR_A.Motor_Pwm, MOTOR_B.Motor_Pwm, MOTOR_C.Motor_Pwm, MOTOR_D.Motor_Pwm);
        }
        else
        {
            Reset_Velocity_PI();
        }
    }

    return 0;
}


/**************************************************************************
Function: Assign a value to the PWM register to control wheel speed and direction
Input   : PWM
Output  : none
�������ܣ���ֵ��PWM�Ĵ��������Ƴ���ת���뷽��
��ڲ�����PWM
����  ֵ����
**************************************************************************/
void Set_Pwm(int motor_a,int motor_b,int motor_c,int motor_d)
{
	// 每次输出 PWM 前确保驱动芯片退出待机（TB6612 STBY 必须为高）
	MOTOR_ENABLE();
	TIM_CtrlPWMOutputs(TIM8, ENABLE);

	// TB6612：PWM=0 时 IN1=IN2=0 为安全停止，避免 IN 脚残留导致某路 H 桥异常导通
	if (motor_a == 0)       AIN1 = 0, AIN2 = 0, PWMA = 0;
	else if (motor_a < 0)   AIN1 = 1, AIN2 = 0, PWMA = -motor_a;
	else                    AIN1 = 0, AIN2 = 1, PWMA = motor_a;

	if (motor_b == 0)       BIN1 = 0, BIN2 = 0, PWMB = 0;
	else if (motor_b < 0)   BIN1 = 1, BIN2 = 0, PWMB = -motor_b;
	else                    BIN1 = 0, BIN2 = 1, PWMB = motor_b;

	if (motor_c == 0)       CIN1 = 0, CIN2 = 0, PWMC = 0;
	else if (motor_c < 0)   CIN1 = 1, CIN2 = 0, PWMC = -motor_c;
	else                    CIN1 = 0, CIN2 = 1, PWMC = motor_c;

	if (motor_d == 0)       DIN1 = 0, DIN2 = 0, PWMD = 0;
	else if (motor_d < 0)   DIN1 = 1, DIN2 = 0, PWMD = -motor_d;
	else                    DIN1 = 0, DIN2 = 1, PWMD = motor_d;
}

void Get_RC(void)
{
	u8 Flag_Move=1;
	
	switch(Flag_Direction)  //Handle direction control commands //���������������
 { 
		case 1:      Move_X=RC_Velocity;  	 Move_Y=0;             Flag_Move=1;    break;
		case 2:      Move_X=RC_Velocity;  	 Move_Y=RC_Velocity;   Flag_Move=1; 	 break;
		case 3:      Move_X=0;      		     Move_Y=RC_Velocity;   Flag_Move=1; 	 break;
		case 4:      Move_X=-RC_Velocity;  	 Move_Y=RC_Velocity;   Flag_Move=1;    break;
		case 5:      Move_X=-RC_Velocity;  	 Move_Y=0;             Flag_Move=1;    break;
		case 6:      Move_X=-RC_Velocity;  	 Move_Y=-RC_Velocity;  Flag_Move=1;    break;
		case 7:      Move_X=0;     	 		     Move_Y=-RC_Velocity;  Flag_Move=1;    break;
		case 8:      Move_X=RC_Velocity; 	   Move_Y=-RC_Velocity;  Flag_Move=1;    break; 
		default:     Move_X=0;               Move_Y=0;             Flag_Move=0;    break;
 }
 if(Flag_Move==0)		
 {	
	 //If no direction control instruction is available, check the steering control status
	 //����޷������ָ����ת�����״̬
	 if     (Flag_Left ==1)  Move_Z= Pi/2*(RC_Velocity/500); //left rotation  //����ת  
	 else if(Flag_Right==1)  Move_Z=-Pi/2*(RC_Velocity/500); //right rotation //����ת
	 else 		               Move_Z=0;                       //stop           //ֹͣ
 }
	//Unit conversion, mm/s -> m/s
  //��λת����mm/s -> m/s	
	Move_X=Move_X/1000;       Move_Y=Move_Y/1000;         Move_Z=Move_Z;
	 
	//Control target value is obtained and kinematics analysis is performed
	//�õ�����Ŀ��ֵ�������˶�ѧ����
	Drive_Motor(Move_X,Move_Y,Move_Z);
}

/**************************************************************************
�������ܣ�С������ģʽ
��ڲ�������
����  ֵ����
**************************************************************************/
void Lidar_Avoid_RC(void)
{
	int i = 0; 
	u8 calculation_angle_cnt = 0;	//�����ж�225��������Ҫ�����ϵĵ�
	int angle_sum = 0;			//���Լ����ϰ���λ���������
	u8 distance_count = 0;			//����С��ĳֵ�ļ���
	for(i=0;i<450;i++)				//����120�ȷ�Χ�ڵľ������ݣ���120�������ҵ�����
	{
		if((Dataprocess[i].angle>300)||(Dataprocess[i].angle<60))  //���ϽǶ���300-60֮��
		{
			if((0<Dataprocess[i].distance)&&(Dataprocess[i].distance<Avoid_Distance))	//����С��450mm��Ҫ����,ֻ��Ҫ120�ȷ�Χ�ڵ�
			{
				calculation_angle_cnt++;						 			//�������С�ڱ��Ͼ���ĵ����
				if(Dataprocess[i].angle<60)		
					angle_sum += Dataprocess[i].angle;
				else if(Dataprocess[i].angle>300)
					angle_sum += (Dataprocess[i].angle-360);	//300�ȵ�60��ת��Ϊ-60�ȵ�60��
				if(Dataprocess[i].distance<Avoid_Min_Distance)				//��¼С��200mm�ĵ�ļ���
					distance_count++;
			}
	  }
	}
  Move_X = forward_velocity;
  if(calculation_angle_cnt == 0)//����Ҫ����
	{
		Move_Z = 0;
	}
	else                          //������С��200mm��С��������
	{
		if(distance_count>8)
		{
			Move_X = -forward_velocity;
			Move_Z = 0;
		}
		else
		{
			if(angle_sum > 0)//�ϰ���ƫ��
			{
					Move_X = 0;
				  Move_Z=other_corner_velocity;//��ת
			}
			else		//ƫ��
			{
					Move_X = 0;
					Move_Z=-other_corner_velocity;
			}
	  }
	}
	Drive_Motor(Move_X,Move_Y,Move_Z);
}

/**************************************************************************
�������ܣ�С����ֱ��ģʽ
��ڲ�������
����  ֵ����
**************************************************************************/
void Lidar_Along_RC(void)
{
	static u32 target_distance=0;
	static int i=0;
	int j;

	u32 distance;
	u8 data_count = 0;			//�����˳�һд���ļ�������
	
	Move_X = forward_velocity;  //��ʼ�ٶ�
	
	for(j=0;j<450;j++) //225
	{
		if(Dataprocess[j].angle>268 && Dataprocess[j].angle<272)   //ȡ�״��4�ȵĵ�
		{
			if(i==0)
			{
				target_distance=Dataprocess[j].distance;  //�״ﲶ���һ������
				i++;
			}
		  if(Dataprocess[j].distance<(target_distance+limit_distance))//����һ���״��̽�����
		  {
			  data_count++;
			  distance=Dataprocess[j].distance;//ʵʱ����
		  }
		}
	}
	Move_Y=-Along_Adjust_PID(distance,target_distance);
	Move_X = forward_velocity;
	Move_Z = 0;
	if(data_count == 0)  //��data_count����0��ֻ��ǰ���ٶ�
	{
		Move_Y = 0;
		Move_Z = 0;
	}
	Drive_Motor(Move_X,Move_Y,Move_Z);
}

/**************************************************************************
�������ܣ�С������ģʽ
��ڲ�������
����  ֵ����
**************************************************************************/
void Lidar_Follow_RC(void)
{
	static u16 cnt = 0;
	int i;
	int calculation_angle_cnt = 0;
	static float angle = 0;				//���ϵĽǶ�
	static float last_angle = 0;		//
	u16 mini_distance = 65535;
	static u8 data_count = 0;			//�����˳�һд���ļ�������
	//��Ҫ�ҳ�������Ǹ���ĽǶ�
	for(i = 0; i < 450; i++)
	{
			if((100<Dataprocess[i].distance)&&(Dataprocess[i].distance<Follow_Distance))
			{
				calculation_angle_cnt++;
				if(Dataprocess[i].distance<mini_distance)
				{
					mini_distance = Dataprocess[i].distance;
					angle = Dataprocess[i].angle;
				}
			}
	}
	if(angle > 180)  //0--360��ת����0--180��-180--0��˳ʱ�룩
		angle -= 360;
	if((angle-last_angle > 10)||(angle-last_angle < -10))   //��һ����������������10�ȵ���Ҫ���ж�
	{
		if(++data_count > 30)   //����30�βɼ�����ֵ(300ms��)���ϴεıȴ���10�ȣ���ʱ������Ϊ����Чֵ
		{
			data_count = 0;
			last_angle = angle;
		}
	}
	else    //����С��10�ȵĿ���ֱ����Ϊ����Чֵ
	{
//		if(++data_count > 10)   //����10�βɼ�����ֵ(100ms��)����ʱ������Ϊ����Чֵ
//		{
			data_count = 0;
			last_angle = angle;
//		}
	}
	if(calculation_angle_cnt < 6)  //�������С��8�ҵ�cnt>40��ʱ����Ϊ��1600��û�и���Ŀ��
	{
		if(cnt < 40)
			cnt++;
		if(cnt >= 40)
		{
			Move_X = 0;
			Move_Z = 0;
		}
	}
	else
	{
		cnt = 0;
		if(Move_X > 0.06f || Move_X < -0.06f)  //��Move_X���ٶ�ʱ��ת��PID��ʼ����
		{
			if(mini_distance < 700 && (last_angle > 60 || last_angle < -60))
			{
				Move_Z = -0.0298f*last_angle;  //������ƫС�ҽǶȲ�����ֱ�ӿ���ת��
			}
			else
			{
				  Move_Z = -Follow_Turn_PID(last_angle,0);		//ת��PID����ͷ��Զ���Ÿ�����Ʒ
			}
		}
		else
		{
			Move_Z = 0;
		}
		if(angle>150 || angle<-150)  //���С���ں�60����Ҫ�������˶��Լ�����ת��
		{
			Move_X = -Distance_Adjust_PID(mini_distance, Keep_Follow_Distance);
			Move_Z = -0.0298f*last_angle;
		}
		else
		{
		  Move_X = Distance_Adjust_PID(mini_distance, Keep_Follow_Distance);  //���־��뱣����500mm
		}
		Move_X = target_limit_float(Move_X,-amplitude_limiting,amplitude_limiting);   //��ǰ���ٶ��޷�
	}
	Drive_Motor(Move_X,Move_Y,Move_Z);
}


void Get_Velocity_Form_Encoder(void)
{
	//Retrieves the original data of the encoder
	//��ȡ��������ԭʼ����
	int Encoder_A_pr,Encoder_B_pr,Encoder_C_pr,Encoder_D_pr; 
	
	OriginalEncoder.A = Read_Encoder(5);
	OriginalEncoder.B = Read_Encoder(3);
	OriginalEncoder.C = Read_Encoder(4);
	OriginalEncoder.D = Read_Encoder(2);
	
	Encoder_A_pr = OriginalEncoder.A;
	Encoder_B_pr = OriginalEncoder.B;
	Encoder_C_pr = OriginalEncoder.C;
	Encoder_D_pr = OriginalEncoder.D;
	
	//The encoder converts the raw data to wheel speed in mm/s
	//编码器原始数据转为轮速，单位mm/s
	//速度 = 编码器增量 * 100 * (0.100*Pi) / Encoder_precision
	MOTOR_A.Encoder = Encoder_A_pr*CONTROL_FREQUENCY*Wheel_perimeter/Encoder_precision;
	MOTOR_B.Encoder = Encoder_B_pr*CONTROL_FREQUENCY*Wheel_perimeter/Encoder_precision;
	MOTOR_C.Encoder = Encoder_C_pr*CONTROL_FREQUENCY*Wheel_perimeter/Encoder_precision;
	MOTOR_D.Encoder = Encoder_D_pr*CONTROL_FREQUENCY*Wheel_perimeter/Encoder_precision;
	
}

/**************************************************************************
Function: Incremental PI controller
Input   : Encoder measured value (actual speed), target speed
Output  : Motor PWM
According to the incremental discrete PID formula
pwm+=Kp[e��k��-e(k-1)]+Ki*e(k)+Kd[e(k)-2e(k-1)+e(k-2)]
e(k) represents the current deviation
e(k-1) is the last deviation and so on
PWM stands for incremental output
In our speed control closed loop system, only PI control is used
pwm+=Kp[e��k��-e(k-1)]+Ki*e(k)

�������ܣ�����ʽPI������
��ڲ���������������ֵ(ʵ���ٶ�)��Ŀ���ٶ�
����  ֵ�����PWM
��������ʽ��ɢPID��ʽ 
pwm+=Kp[e��k��-e(k-1)]+Ki*e(k)+Kd[e(k)-2e(k-1)+e(k-2)]
e(k)��������ƫ�� 
e(k-1)������һ�ε�ƫ��  �Դ����� 
pwm�����������
�����ǵ��ٶȿ��Ʊջ�ϵͳ���棬ֻʹ��PI����
pwm+=Kp[e��k��-e(k-1)]+Ki*e(k)
**************************************************************************/
typedef struct {
	float pwm;
	float last_bias;
} VelocityPIState;

static VelocityPIState velocity_pi_state[4];

static float motor_absf(float v)
{
	return (v < 0.0f) ? -v : v;
}

static u8 motor_check_stall(float pwm, float encoder, float target, u8 idx)
{
	float abs_pwm;
	float abs_enc;
	float abs_tgt;

	abs_pwm = motor_absf(pwm);
	abs_enc = motor_absf(encoder);
	abs_tgt = motor_absf(target);

	if (abs_pwm >= (float)MOTOR_STALL_PWM_THRESHOLD && abs_tgt > 8.0f && abs_enc < 4.0f) {
		if (motor_stall_ticks[idx] < 255) {
			motor_stall_ticks[idx]++;
		}
		if (motor_stall_ticks[idx] >= MOTOR_STALL_TICKS) {
			return 1;
		}
	} else {
		motor_stall_ticks[idx] = 0;
	}
	return 0;
}

void Motor_Safety_Check(void)
{
	if (motor_safety_latched) {
		return;
	}

	if (motor_check_stall(MOTOR_A.Motor_Pwm, MOTOR_A.Encoder, MOTOR_A.Target, 0) ||
	    motor_check_stall(MOTOR_B.Motor_Pwm, MOTOR_B.Encoder, MOTOR_B.Target, 1) ||
	    motor_check_stall(MOTOR_C.Motor_Pwm, MOTOR_C.Encoder, MOTOR_C.Target, 2) ||
	    motor_check_stall(MOTOR_D.Motor_Pwm, MOTOR_D.Encoder, MOTOR_D.Target, 3)) {
		motor_safety_latched = 1;
		Move_X = 0.0f;
		Move_Y = 0.0f;
		Move_Z = 0.0f;
		Reset_Smooth_Control();
		Reset_Velocity_PI();
		Motor_StopOutputs();
		motor_stall_ticks[0] = 0;
		motor_stall_ticks[1] = 0;
		motor_stall_ticks[2] = 0;
		motor_stall_ticks[3] = 0;
	}
}

static int run_velocity_pi(VelocityPIState *state, float encoder, float target)
{
	float bias;

	bias = target - encoder;
	/* 目标速度为 0 时快速泄放 PWM，避免增量 PI 残留导致某轮不停 */
	if (target > -0.004f && target < 0.004f) {
		state->pwm *= 0.55f;
		if (state->pwm > -12 && state->pwm < 12) {
			state->pwm = 0;
			state->last_bias = 0;
			return 0;
		}
		state->last_bias = bias;
		return (int)state->pwm;
	}
	state->pwm += Velocity_KP * (bias - state->last_bias) + Velocity_KI * bias;
	if (state->pwm > MOTOR_PWM_MAX) state->pwm = MOTOR_PWM_MAX;
	if (state->pwm < -MOTOR_PWM_MAX) state->pwm = -MOTOR_PWM_MAX;
	state->last_bias = bias;
	return (int)state->pwm;
}

void Reset_Velocity_PI(void)
{
	velocity_pi_state[0].pwm = 0;
	velocity_pi_state[0].last_bias = 0;
	velocity_pi_state[1].pwm = 0;
	velocity_pi_state[1].last_bias = 0;
	velocity_pi_state[2].pwm = 0;
	velocity_pi_state[2].last_bias = 0;
	velocity_pi_state[3].pwm = 0;
	velocity_pi_state[3].last_bias = 0;
	MOTOR_A.Motor_Pwm = 0;
	MOTOR_B.Motor_Pwm = 0;
	MOTOR_C.Motor_Pwm = 0;
	MOTOR_D.Motor_Pwm = 0;
	MOTOR_A.Target = 0.0f;
	MOTOR_B.Target = 0.0f;
	MOTOR_C.Target = 0.0f;
	MOTOR_D.Target = 0.0f;
	Set_Pwm(0, 0, 0, 0);
	Motor_StopOutputs();
}

void Reset_Smooth_Control(void)
{
	smooth_control.VX = 0.0f;
	smooth_control.VY = 0.0f;
	smooth_control.VZ = 0.0f;
}

void Chassis_Stop_All(void)
{
	Move_X = 0.0f;
	Move_Y = 0.0f;
	Move_Z = 0.0f;
	Reset_Smooth_Control();
	Reset_Velocity_PI();
	motor_stall_ticks[0] = 0;
	motor_stall_ticks[1] = 0;
	motor_stall_ticks[2] = 0;
	motor_stall_ticks[3] = 0;
	motor_safety_latched = 0;
}

int Incremental_PI_A (float Encoder,float Target)
{
	return run_velocity_pi(&velocity_pi_state[0], Encoder, Target);
}
int Incremental_PI_B (float Encoder,float Target)
{
	return run_velocity_pi(&velocity_pi_state[1], Encoder, Target);
}
int Incremental_PI_C (float Encoder,float Target)
{
	return run_velocity_pi(&velocity_pi_state[2], Encoder, Target);
}
int Incremental_PI_D (float Encoder,float Target)
{
	return run_velocity_pi(&velocity_pi_state[3], Encoder, Target);
}

/**************************************************************************
Function: Distance_Adjust_PID
Input   : Current_Distance;Target_Distance
Output  : OutPut
�������ܣ���ֱ���״����pid
��ڲ���: ��ǰ�����Ŀ�����
����  ֵ�����Ŀ���ٶ�
**************************************************************************/	 	
//��ֱ���״�������pid

float Along_Adjust_PID(float Current_Distance,float Target_Distance)//�������PID
{
	static float Bias,OutPut,Integral_bias,Last_Bias;
	Bias=Target_Distance-Current_Distance;                          	//����ƫ��
	Integral_bias+=Bias;	                                 			//���ƫ��Ļ���
	if(Integral_bias>1000) Integral_bias=1000;
	else if(Integral_bias<-1000) Integral_bias=-1000;
	OutPut=-Along_Distance_KP*Bias/100000-Along_Distance_KI*Integral_bias/100000-Along_Distance_KD*(Bias-Last_Bias)/1000;//λ��ʽPID������
	Last_Bias=Bias;                                       		 			//������һ��ƫ��
	if(Turn_Off(voltage)== 1)								//����رգ���ʱ��������
		Integral_bias = 0;
	return OutPut;                                          	
}

/**************************************************************************
Function: Follow_Turn_PID
Input   : Current_Angle;Target_Angle
Output  : OutPut
�������ܣ������״�ת��pid
��ڲ���: ��ǰ�ǶȺ�Ŀ��Ƕ�
����  ֵ�����ת���ٶ�
**************************************************************************/	 	
//�����״�ת��pid
float Follow_Turn_PID(float Current_Angle,float Target_Angle)
{
	static float Bias,OutPut,Integral_bias,Last_Bias;
	Bias=Target_Angle-Current_Angle;                         				 //����ƫ��
	Integral_bias+=Bias;	                                 				 //���ƫ��Ļ���
	if(Integral_bias>1000) Integral_bias=1000;
	else if(Integral_bias<-1000) Integral_bias=-1000;
	OutPut=(Follow_KP/100)*Bias+(Follow_KI/100)*Integral_bias+(Follow_KD/100)*(Bias-Last_Bias);	//λ��ʽPID������
	Last_Bias=Bias;                                       					 		//������һ��ƫ��
	if(Turn_Off(voltage)== 1)								//����رգ���ʱ��������
		Integral_bias = 0;
	return OutPut;                                           					 	//���
	
}

/**************************************************************************
Function: Distance_Adjust_PID
Input   : Current_Distance;Target_Distance
Output  : OutPut
�������ܣ������״����pid
��ڲ���: ��ǰ�����Ŀ�����
����  ֵ�����Ŀ���ٶ�
**************************************************************************/	 	
//�����״�������pid
float Distance_Adjust_PID(float Current_Distance,float Target_Distance)//�������PID
{
	static float Bias,OutPut,Integral_bias,Last_Bias;
	Bias=Target_Distance-Current_Distance;                          	//����ƫ��
	Integral_bias+=Bias;	                                 			//���ƫ��Ļ���
	if(Integral_bias>1000) Integral_bias=1000;
	else if(Integral_bias<-1000) Integral_bias=-1000;
	OutPut=Distance_KP*Bias/100+Distance_KI*Integral_bias/100+Distance_KD*(Bias-Last_Bias)/100;//λ��ʽPID������
	Last_Bias=Bias;                                       		 			//������һ��ƫ��
	if(Turn_Off(voltage)== 1)								//����رգ���ʱ��������
		Integral_bias = 0;
	return OutPut;                                          	
}

/**************************************************************************
Function: Smoothing the three axis target velocity
Input   : Three-axis target velocity
Output  : none
�������ܣ�������Ŀ���ٶ���ƽ������
��ڲ���������Ŀ���ٶ�
����  ֵ����
**************************************************************************/
void Smooth_control(float vx,float vy,float vz)
{
	float step=0.1;

	if	   (vx>0) 	smooth_control.VX+=step;
	else if(vx<0)		smooth_control.VX-=step;
	else if(vx==0)	smooth_control.VX=smooth_control.VX*0.9f;
	
	if	   (vy>0)   smooth_control.VY+=step;
	else if(vy<0)		smooth_control.VY-=step;
	else if(vy==0)	smooth_control.VY=smooth_control.VY*0.9f;
	
	if	   (vz>0) 	smooth_control.VZ+=step;
	else if(vz<0)		smooth_control.VZ-=step;
	else if(vz==0)	smooth_control.VZ=smooth_control.VZ*0.9f;
	
	smooth_control.VX=target_limit_float(smooth_control.VX,-float_abs(vx),float_abs(vx));
	smooth_control.VY=target_limit_float(smooth_control.VY,-float_abs(vy),float_abs(vy));
	smooth_control.VZ=target_limit_float(smooth_control.VZ,-float_abs(vz),float_abs(vz));
}

/**************************************************************************
Function: Check the battery voltage, enable switch status, software failure flag status
Input   : Voltage
Output  : Whether control is allowed, 1: not allowed, 0 allowed
�������ܣ�����ص�ѹ��ʹ�ܿ���״̬������ʧ�ܱ�־λ״̬
��ڲ�������ѹ
����  ֵ���Ƿ��������ƣ�1����������0����
**************************************************************************/
u8 Turn_Off( int voltage)
{
	// voltage 单位：0.01V，1000 = 10.00V；未采样前为 0，不能误判为低电压
	if (voltage == 0) {
		return 0;
	}
	if (voltage < 1000) {
		return 1;
	}
	return 0;
}

/**************************************************************************
Function: Floating-point data calculates the absolute value
Input   : float
Output  : The absolute value of the input number
�������ܣ����������ݼ������ֵ
��ڲ�����������
����  ֵ���������ľ���ֵ
**************************************************************************/
float float_abs(float insert)
{
	if(insert>=0) return insert;
	else return -insert;
}

/**************************************************************************
Function: Limiting function
Input   : Value
Output  : none
�������ܣ��޷�����
��ڲ�������ֵ
����  ֵ����
**************************************************************************/
float target_limit_float(float insert,float low,float high)
{
    if (insert < low)
        return low;
    else if (insert > high)
        return high;
    else
        return insert;	
}
int target_limit_int(int insert,int low,int high)
{
    if (insert < low)
        return low;
    else if (insert > high)
        return high;
    else
        return insert;	
}

/**************************************************************************
Function: Limiting function
Input   : none
Output  : none
�������ܣ��޷�����
��ڲ�������
����  ֵ����
**************************************************************************/
void Key_Scan(void)
{
	u8 tmp=0;
	tmp=click_N_Double(50);
	
	if(tmp==1)
	{
		if(Mode==Lidar_Mode)					
		{
			Car_Mode++;
			if(Car_Mode==3)								Car_Mode=0;
		}
	}
	else if(tmp==2)
	{
		if(Mode==Normal_Mode)					
		{
			Mode=Lidar_Mode,Car_Mode=Lidar_Avoid_Mode;
			Move_X=0,Move_Y=0,Move_Z=0;
		}
		else if(Mode==Lidar_Mode)			
		{
			Move_X=0,Move_Y=0,Move_Z=0;
			Mode=Normal_Mode,Car_Mode=ROS_Mode;
		}
	}
}

/**************************************************************************
Function: The data sent by the serial port is assigned
Input   : none
Output  : none
�������ܣ����ڷ��͵����ݽ��и�ֵ
��ڲ�������
����  ֵ����
**************************************************************************/
void data_transition(void)
{
	Send_Data.Sensor_Str.Frame_Header = FRAME_HEADER; //Frame_header //֡ͷ
	Send_Data.Sensor_Str.Frame_Tail = FRAME_TAIL;     //Frame_tail //֡β
	
	Send_Data.Sensor_Str.X_speed = ((MOTOR_A.Encoder+MOTOR_B.Encoder+MOTOR_C.Encoder+MOTOR_D.Encoder)/4)*1000;
	Send_Data.Sensor_Str.Y_speed = ((MOTOR_A.Encoder-MOTOR_B.Encoder+MOTOR_C.Encoder-MOTOR_D.Encoder)/4)*1000; 
	Send_Data.Sensor_Str.Z_speed = ((-MOTOR_A.Encoder-MOTOR_B.Encoder+MOTOR_C.Encoder+MOTOR_D.Encoder)/4/(Axle_spacing+Wheel_spacing))*1000; 
	
	//The acceleration of the triaxial acceleration //���ٶȼ�������ٶ�
	Send_Data.Sensor_Str.Accelerometer.X_data= imu.accel.y; //The accelerometer Y-axis is converted to the ros coordinate X axis //���ٶȼ�Y��ת����ROS����X��
	Send_Data.Sensor_Str.Accelerometer.Y_data=-imu.accel.x; //The accelerometer X-axis is converted to the ros coordinate y axis //���ٶȼ�X��ת����ROS����Y��
	Send_Data.Sensor_Str.Accelerometer.Z_data= imu.accel.z; //The accelerometer Z-axis is converted to the ros coordinate Z axis //���ٶȼ�Z��ת����ROS����Z��
	
	//The Angle velocity of the triaxial velocity //���ٶȼ�������ٶ�
	Send_Data.Sensor_Str.Gyroscope.X_data= imu.gyro.y; //The Y-axis is converted to the ros coordinate X axis //���ٶȼ�Y��ת����ROS����X��
	Send_Data.Sensor_Str.Gyroscope.Y_data=-imu.gyro.x; //The Y-axis is converted to the ros coordinate Y axis //���ٶȼ�Y��ת����ROS����Y��
	Send_Data.Sensor_Str.Gyroscope.Y_data= imu.gyro.z; //The Z-axis is converted to the ros coordinate Z axis //���ٶȼ�Z��ת����ROS����Z��
	
	//Battery voltage (this is a thousand times larger floating point number, which will be reduced by a thousand times as well as receiving the data).
	//��ص�ѹ(���ｫ�������Ŵ�һǧ�����䣬��Ӧ���ڽ��ն��ڽ��յ����ݺ�Ҳ����Сһǧ��)
	Send_Data.Sensor_Str.Power_Voltage = voltage*10; 
	
	Send_Data.buffer[0]=Send_Data.Sensor_Str.Frame_Header; //Frame_heade //֡ͷ
  Send_Data.buffer[1]=0; 				//This is reserved, can be expanded  //��Ϊ����������������չ
	
	//The three-axis speed of / / car is split into two eight digit Numbers
	//С�������ٶ�,���ᶼ���Ϊ����8λ�����ٷ���
	Send_Data.buffer[2]=Send_Data.Sensor_Str.X_speed >>8; 
	Send_Data.buffer[3]=Send_Data.Sensor_Str.X_speed ;    
	Send_Data.buffer[4]=Send_Data.Sensor_Str.Y_speed>>8;  
	Send_Data.buffer[5]=Send_Data.Sensor_Str.Y_speed;     
	Send_Data.buffer[6]=Send_Data.Sensor_Str.Z_speed >>8; 
	Send_Data.buffer[7]=Send_Data.Sensor_Str.Z_speed ;    
	
	//The acceleration of the triaxial axis of / / imu accelerometer is divided into two eight digit reams
	//IMU���ٶȼ�������ٶ�,���ᶼ���Ϊ����8λ�����ٷ���
	Send_Data.buffer[8]=Send_Data.Sensor_Str.Accelerometer.X_data>>8; 
	Send_Data.buffer[9]=Send_Data.Sensor_Str.Accelerometer.X_data;   
	Send_Data.buffer[10]=Send_Data.Sensor_Str.Accelerometer.Y_data>>8;
	Send_Data.buffer[11]=Send_Data.Sensor_Str.Accelerometer.Y_data;
	Send_Data.buffer[12]=Send_Data.Sensor_Str.Accelerometer.Z_data>>8;
	Send_Data.buffer[13]=Send_Data.Sensor_Str.Accelerometer.Z_data;
	
	//The axis of the triaxial velocity of the / /imu is divided into two eight digits
	//IMU���ٶȼ�������ٶ�,���ᶼ���Ϊ����8λ�����ٷ���
	Send_Data.buffer[14]=Send_Data.Sensor_Str.Gyroscope.X_data>>8;
	Send_Data.buffer[15]=Send_Data.Sensor_Str.Gyroscope.X_data;
	Send_Data.buffer[16]=Send_Data.Sensor_Str.Gyroscope.Y_data>>8;
	Send_Data.buffer[17]=Send_Data.Sensor_Str.Gyroscope.Y_data;
	Send_Data.buffer[18]=Send_Data.Sensor_Str.Gyroscope.Z_data>>8;
	Send_Data.buffer[19]=Send_Data.Sensor_Str.Gyroscope.Z_data;
	
	//Battery voltage, split into two 8 digit Numbers
	//��ص�ѹ,���Ϊ����8λ���ݷ���
	Send_Data.buffer[20]=Send_Data.Sensor_Str.Power_Voltage >>8; 
	Send_Data.buffer[21]=Send_Data.Sensor_Str.Power_Voltage; 

  //Data check digit calculation, Pattern 1 is a data check
  //����У��λ���㣬ģʽ1�Ƿ�������У��
	Send_Data.buffer[22]=Check_Sum(22,1); 
	
	Send_Data.buffer[23]=Send_Data.Sensor_Str.Frame_Tail; //Frame_tail //֡β
}



