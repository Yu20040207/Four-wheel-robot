#include "bsp.h"

/**
  * 函数：LED初始化
  * 参数：无
  * 返回值：无
  */
void LED_Init(void)
{
    /* 开启GPIOC的时钟 */
	GPIO_InitTypeDef GPIO_InitStructure;
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);

    /* GPIO初始化结构体 */
    

    /* 配置PC13为推挽输出模式 */
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_13;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOC, &GPIO_InitStructure);

    /* 设置GPIO初始化后的默认电平 */
    GPIO_SetBits(GPIOC, GPIO_Pin_13);              // 设置PC13引脚为高电平（LED关闭）
}

/**
  * 函数：LED开启
  * 参数：无
  * 返回值：无
  */
void LED_ON(void)
{
    GPIO_ResetBits(GPIOC, GPIO_Pin_13);    // 设置PC13引脚为低电平（LED开启）
}

/**
  * 函数：LED关闭
  * 参数：无
  * 返回值：无
  */
void LED_OFF(void)
{
    GPIO_SetBits(GPIOC, GPIO_Pin_13);      // 设置PC13引脚为高电平（LED关闭）
}

/**
  * 函数：LED状态翻转
  * 参数：无
  * 返回值：无
  */
void LED_Turn(void)
{
    if (GPIO_ReadOutputDataBit(GPIOC, GPIO_Pin_13) == 0) // 获取输出寄存器的状态，如果当前引脚输出低电平
    {
        GPIO_SetBits(GPIOC, GPIO_Pin_13);             // 则设置PC13引脚为高电平
    }
    else                                              // 否则，即当前引脚输出高电平
    {
        GPIO_ResetBits(GPIOC, GPIO_Pin_13);           // 则设置PC13引脚为低电平
    }
}
