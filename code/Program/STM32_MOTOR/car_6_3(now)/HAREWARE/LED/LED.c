#include "LED.h"

/**************************************************************************
Function: Initialization of LED
Input   : none
Output  : none
函数功能：LED初始化
入口参数：无
返回  值：无
**************************************************************************/
void LED_Init(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_14;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOB, &GPIO_InitStructure);
}

/**************************************************************************
Function: LED flash
Input   : The number of times the function is executed
Output  : none
函数功能：LED闪烁
入口参数：函数执行的次数
返回  值：无
**************************************************************************/
void LED_Flash(u8 time)
{
	static int LED_delay=0;
	if(time==0)					LED = 0;															//无延时时长，直接让LED灯常亮
	else if(++LED_delay==time)			LED=~LED,LED_delay=0;			//放在固定频率就会执行一次的函数中，每执行多少次该函数就会切换一次LED状态
}

/**************************************************************************
Function: Switch with LED 
Input   : LED status: 0 off, 1 on
Output  : none
函数功能：LED开关
入口参数：LED灯的状态：0 灭， 1 亮
返回  值：无
**************************************************************************/
void LED_Switch(u8 state)
{
	u8 temp = state;
	if(temp==0)				LED = 1;
	else							LED = 0;
}

/**************************************************************************
Function: LED turn over
Input   : none
Output  : none
函数功能：LED翻转
入口参数：无
返回  值：无
**************************************************************************/
void LED_TURN(void)
{
    LED = !LED;  // 直接翻转LED状态
}
