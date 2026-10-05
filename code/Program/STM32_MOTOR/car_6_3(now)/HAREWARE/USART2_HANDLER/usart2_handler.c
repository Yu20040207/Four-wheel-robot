#include "usart2_handler.h"
#include "control.h"

#include "voice_control.h"

#include "avoidance.h"

#include <string.h>

#include <stdlib.h>

#include <ctype.h>

#include "stm32f10x.h"

#include "sys.h"

#include "stdio.h"
#include "LineFollow.h"



// 行接收缓冲（ISR 逐字节拼装）

static uint8_t rx_buffer[64] = {0};

static uint8_t rx_index = 0;

/* Invalid raw text must not be filtered into an authorization. */
static uint8_t rx_invalid = 0;
static volatile uint8_t start_ready = 0;



// 超声波与底盘命令各自独立缓冲，避免互相覆盖导致丢指令

static uint8_t ultrasonic_line[64] = {0};

static uint8_t chassis_line[12] = {0};

static volatile uint8_t data_ready = 0;

static volatile uint8_t chassis_data_ready = 0;



static UltrasonicData ultrasonic_data = {0, 0, 0, 0, 0, 0};

static volatile uint8_t ultrasonic_updated = 0;



static ChassisCmdData chassis_cmd = {{0}};

static volatile uint8_t chassis_cmd_updated = 0;



volatile uint8_t line_follow_enabled = 0;



static void copy_line_to_buffer(uint8_t *dest, size_t dest_size)

{

    size_t copy_len = rx_index;



    if (copy_len >= dest_size) {

        copy_len = dest_size - 1;

    }

    memcpy(dest, rx_buffer, copy_len);

    dest[copy_len] = '\0';

}



void USART2_Init(void) {

    GPIO_InitTypeDef GPIO_InitStructure;

    USART_InitTypeDef USART_InitStructure;

    NVIC_InitTypeDef NVIC_InitStructure;

    

    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_AFIO, ENABLE);

    RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART2, ENABLE);

    

    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_2;

    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;

    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;

    GPIO_Init(GPIOA, &GPIO_InitStructure);

    

    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3;

    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;

    GPIO_Init(GPIOA, &GPIO_InitStructure);

    

    USART_InitStructure.USART_BaudRate = 115200;

    USART_InitStructure.USART_WordLength = USART_WordLength_8b;

    USART_InitStructure.USART_StopBits = USART_StopBits_1;

    USART_InitStructure.USART_Parity = USART_Parity_No;

    USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;

    USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;

    USART_Init(USART2, &USART_InitStructure);

    

    NVIC_InitStructure.NVIC_IRQChannel = USART2_IRQn;

    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0;

    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;

    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;

    NVIC_Init(&NVIC_InitStructure);

    

    USART_ITConfig(USART2, USART_IT_RXNE, ENABLE);

    USART_Cmd(USART2, ENABLE);

}



void USART2_IRQHandler(void) {

    if(USART_GetITStatus(USART2, USART_IT_RXNE) != RESET) {

        uint8_t received_char = USART_ReceiveData(USART2);

        USART_ClearITPendingBit(USART2, USART_IT_RXNE);

        

        if (received_char == '\n' || received_char == '\r') {

            if(rx_index > 0) {

                rx_buffer[rx_index] = '\0';

                

                /* STOP bypasses the mode gates and the single command slot. */
                if (strcmp((char *)rx_buffer, "S") == 0 ||
                    strcmp((char *)rx_buffer, "stop") == 0 ||
                    strcmp((char *)rx_buffer, "7") == 0 ||
                    strcmp((char *)rx_buffer, "9") == 0 ||
                    strcmp((char *)rx_buffer, "B") == 0) {
                    Chassis_RequestStop();
                    chassis_data_ready = 0;
                    chassis_cmd_updated = 0;
                    start_ready = 0;
                } else if (!rx_invalid && strcmp((char *)rx_buffer, "START") == 0) {
                    /* A request arriving before STOP cleanup is discarded. */
                    if (Chassis_IsStopped() && !Chassis_StopPending()) {
                        start_ready = 1;
                    }
                } else if (!Chassis_IsStopped() && isdigit(rx_buffer[0])) {

                    if(rx_index == 1 && (rx_buffer[0] == '6' || rx_buffer[0] == '7' ||

                                         rx_buffer[0] == '8' || rx_buffer[0] == '9')) {

                        copy_line_to_buffer(chassis_line, sizeof(chassis_line));

                        chassis_data_ready = 1;

                    } else {

                        copy_line_to_buffer(ultrasonic_line, sizeof(ultrasonic_line));

                        data_ready = 1;

                    }

                } 

                else if (!Chassis_IsStopped() && isalpha(rx_buffer[0])) {

                    if (!line_follow_enabled) {

                        copy_line_to_buffer(chassis_line, sizeof(chassis_line));

                        chassis_data_ready = 1;

                    }

                }

            }

            rx_index = 0;
            rx_invalid = 0;

        } 

        else if (rx_index < sizeof(rx_buffer) - 1) {

            if (isdigit(received_char) || received_char == ',' || isalpha(received_char)) {

                rx_buffer[rx_index++] = received_char;

            } else {
                rx_invalid = 1;
            }

        } else {
            rx_invalid = 1;
        }

    }

}



