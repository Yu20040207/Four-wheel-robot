#ifndef R1_HOST_STM32F10X_H
#define R1_HOST_STM32F10X_H
#include <stdint.h>
#include <stddef.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef int FunctionalState;
typedef int ITStatus;
typedef int FlagStatus;
#define ENABLE 1
#define DISABLE 0
#define RESET 0
#define SET 1
typedef struct { uint32_t CCR1, CCR2, CCR3, CCR4; unsigned pending, pwm_enabled; } TIM_TypeDef;
typedef struct { uint16_t data; unsigned pending; uint32_t DR, SR; } USART_TypeDef;
typedef struct { unsigned index; } GPIO_TypeDef;
extern TIM_TypeDef host_tim6, host_tim7, host_tim8;
extern USART_TypeDef host_usart1, host_usart2, host_usart3;
extern GPIO_TypeDef host_gpioa, host_gpiob, host_gpioc, host_gpiod;
#define TIM6 (&host_tim6)
#define TIM7 (&host_tim7)
#define TIM8 (&host_tim8)
#define USART1 (&host_usart1)
#define USART2 (&host_usart2)
#define USART3 (&host_usart3)
#define GPIOA (&host_gpioa)
#define GPIOB (&host_gpiob)
#define GPIOC (&host_gpioc)
#define GPIOD (&host_gpiod)
typedef struct { uint32_t GPIO_Pin, GPIO_Mode, GPIO_Speed; } GPIO_InitTypeDef;
typedef struct { uint32_t USART_BaudRate, USART_WordLength, USART_StopBits, USART_Parity, USART_HardwareFlowControl, USART_Mode; } USART_InitTypeDef;
typedef struct { uint32_t NVIC_IRQChannel, NVIC_IRQChannelPreemptionPriority, NVIC_IRQChannelSubPriority, NVIC_IRQChannelCmd; } NVIC_InitTypeDef;
typedef struct { uint32_t TIM_Period, TIM_Prescaler, TIM_ClockDivision, TIM_CounterMode; } TIM_TimeBaseInitTypeDef;
#define GPIO_Pin_2 (1u << 2)
#define GPIO_Pin_3 (1u << 3)
#define GPIO_Pin_4 (1u << 4)
#define GPIO_Pin_5 (1u << 5)
#define GPIO_Pin_8 (1u << 8)
#define GPIO_Pin_9 (1u << 9)
#define GPIO_Pin_10 (1u << 10)
#define GPIO_Pin_11 (1u << 11)
#define GPIO_Pin_12 (1u << 12)
#define GPIO_Pin_13 (1u << 13)
#define GPIO_Pin_14 (1u << 14)
#define GPIO_Mode_Out_PP 0
#define GPIO_Mode_AF_PP 1
#define GPIO_Mode_IN_FLOATING 2
#define GPIO_Speed_50MHz 50
#define GPIO_PartialRemap_USART3 1
#define RCC_APB2Periph_GPIOA 1
#define RCC_APB2Periph_GPIOB 2
#define RCC_APB2Periph_GPIOC 4
#define RCC_APB2Periph_GPIOD 8
#define RCC_APB2Periph_AFIO 16
#define RCC_APB2Periph_USART1 32
#define RCC_APB1Periph_USART2 1
#define RCC_APB1Periph_USART3 2
#define RCC_APB1Periph_TIM7 4
#define USART_WordLength_8b 8
#define USART_StopBits_1 1
#define USART_Parity_No 0
#define USART_HardwareFlowControl_None 0
#define USART_Mode_Rx 1
#define USART_Mode_Tx 2
#define USART_IT_RXNE 1
#define USART_FLAG_TXE 2
#define USART1_IRQn 1
#define USART2_IRQn 2
#define USART3_IRQn 3
#define TIM7_IRQn 7
#define TIM_IT_Update 1
#define TIM_CounterMode_Up 0
void RCC_APB1PeriphClockCmd(uint32_t, FunctionalState);
void RCC_APB2PeriphClockCmd(uint32_t, FunctionalState);
void GPIO_Init(GPIO_TypeDef *, GPIO_InitTypeDef *);
void GPIO_ResetBits(GPIO_TypeDef *, uint16_t);
void GPIO_PinRemapConfig(uint32_t, FunctionalState);
void USART_Init(USART_TypeDef *, USART_InitTypeDef *);
void USART_ITConfig(USART_TypeDef *, uint16_t, FunctionalState);
void USART_Cmd(USART_TypeDef *, FunctionalState);
ITStatus USART_GetITStatus(USART_TypeDef *, uint16_t);
uint16_t USART_ReceiveData(USART_TypeDef *);
void USART_ClearITPendingBit(USART_TypeDef *, uint16_t);
FlagStatus USART_GetFlagStatus(USART_TypeDef *, uint16_t);
void USART_SendData(USART_TypeDef *, uint16_t);
void NVIC_Init(NVIC_InitTypeDef *);
void NVIC_EnableIRQ(int);
void TIM_TimeBaseInit(TIM_TypeDef *, TIM_TimeBaseInitTypeDef *);
void TIM_ITConfig(TIM_TypeDef *, uint16_t, FunctionalState);
void TIM_Cmd(TIM_TypeDef *, FunctionalState);
ITStatus TIM_GetITStatus(TIM_TypeDef *, uint16_t);
void TIM_ClearITPendingBit(TIM_TypeDef *, uint16_t);
void TIM_CtrlPWMOutputs(TIM_TypeDef *, FunctionalState);
uint32_t __get_PRIMASK(void);
void __disable_irq(void);
void __enable_irq(void);
void __set_PRIMASK(uint32_t);
void __DMB(void);
#endif
