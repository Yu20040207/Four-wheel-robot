#include "bsp.h"
#include "i2c_ctl.h"

int main(void)
{
    // 初始化系统时钟等
	Delay_ms(3000);				  //等待WiFi初始化完成
    SystemInit();
    
    // 初始化外设
    USART1_Init(115200);            // 机械臂驱动
    USART2_Init(115200);            // 语音接收
    USART3_Init(115200);            // 超声波发送
    TIM_Delay_Configuration();      // 配置延时
    LED_Init();                     // 初始化LED
    LED_ON();             	        // 初始关闭LED（超声波关闭状态）
	
    // 初始化I2C总线 - 必须先于其他I2C设备初始化
    I2C_Bus_Init();
    
    
    // 初始化其他模块
    Ultrasonic_Init();              // 超声波初始化
    SerialDispose_Init();           // 串口处理初始化
	//performHandshake();   // 执行握手动作
    
	performReset();                 // 复位机械臂
    
    // 初始化SysTick定时器（1ms中断）
    if (SysTick_Config(SystemCoreClock / 1000)) {
        // 捕获错误
        while (1);
    }

    while (1)
    {
        
        
		// 1. 处理超声波测量（完全封装在模块内）
        Ultrasonic_Process();
        
        // 2. 处理串口数据
        SerialDispose_Process();
        
        // 3. 添加短延时减少CPU负载
        Delay_ms(1);
    }
}
