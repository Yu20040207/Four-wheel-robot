#ifndef __KEY_H
#define __KEY_H

#include "sys.h"

#define KEY 	PBin(15)

void Key_Init(void);
u8 click(void);
u8 click_N_Double (u8 time);

#endif
