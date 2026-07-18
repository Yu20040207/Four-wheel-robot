#include "stm32f10x_it.h" 
#include "serial_dispose.h"  // 包含串口处理头文件


// stm32f10x_it.c 中添加以下内容
extern volatile uint32_t sys_tick;
// 定义系统滴答计时器变量
volatile uint32_t sys_tick = 0;

void SysTick_Handler(void)
{
    sys_tick++;
}
 
void NMI_Handler(void)
{
}
 
void HardFault_Handler(void)
{
  /* Go to infinite loop when Hard Fault exception occurs */
  while (1)
  {
  }
}
 
void MemManage_Handler(void)
{
  /* Go to infinite loop when Memory Manage exception occurs */
  while (1)
  {
  }
}

 
void BusFault_Handler(void)
{
  /* Go to infinite loop when Bus Fault exception occurs */
  while (1)
  {
  }
}
 
void UsageFault_Handler(void)
{
  /* Go to infinite loop when Usage Fault exception occurs */
  while (1)
  {
  }
}
 
void SVC_Handler(void)
{
}
 
void DebugMon_Handler(void)
{
}
 
void PendSV_Handler(void)
{
}
