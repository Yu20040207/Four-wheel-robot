#include "KEY.h"

/**************************************************************************
Function: Initialization of KEY
Input   : none
Output  : none
函数功能：按键初始化
入口参数：无
返回  值：无
**************************************************************************/
void Key_Init(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_15;
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU;
	GPIO_Init(GPIOB, &GPIO_InitStructure);
}

/**************************************************************************
Function: Buttons to scan
Input   : none
Output  : none
函数功能：按键扫描
入口参数：无
返回  值：按键状态 0：无动作 1：单击 
**************************************************************************/
u8 click(void)
{
	//Press the release sign
	//按键按松开标志
	static u8 flag_key=1;
	
	if(flag_key&&KEY==0)
	{
	 flag_key=0; //The key is pressed //按键按下
	 return 1;	
	}
	else if(1==KEY)			
		flag_key=1;
	return 0; //No key is pressed //无按键按下
}

/**************************************************************************
Function: Buttons to scan
Input   : Double click wait time
Output  : Button status: 0- no action, 1- click, 2- double click
函数功能：按键扫描
入口参数：双击等待时间
返回  值：按键状态: 0-无动作, 1-单击, 2-双击 
**************************************************************************/
u8 click_N_Double (u8 time)
{
	static	u8 flag_key,count_key,double_key;	
	static	u16 count_single,Forever_count;
	if(KEY==0)  Forever_count++;   //长按标志位未置1
	else        Forever_count=0;
	if(0==KEY&&0==flag_key)		flag_key=1;	//第一次按下
	if(0==count_key)
	{
			if(flag_key==1) 
			{
				double_key++;
				count_key=1;			//标记按下一次
			}
			if(double_key==2) 
			{										//按下两次
				double_key=0;
				count_single=0;
				return 2;					//双击执行的指令
			}
	}
	if(1==KEY)			flag_key=0,count_key=0;
	
	if(1==double_key)
	{
		count_single++;
		if(count_single>time&&Forever_count<time)
		{
			double_key=0;
			count_single=0;	//超时不标记为双击
		return 1;//单击执行的指令
		}
		if(Forever_count>time)
		{
			double_key=0;
			count_single=0;	
		}
	}	
	return 0;
}






