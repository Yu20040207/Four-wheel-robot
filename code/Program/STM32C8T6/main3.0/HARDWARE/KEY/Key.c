#include "bsp.h"


/**
  * 函数：按键初始化
  * 参数：无
  * 返回值：无
  */
void Key_Init(void)
{
    /* GPIO初始化结构体 */
    GPIO_InitTypeDef GPIO_InitStructure;
    /* 开启GPIOB的时钟 */
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB, ENABLE);
    /* 开启GPIOA的时钟 */
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA, ENABLE);

    /* 配置PB12, PB13, PB14, PB15为上拉输入模式（公共端接3.3V，所以用上拉） */
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IPU; // 上拉输入模式
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_12 | GPIO_Pin_13 | GPIO_Pin_14 | GPIO_Pin_15;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    /* 配置PA8为上拉输入模式 */
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_8;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
}

uint8_t Key_GetNum(void)
{
    uint8_t KeyNum = 0; // 定义变量，默认键码值为0
    uint16_t i; // 声明循环变量

    // 检测PB12按键
    if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_12) == 1) // 检测高电平（公共端接3.3V）
    {
        // 延时消抖
        for(i = 0; i < 10000; i++);
        // 再次确认按键状态
        if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_12) == 1)
        {
            while (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_12) == 1); // 等待按键松手
            KeyNum = 1; // 按键1对应的键码值为1
        }
    }
    // 检测PB13按键
    else if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_13) == 1) // 检测高电平
    {
        // 延时消抖
        for(i = 0; i < 10000; i++);
        // 再次确认按键状态
        if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_13) == 1)
        {
            while (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_13) == 1);
            KeyNum = 2;
        }
    }
    // 检测PB14按键
    else if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_14) == 1) // 检测高电平
    {
        // 延时消抖
        for(i = 0; i < 10000; i++);
        // 再次确认按键状态
        if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_14) == 1)
        {
            while (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_14) == 1);
            KeyNum = 3;
        }
    }
    // 检测PB15按键
    else if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_15) == 1) // 检测高电平
    {
        // 延时消抖
        for(i = 0; i < 10000; i++);
        // 再次确认按键状态
        if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_15) == 1)
        {
            while (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_15) == 1);
            KeyNum = 4;
        }
    }
    // 检测PA8按键
    else if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_8) == 1) // 检测高电平
    {
        // 延时消抖
        for(i = 0; i < 10000; i++);
        // 再次确认按键状态
        if (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_8) == 1)
        {
            while (GPIO_ReadInputDataBit(GPIOA, GPIO_Pin_8) == 1);
            KeyNum = 5;
        }
    }

    return KeyNum; // 返回键码值
}
