#include "usart_x.h"
#include "avoidance.h"

SEND_DATA Send_Data;

PointDataProcessDef Dataprocess[1000] ;//更新50个数据
LiDARFrameTypeDef Pack_Data;

void Data_Send(void)
{
	unsigned char i = 0;	
	
	for(i=0; i<24; i++)
	{
		usart1_send(Send_Data.buffer[i]);
	}
}

/**************************************************************************
Function: Serial port 1 sends data
Input   : Data to be sent
Output  : none
函数功能：串口1发送数据
入口参数：要发送的数据
返回  值：无
**************************************************************************/
void usart1_send(u8 data)
{
	USART1->DR = data;
	while((USART1->SR&0x40)==0);	
}

/**************************************************************************
Function: Serial port 2 sends data
Input   : Data to be sent
Output  : none
函数功能：串口1发送数据
入口参数：要发送的数据
返回  值：无
**************************************************************************/
void usart2_send(u8 data)
{
	USART2->DR = data;
	while((USART2->SR&0x40)==0);	
}

/**************************************************************************
Function: Serial port 1 is initialized
Input   : Baud rate
Output  : none
函数功能：串口1初始化
入口参数：波特率
返回  值：无
**************************************************************************/
void Usart1_Init(u32 bound)
{
  //GPIO端口设置
  GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;
	 
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1|RCC_APB2Periph_GPIOA, ENABLE);	//使能USART1，GPIOA时钟
  
	//USART1_TX   GPIOA.9
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9; //PA.9
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;	//复用推挽输出
  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化GPIOA.9
  
  //USART1_RX	  GPIOA.10初始化
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;//PA10
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;//浮空输入
  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化GPIOA.10  

   //USART 初始化设置
	USART_InitStructure.USART_BaudRate = bound;//串口波特率
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;//字长为8位数据格式
	USART_InitStructure.USART_StopBits = USART_StopBits_1;//一个停止位
	USART_InitStructure.USART_Parity = USART_Parity_No;//无奇偶校验位
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;//无硬件数据流控制
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;	//收发模
  USART_Init(USART1, &USART_InitStructure); //初始化串口1
	
	NVIC_InitStructure.NVIC_IRQChannel = USART1_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=1;		//抢占优先级
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;				//子优先级
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;	
	NVIC_Init(&NVIC_InitStructure);	
	
  USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);//开启串口接受中断
  USART_Cmd(USART1, ENABLE);                    //使能串口1 
}

/*****
Function: Serial port 1 is initialized
Input   : Baud rate
Output  : none
函数功能：串口3初始化
入口参数：波特率
返回  值：无
**************************************************************************/
void Usart3_Init(u32 bound)
{
  //GPIO端口设置
  GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;
	 
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART3,ENABLE);	//使能USART4
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC | RCC_APB2Periph_AFIO, ENABLE);	//GPIOC时钟

	GPIO_PinRemapConfig(GPIO_PartialRemap_USART3, ENABLE);		//使用PC10、11做串口3收发引脚需要重映射
  
	//USART3_TX   GPIOC.10
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10; //PC.10
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;	//复用推挽输出
  GPIO_Init(GPIOC, &GPIO_InitStructure);//初始化GPIOC.10
  
  //USART3_RX	  GPIOC.11初始化
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_11;//PC11
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;//浮空输入
  GPIO_Init(GPIOC, &GPIO_InitStructure);//初始化GPIOC.11  

   //USART 初始化设置
	USART_InitStructure.USART_BaudRate = bound;//串口波特率
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;//字长为8位数据格式
	USART_InitStructure.USART_StopBits = USART_StopBits_1;//一个停止位
	USART_InitStructure.USART_Parity = USART_Parity_No;//无奇偶校验位
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;//无硬件数据流控制
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;	//收发模
  USART_Init(USART3, &USART_InitStructure); //初始化串口1
	
	NVIC_InitStructure.NVIC_IRQChannel = USART3_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=1;		//抢占优先级
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;				//子优先级
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;	
	NVIC_Init(&NVIC_InitStructure);	
	
  USART_ITConfig(USART3, USART_IT_RXNE, ENABLE);
  NVIC_EnableIRQ(USART3_IRQn);
  USART_Cmd(USART3, ENABLE);                    //使能串口1 
}




