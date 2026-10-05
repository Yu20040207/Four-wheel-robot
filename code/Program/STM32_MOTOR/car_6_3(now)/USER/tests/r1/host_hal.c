#include "host_hal.h"
#include "LineFollow.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
TIM_TypeDef host_tim6, host_tim7, host_tim8;
USART_TypeDef host_usart1, host_usart2, host_usart3;
GPIO_TypeDef host_gpioa = {0}, host_gpiob = {1}, host_gpioc = {2}, host_gpiod = {3};
uint32_t host_gpio_bits[4][16];
u32 voltage = 2400;
u8 Car_Mode, Mode, Flag_Direction, PID_Send, Flag_Left, Flag_Right;
u8 Receive_Data[12], Lidar_Success_Receive_flag;
float Axle_spacing = 1, Wheel_spacing = 1, Velocity_KP = 100, Velocity_KI = 10;
float Along_Distance_KP, Along_Distance_KI, Along_Distance_KD;
float Distance_KP, Distance_KI, Distance_KD;
float Follow_KP, Follow_KI, Follow_KD, RC_Velocity;
volatile uint32_t system_tick;
HostImu imu;
static uint32_t primask;
static char deferred_text[512];
static unsigned deferred_unmasks;
static unsigned deliveries, enable_while_stopped, key_reads;
static u8 next_key;
static int stop_on_encoder, stop_on_pwm;

