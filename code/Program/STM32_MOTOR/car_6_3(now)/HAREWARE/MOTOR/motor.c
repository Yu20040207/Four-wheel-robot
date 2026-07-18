#include "motor.h"

void Motor_Init(void)
{    
    GPIO_InitTypeDef GPIO_InitStructure;
    
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB | RCC_APB2Periph_GPIOC | RCC_APB2Periph_GPIOD, ENABLE);
    
    // ???????��???????????????????????0
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_Out_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    
    // GPIOB
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_8 | GPIO_Pin_9;
    GPIO_Init(GPIOB, &GPIO_InitStructure);
    GPIO_ResetBits(GPIOB, GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_8 | GPIO_Pin_9);
    
    // GPIOC
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_2 | GPIO_Pin_12 | GPIO_Pin_13 | GPIO_Pin_14;
    GPIO_Init(GPIOC, &GPIO_InitStructure);
    GPIO_ResetBits(GPIOC, GPIO_Pin_2 | GPIO_Pin_12 | GPIO_Pin_13 | GPIO_Pin_14);
    
    // GPIOD
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_2;
    GPIO_Init(GPIOD, &GPIO_InitStructure);
    GPIO_ResetBits(GPIOD, GPIO_Pin_2);
    
    // ??????????????????
    STBY = 0;
}

void Motor_StopOutputs(void)
{
    PWMA = 0;
    PWMB = 0;
    PWMC = 0;
    PWMD = 0;
    AIN1 = 0;
    AIN2 = 0;
    BIN1 = 0;
    BIN2 = 0;
    CIN1 = 0;
    CIN2 = 0;
    DIN1 = 0;
    DIN2 = 0;
}

void Motor_Safe_Start(void)
{
    // ˫�ذ�ȫ��֤
    MOTOR_EMERGENCY_STOP();
    
    // �ӳ���Դ�ȶ��ȴ�ʱ��
    delay_ms(200);  // ������200ms
    
    // ����������
    STBY = 1;
    
    // �ٴ�ȷ��PWMΪ0
    TIM8->CCR1 = 0;
    TIM8->CCR2 = 0;
    TIM8->CCR3 = 0;
    TIM8->CCR4 = 0;
}
