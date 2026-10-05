#ifndef R1_HOST_HAL_H
#define R1_HOST_HAL_H
#include "sys.h"
/* Also permits compiling the peripheral stubs against the pre-R1 headers. */
void Chassis_RequestStop(void);
void Chassis_ServiceStop(void);
uint8_t Chassis_IsStopped(void);
uint8_t Chassis_StopPending(void);
uint8_t Chassis_Start(void);
void host_reset_hal(void);
void host_feed_uart(unsigned uart, const uint8_t *bytes, size_t count);
void host_feed_text(const char *text);
void host_tick(void);
void host_schedule_text_on_unmask(const char *text);
void host_schedule_text_after_unmasks(const char *text, unsigned count);
unsigned host_scheduled_deliveries(void);
void host_schedule_stop_on_encoder(void);
void host_schedule_stop_on_pwm(void);
void host_avoidance_tick(void);
void host_set_key(u8 key);
unsigned host_key_reads(void);
unsigned host_enable_while_stopped(void);
void host_seed_pi(float pwm, float bias);
int host_pi_is_zero(void);
void host_set_fault(unsigned value);
unsigned host_get_fault(void);
int host_lf_is_clean(void);
int host_uart2_is_clean(void);
void USART2_IRQHandler(void);
int TIM6_IRQHandler(void);
#endif
