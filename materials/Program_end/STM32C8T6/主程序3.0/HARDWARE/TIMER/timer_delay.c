#include "bsp.h"

__IO u32 timer_delay_count = 0;

static void config_timer_delay() {
    NVIC_InitTypeDef NVIC_InitStructure;
    NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);

    NVIC_InitStructure.NVIC_IRQChannel = TIM_DELAY_IRQ;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 3;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 2;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
}

void TIM_Delay_Configuration() {
    TIM_TimeBaseInitTypeDef TIM_TimeBaseInitstructure;

    TIM_DELAY_CLOCK_CMD(TIM_DELAY_CLK, ENABLE);

    TIM_TimeBaseInitstructure.TIM_Period = 1000;
    TIM_TimeBaseInitstructure.TIM_Prescaler = 71;
    TIM_TimeBaseInitstructure.TIM_ClockDivision = 0;
    TIM_TimeBaseInit(TIM_DELAY, &TIM_TimeBaseInitstructure);

    TIM_ClearFlag(TIM_DELAY, TIM_FLAG_Update);
    TIM_ITConfig(TIM_DELAY, TIM_IT_Update, ENABLE);

    config_timer_delay();
}

void TIM_DELAY_IRQHandler() {
    if (TIM_GetITStatus(TIM_DELAY, TIM_IT_Update) != RESET) {
        timer_delay_count--;
        TIM_ClearITPendingBit(TIM_DELAY, TIM_IT_Update);
    }
}

void timer_delay_ms(u16 t) {
    timer_delay_count = t;
    TIM_Cmd(TIM_DELAY, ENABLE);
    while (timer_delay_count != 0);
    TIM_Cmd(TIM_DELAY, DISABLE);
}