void USART2_ProcessData(void) {
    uint32_t primask;
    Chassis_ServiceStop();
    primask = __get_PRIMASK();
    __disable_irq();

    if (start_ready) {
        start_ready = 0;
        Chassis_Start();
        __set_PRIMASK(primask);
        return;
    }
    if (Chassis_IsStopped()) {
        __set_PRIMASK(primask);
        return;
    }

    if (data_ready) {

        uint8_t *ptr = ultrasonic_line;

        uint16_t values[6] = {0};

        uint8_t value_index = 0;

        uint8_t parsing_number = 0;

        

        while (*ptr && value_index < 6) {

            if (*ptr >= '0' && *ptr <= '9') {

                values[value_index] = values[value_index] * 10 + (*ptr - '0');

                parsing_number = 1;

            } else if (*ptr == ',' && parsing_number) {

                value_index++;

                parsing_number = 0;

            }

            ptr++;

        }

        

        ultrasonic_data.front_left = values[0];

        ultrasonic_data.front = values[1];

        ultrasonic_data.front_right = values[2];

        ultrasonic_data.rear = values[3];

        ultrasonic_data.rear_left = values[4];

        ultrasonic_data.rear_right = values[5];

        ultrasonic_updated = 1;

        

        data_ready = 0;

    }

    

    if (chassis_data_ready) {

        strncpy(chassis_cmd.cmd_str, (char*)chassis_line, sizeof(chassis_cmd.cmd_str) - 1);

        chassis_cmd.cmd_str[sizeof(chassis_cmd.cmd_str) - 1] = '\0';

        

        if (strcmp(chassis_cmd.cmd_str, "8") == 0) {

            LineFollow_ResetController();
            line_follow_enabled = 1;

            Move_X = 0;

            Move_Y = 0;

            Move_Z = 0;

            LED_TURN();

        } else if (strcmp(chassis_cmd.cmd_str, "9") == 0) {

            line_follow_enabled = 0;
            LineFollow_ResetController();

			Move_X = 0;

            Move_Y = 0;

            Move_Z = 0;

            LED_TURN();

        } else if (strcmp(chassis_cmd.cmd_str, "6") == 0) {

            Avoidance_SetAutonomousMode(1);

            Voice_Control_Disable();

            Move_X = 0;

            Move_Y = 0;

            Move_Z = 0;

        } else if (strcmp(chassis_cmd.cmd_str, "7") == 0) {

            Avoidance_SetAutonomousMode(0);

        } else if (strcmp(chassis_cmd.cmd_str, "A") == 0) {

            line_follow_enabled = 0;

            Avoidance_SetAutonomousMode(0);

            Voice_Control_Enable();

            Move_X = 0;

            Move_Y = 0;

            Move_Z = 0;

        } else if (strcmp(chassis_cmd.cmd_str, "B") == 0) {

            Voice_Control_Disable();

        } else if (!line_follow_enabled) {

            chassis_cmd_updated = 1;

        }

        

        chassis_data_ready = 0;

    }
    __set_PRIMASK(primask);

}



uint8_t USART2_UltrasonicUpdated(void) {

    if(ultrasonic_updated) {

        ultrasonic_updated = 0;

        return 1;

    }

    return 0;

}



UltrasonicData USART2_GetUltrasonicData(void) {

    return ultrasonic_data;

}



uint8_t USART2_ChassisCmdUpdated(void) {

    if(chassis_cmd_updated) {

        chassis_cmd_updated = 0;

        return 1;

    }

    return 0;

}



ChassisCmdData USART2_GetChassisCmd(void) {

    return chassis_cmd;

}

/* Discard every pre-stop command, mode request, update and partial line. */
void USART2_DiscardPendingMotion(void)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    chassis_data_ready = 0;
    chassis_cmd_updated = 0;
    data_ready = 0;
    ultrasonic_updated = 0;
    start_ready = 0;
    rx_index = 0;
    rx_invalid = 0;
    memset(rx_buffer, 0, sizeof(rx_buffer));
    memset(chassis_line, 0, sizeof(chassis_line));
    memset(&chassis_cmd, 0, sizeof(chassis_cmd));
    __set_PRIMASK(primask);
}