/**************************************************************************
Function: Serial port 1 Interrupt handler function
Input   : none
Output  : none
函数功能：串口1中断处理函数
入口参数：无
返回  值：无
**************************************************************************/
int USART1_IRQHandler(void)
{
	static u8 Count=0;
	u8 Usart_Receive;
	if(USART_GetITStatus(USART1, USART_IT_RXNE)!=RESET)
	{
		USART_ClearITPendingBit(USART1, USART_IT_RXNE);
		Usart_Receive = USART_ReceiveData(USART1);//Read the data //读取数据
		//Fill the array with serial data
		//串口数据填入数组
    Receive_Data[Count]=Usart_Receive;
		// Ensure that the first data in the array is FRAME_HEADER
		//确保数组第一个数据为FRAME_HEADER
		if(Usart_Receive == FRAME_HEADER||Count>0) 
			Count++; 
		else 
			Count=0;
		
		if (Count == 11) //Verify the length of the packet //验证数据包的长度
		{   
			Count=0; //Prepare for the serial port data to be refill into the array //为串口数据重新填入数组做准备
			if(Receive_Data[10] == FRAME_TAIL) //Verify the frame tail of the packet //验证数据包的帧尾
			{
				//Data exclusionary or bit check calculation, mode 0 is sent data check
				//数据异或位校验计算，模式0是发送数据校验
				if(Receive_Data[9] ==Check_Sum(9,0))	 
				{	
					//All modes flag position 0, USART3 control mode
					//所有模式标志位置0，为Usart1控制模式						
					Mode = Normal_Mode;
					Car_Mode = ROS_Mode;
					//Calculate the target speed of three axis from serial data, unit m/s
					//从串口数据求三轴目标速度， 单位m/s
					Move_X=XYZ_Target_Speed_transition(Receive_Data[3],Receive_Data[4]);
					Move_Y=XYZ_Target_Speed_transition(Receive_Data[5],Receive_Data[6]);
					Move_Z=XYZ_Target_Speed_transition(Receive_Data[7],Receive_Data[8]);
				}		
			}
		}
	}
	return 0;
}



/**************************************************************************
Function: Calculates the check bits of data to be sent/received
Input   : Count_Number: The first few digits of a check; Mode: 0-Verify the received data, 1-Validate the sent data
Output  : Check result
函数功能：计算要发送/接收的数据校验结果
入口参数：Count_Number：校验的前几位数；Mode：0-对接收数据进行校验，1-对发送数据进行校验
返回  值：校验结果
**************************************************************************/
u8 Check_Sum(unsigned char Count_Number,unsigned char Mode)
{
	unsigned char check_sum=0,k;
	
	//Validate the data to be sent
	//对要发送的数据进行校验
	if(Mode==1)
	for(k=0;k<Count_Number;k++)
	{
		check_sum=check_sum^Send_Data.buffer[k];
	}
	
	//Verify the data received
	//对接收到的数据进行校验
	if(Mode==0)
	for(k=0;k<Count_Number;k++)
	{
	check_sum=check_sum^Receive_Data[k];
	}
	return check_sum;
}

/**************************************************************************
Function: After the top 8 and low 8 figures are integrated into a short type data, the unit reduction is converted
Input   : 8 bits high, 8 bits low
Output  : The target velocity of the robot on the X/Y/Z axis
函数功能：将上位机发过来的高8位和低8位数据整合成一个short型数据后，再做单位还原换算
入口参数：高8位，低8位
返回  值：机器人X/Y/Z轴的目标速度
**************************************************************************/
float XYZ_Target_Speed_transition(u8 High,u8 Low)
{
	//Data conversion intermediate variable
	//数据转换的中间变量
	short transition; 
	
	//将高8位和低8位整合成一个16位的short型数据
	//The high 8 and low 8 bits are integrated into a 16-bit short data
	transition=((High<<8)+Low); 
	return 
		transition/1000+(transition%1000)*0.001; //Unit conversion, mm/s->m/s //单位转换, mm/s->m/s						
}
