#ifndef __RANGING_H
#define __RANGING_H

#include "stm32f10x.h"

// ³¬Éù²¨½Ó¿Úº¯Êý
void Ultrasonic_Init(void);
void Ultrasonic_SetEnable(uint8_t status);
void Ultrasonic_Process(void);
uint8_t Ultrasonic_Measure_NonBlocking(void);
uint8_t Ultrasonic_IsMeasuring(void);
void USART3_SendDistance(void);

#endif /* __RANGING_H */