void host_reset_hal(void) {
    memset(&host_tim6, 0, sizeof host_tim6);
    memset(&host_tim7, 0, sizeof host_tim7);
    memset(&host_tim8, 0, sizeof host_tim8);
    memset(&host_usart1, 0, sizeof host_usart1);
    memset(&host_usart2, 0, sizeof host_usart2);
    memset(&host_usart3, 0, sizeof host_usart3);
    host_usart1.SR = host_usart2.SR = host_usart3.SR = 0x40;
    memset(host_gpio_bits, 0, sizeof host_gpio_bits);
    memset(Receive_Data, 0, sizeof Receive_Data);
    primask = deliveries = enable_while_stopped = key_reads = 0;
    next_key = 0; deferred_text[0] = 0; deferred_unmasks = 0;
    stop_on_encoder = stop_on_pwm = 0;
    Mode = Normal_Mode; Car_Mode = ROS_Mode;
    Flag_Direction = PID_Send = Flag_Left = Flag_Right = 0;
    voltage = 2400;
}
void host_feed_uart(unsigned uart, const uint8_t *bytes, size_t count) {
    USART_TypeDef *port = uart == 1 ? USART1 : uart == 2 ? USART2 : USART3;
    size_t i;
    if (primask) { fprintf(stderr, "host_feed_uart called while IRQ masked\n"); abort(); }
    for (i = 0; i < count; ++i) {
        port->data = bytes[i]; port->pending = 1;
        if (uart == 1) USART1_IRQHandler();
        else if (uart == 2) USART2_IRQHandler();
        else USART3_IRQHandler();
    }
}
void host_feed_text(const char *text) { host_feed_uart(2, (const uint8_t *)text, strlen(text)); }
void host_tick(void) { TIM6->pending = 1; TIM6_IRQHandler(); }
void host_avoidance_tick(void) { TIM7->pending = 1; Avoidance_TIM7_IRQHandler(); }
void host_schedule_text_after_unmasks(const char *text, unsigned count) {
    if (strlen(text) >= sizeof deferred_text || count == 0) abort();
    strcpy(deferred_text, text);
    deferred_unmasks = count;
}
void host_schedule_text_on_unmask(const char *text) { host_schedule_text_after_unmasks(text, 1); }
unsigned host_scheduled_deliveries(void) { return deliveries; }
void host_schedule_stop_on_encoder(void) { stop_on_encoder = 1; }
void host_schedule_stop_on_pwm(void) { stop_on_pwm = 1; }
void host_set_key(u8 key) { next_key = key; }
unsigned host_key_reads(void) { return key_reads; }
unsigned host_enable_while_stopped(void) { return enable_while_stopped; }
uint32_t __get_PRIMASK(void) { return primask; }
void __disable_irq(void) { primask = 1; }
void __set_PRIMASK(uint32_t value) {
    uint32_t was_masked = primask;
    primask = value ? 1 : 0;
    if (was_masked && !primask && deferred_text[0] && --deferred_unmasks == 0) {
        char ready[sizeof deferred_text];
        strcpy(ready, deferred_text); deferred_text[0] = 0; ++deliveries;
        host_feed_text(ready);
    }
}
void __enable_irq(void) { __set_PRIMASK(0); }
void __DMB(void) {}
ITStatus USART_GetITStatus(USART_TypeDef *p, uint16_t ignored) { (void)ignored; return p->pending ? SET : RESET; }
uint16_t USART_ReceiveData(USART_TypeDef *p) { return p->data; }
void USART_ClearITPendingBit(USART_TypeDef *p, uint16_t ignored) { (void)ignored; p->pending = 0; }
FlagStatus USART_GetFlagStatus(USART_TypeDef *p, uint16_t ignored) { (void)p; (void)ignored; return SET; }
void USART_SendData(USART_TypeDef *p, uint16_t value) { (void)p; (void)value; }
ITStatus TIM_GetITStatus(TIM_TypeDef *p, uint16_t ignored) { (void)ignored; return p->pending ? SET : RESET; }
void TIM_ClearITPendingBit(TIM_TypeDef *p, uint16_t ignored) { (void)ignored; p->pending = 0; }
void TIM_CtrlPWMOutputs(TIM_TypeDef *p, FunctionalState enabled) {
    if (stop_on_pwm) {
        stop_on_pwm = 0;
        if (primask) host_schedule_text_on_unmask("S\r\n"); else host_feed_text("S\r\n");
    }
    if (enabled && Chassis_IsStopped()) ++enable_while_stopped;
    p->pwm_enabled = enabled;
}
int Read_Encoder(u8 timer) {
    (void)timer;
    if (stop_on_encoder) {
        stop_on_encoder = 0;
        if (primask) host_schedule_text_on_unmask("S\r\n"); else host_feed_text("S\r\n");
    }
    return 0;
}
u8 click_N_Double(u8 ignored) { u8 value = next_key; (void)ignored; ++key_reads; next_key = 0; return value; }
void GPIO_ResetBits(GPIO_TypeDef *p, uint16_t mask) { unsigned n; for (n = 0; n < 16; ++n) if (mask & (1u << n)) host_gpio_bits[p->index][n] = 0; }
void delay_ms(u32 ignored) { (void)ignored; }
void delay_us(u32 ignored) { (void)ignored; }
void LED_TURN(void) {}
#define NOOP2(name, t1, t2) void name(t1 a, t2 b) { (void)a; (void)b; }
#define NOOP3(name, t1, t2, t3) void name(t1 a, t2 b, t3 c) { (void)a; (void)b; (void)c; }
NOOP2(RCC_APB1PeriphClockCmd, uint32_t, FunctionalState)
NOOP2(RCC_APB2PeriphClockCmd, uint32_t, FunctionalState)
NOOP2(GPIO_Init, GPIO_TypeDef *, GPIO_InitTypeDef *)
NOOP2(GPIO_PinRemapConfig, uint32_t, FunctionalState)
NOOP2(USART_Init, USART_TypeDef *, USART_InitTypeDef *)
NOOP3(USART_ITConfig, USART_TypeDef *, uint16_t, FunctionalState)
NOOP2(USART_Cmd, USART_TypeDef *, FunctionalState)
void NVIC_Init(NVIC_InitTypeDef *ignored) { (void)ignored; }
void NVIC_EnableIRQ(int ignored) { (void)ignored; }
NOOP2(TIM_TimeBaseInit, TIM_TypeDef *, TIM_TimeBaseInitTypeDef *)
NOOP3(TIM_ITConfig, TIM_TypeDef *, uint16_t, FunctionalState)
NOOP2(TIM_Cmd, TIM_TypeDef *, FunctionalState)
