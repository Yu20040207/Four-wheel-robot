#ifndef __LED_H
#define __LED_H

#include "sys.h"

#define LED	PBout(14)

void LED_Init(void);
void LED_Flash(u8 time);
void LED_Switch(u8 state);
void LED_TURN(void);




#endif
