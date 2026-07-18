#include "sys.h"
#include "usart2_handler.h"
#include "LineFollow.h"

// 现有变量定义...
int Count=0;
u16 adc_val;
u32 voltage;
u8 Car_Mode=0, Mode=0;
float Axle_spacing = MEC_axlespacing;
float Wheel_spacing = MEC_wheelspacing;
float Velocity_KP=300,Velocity_KI=300;
float Along_Distance_KP = 163,Along_Distance_KI = 1,Along_Distance_KD = 123;
float Distance_KP = -0.150f,Distance_KI = -0.001,Distance_KD = -0.052f;
float Follow_KP = -2.566f,Follow_KI = -0.001f,Follow_KD = -1.368f;
//float Move_X, Move_Y, Move_Z;
float RC_Velocity=350;
u8 Flag_Direction;
u8 PID_Send;
u8 Flag_Left, Flag_Right;
u8 Receive_Data[12];


int main(void)
{
    // 初始化系统时钟
    SystemInit();
    
    // 1. 最简初始化 - 仅设置中断和延时
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);
    delay_init(72);
    
    // 2. 立即初始化电机控制
    Motor_Init();                   // 所有控制引脚置零，STBY=0
    
    // 3. 延长电源稳定等待时间
    delay_ms(300);                  // 增加至300ms
    
    // 4. 初始化编码器（此时电机安全）
    Encoder_TIM2_Init();
    Encoder_TIM3_Init();
    Encoder_TIM4_Init();
    Encoder_TIM5_Init();
    
    // 5. 初始化PWM - 关键步骤
    // 确保PWM初始化在这里完成
    
    // 6. 初始化其他外设
    LED_Init();
    ADC1_Init();
    Key_Init();
    Usart1_Init(115200);  // 初始化串口1，波特率115200
    USART2_Init();        // 初始化串口2
    Usart3_Init(115200);  // 初始化串口3（用于巡线传感器）
    OLED_Init();
    TIM6_Init(71, 9999);
    
    // 7. 安全启动电机系统
    Motor_Safe_Start();
    TIM8_Init(7199, 0);
    
    // 初始化模式
    Mode = Normal_Mode;
    Car_Mode = ROS_Mode; 
    Motor_Control_Init();
    Avoidance_Init();
    
    // 初始化巡线传感器功能
    LineFollow_Init();
    
    // 初始化系统滴答定时器 (1ms中断)
    SysTick_Config(SystemCoreClock / 1000);
    
while(1) {
    // 处理串口2接收的数据
    USART2_ProcessData();
    
    // 只有当巡线模式未启用时，才处理其他控制逻辑
    if (!line_follow_enabled) {
        // 1. 更新避障控制
        Avoidance_Update();
        
        // 2. 只有当避障未激活时，才处理底轮控制
        if (!Is_Avoidance_Active()) {
            Motor_Control_Update();
        }
        
        // 3. 只有当避障未激活时，才处理其他控制模式
        if (!Is_Avoidance_Active()) {
            if(Mode == Normal_Mode && Car_Mode == ROS_Mode) {
                data_transition();
                Data_Send();
            }
        }
    } else {
        // 巡线模式启用时，只处理巡线逻辑
        LineFollow_Process();
    }
    
    // 4. 显示更新
    Show();
    APP_Show();
    
    delay_us(100);
}
}
