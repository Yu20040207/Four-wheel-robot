#include "bsp.h"

/* 配置串口1，设置波特率 */
void USART1_Init(u32 baud_rate)
{
  GPIO_InitTypeDef GPIO_InitStructure;
  USART_InitTypeDef USART_InitStructure;
  //使能USART1，GPIOA时钟
  RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_USART1, ENABLE);
  /*
  *  USART1_TX -> PA9 , USART1_RX ->	PA10
  */
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP; //复用推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
  GPIO_Init(GPIOA, &GPIO_InitStructure);

  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING; //浮空输入
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
  GPIO_Init(GPIOA, &GPIO_InitStructure);

  USART_InitStructure.USART_BaudRate = baud_rate; //串口波特率
  USART_InitStructure.USART_WordLength = USART_WordLength_8b; //字长为8位数据格式
  USART_InitStructure.USART_StopBits = USART_StopBits_1; //一个停止位
  USART_InitStructure.USART_Parity = USART_Parity_No; //无奇偶校验位
  USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None; //无硬件数据流控制
  USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx; //收发模式

  NVIC_Configuration();
  USART_Init(USART1, &USART_InitStructure);
  USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);//开启串口接收中断

  USART_Cmd(USART1, ENABLE);
}

//配置USART1接收中断
void NVIC_Configuration(void)
{
  NVIC_InitTypeDef NVIC_InitStructure;
  /* Configure the NVIC Preemption Priority Bits */
  NVIC_PriorityGroupConfig(NVIC_PriorityGroup_3);

  /* Enable the USARTy Interrupt */
  NVIC_InitStructure.NVIC_IRQChannel = USART1_IRQn;
  NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 3; //抢占优先级3
  NVIC_InitStructure.NVIC_IRQChannelSubPriority = 3; //子优先级3
  NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
  NVIC_Init(&NVIC_InitStructure); //根据指定的参数初始化NVIC寄存器
}

//串口1中断服务程序
void USART1_IRQHandler(void)
{
  u8 Res;
  if (USART_GetITStatus(USART1, USART_IT_RXNE) != RESET) //接收中断(接收到的数据必须是0x0d 0x0a结尾)
  {
    Res = USART_ReceiveData(USART1); //读取接收到的数据
    bus_servo_uart_recv(Res);
  }
}

/*****************  发送一个字符 **********************/
static void Usart_SendByte(USART_TypeDef *pUSARTx, uint8_t ch)
{
  /* 发送一个字节数据到USART1 */
  USART_SendData(pUSARTx, ch);

  /* 等待发送完毕 */
  while (USART_GetFlagStatus(pUSARTx, USART_FLAG_TXE) == RESET)
    ;
}
/*****************  指定长度的发送字符串 **********************/
void Usart_SendStr_length(uint8_t *str, uint32_t strlen)
{
  unsigned int k = 0;
  do
  {
    Usart_SendByte(USART1, *(str + k));
    k++;
  } while (k < strlen);
}

/*****************  发送字符串 **********************/
void Usart_SendString(uint8_t *str)
{
  unsigned int k = 0;
  do
  {
    Usart_SendByte(USART1, *(str + k));
    k++;
  } while (*(str + k) != '\0');
}

//加入以下代码,支持printf函数
#pragma import(__use_no_semihosting)
//标准库需要的支持函数
struct __FILE
{
  int handle;
};
FILE __stdout;
//定义_sys_exit()以避免使用半主机模式
// 重定向半主机函数
void _sys_exit(int x)
{
  x = x;
}
//重定义fputc函数
int fputc(int ch, FILE *f)
{
  while ((USART1->SR & 0X40) == 0)
    ; //循环发送,直到发送完毕
  USART1->DR = (u8)ch;
  return ch;
}

/// 重定向c库函数scanf到USART1
int fgetc(FILE *f)
{
  /* 等待串口1输入数据 */
  while (USART_GetFlagStatus(USART1, USART_FLAG_RXNE) == RESET)
    ;

  return (int)USART_ReceiveData(USART1);
}
