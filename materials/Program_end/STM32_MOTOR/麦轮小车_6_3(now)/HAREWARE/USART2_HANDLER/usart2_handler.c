#include "usart2_handler.h"
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include "stm32f10x.h"
#include "sys.h"
#include "stdio.h"

// 接收缓冲区
static uint8_t rx_buffer[64] = {0};
static uint8_t rx_index = 0;
static volatile uint8_t data_ready = 0;
static volatile uint8_t chassis_data_ready = 0;

// 超声波数据存储
static UltrasonicData ultrasonic_data = {0, 0, 0, 0, 0, 0};
static volatile uint8_t ultrasonic_updated = 0;

// 底盘命令数据存储
static ChassisCmdData chassis_cmd = {{0}};
static volatile uint8_t chassis_cmd_updated = 0;

// 巡线模式使能标志（在此处定义）
volatile uint8_t line_follow_enabled = 0;

// 串口2初始化
void USART2_Init(void) {
    GPIO_InitTypeDef GPIO_InitStructure;
    USART_InitTypeDef USART_InitStructure;
    NVIC_InitTypeDef NVIC_InitStructure;
    
    // 使能时钟
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOA | RCC_APB2Periph_AFIO, ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART2, ENABLE);
    
    // 配置USART2 Tx (PA2) 作为推挽复用输出
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_2;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_PP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
    
    // 配置USART2 Rx (PA3) 作为浮空输入
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN_FLOATING;
    GPIO_Init(GPIOA, &GPIO_InitStructure);
    
    // USART参数配置
    USART_InitStructure.USART_BaudRate = 115200;
    USART_InitStructure.USART_WordLength = USART_WordLength_8b;
    USART_InitStructure.USART_StopBits = USART_StopBits_1;
    USART_InitStructure.USART_Parity = USART_Parity_No;
    USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;
    USART_Init(USART2, &USART_InitStructure);
    
    // 配置USART2接收中断
    NVIC_InitStructure.NVIC_IRQChannel = USART2_IRQn;
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0;
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&NVIC_InitStructure);
    
    // 使能接收中断
    USART_ITConfig(USART2, USART_IT_RXNE, ENABLE);
    
    // 使能USART2
    USART_Cmd(USART2, ENABLE);
}

// 串口2中断处理函数
void USART2_IRQHandler(void) {
    if(USART_GetITStatus(USART2, USART_IT_RXNE) != RESET) {
        uint8_t received_char = USART_ReceiveData(USART2);
        USART_ClearITPendingBit(USART2, USART_IT_RXNE);
        
        // 处理接收到的字符
        if (received_char == '\n' || received_char == '\r') {
            if(rx_index > 0) {
                rx_buffer[rx_index] = '\0'; // 添加字符串结束符
                
                // 根据首字符判断数据类型
                if (isdigit(rx_buffer[0])) {
                    // 数字开头：超声波数据或单数字命令
                    if(rx_index == 1 && (rx_buffer[0] == '8' || rx_buffer[0] == '9')) {
                        // 单数字命令：8或9
                        chassis_data_ready = 1;
                    } else {
                        // 多数字：超声波数据
                        data_ready = 1;
                    }
                } 
                else if (isalpha(rx_buffer[0])) {
                    // 字母开头：底盘命令
                    // 只有在巡线模式未启用时才处理底盘命令
                    if (!line_follow_enabled) {
                        chassis_data_ready = 1;
                    }
                }
            }
            rx_index = 0;
        } 
        // 缓冲区未满时存储有效字符
        else if (rx_index < sizeof(rx_buffer) - 1) {
            // 只接收有效字符：数字、逗号、字母
            if (isdigit(received_char) || received_char == ',' || isalpha(received_char)) {
                rx_buffer[rx_index++] = received_char;
            }
        }
    }
}

// 处理接收到的数据
void USART2_ProcessData(void) {
    // 处理超声波数据
    if (data_ready) {
        uint8_t *ptr = rx_buffer;
        uint16_t values[6] = {0};
        uint8_t value_index = 0;
        uint8_t parsing_number = 0;
        
        // 解析超声波数据 (格式: "20,20,20,20,20,20")
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
        
        // 更新数据
        ultrasonic_data.front_left = values[0];
        ultrasonic_data.front = values[1];
        ultrasonic_data.front_right = values[2];
        ultrasonic_data.rear = values[3];
        ultrasonic_data.rear_left = values[4];
        ultrasonic_data.rear_right = values[5];
        ultrasonic_updated = 1;
        
        data_ready = 0;
    }
    
    // 处理底盘命令
    if (chassis_data_ready) {
        // 复制命令字符串 (最大3个字符)
        strncpy(chassis_cmd.cmd_str, (char*)rx_buffer, sizeof(chassis_cmd.cmd_str) - 1);
        chassis_cmd.cmd_str[sizeof(chassis_cmd.cmd_str) - 1] = '\0'; // 确保结束符
        
        // 处理巡线模式命令
        if (strcmp(chassis_cmd.cmd_str, "8") == 0) {
            line_follow_enabled = 1; // 开启巡线模式
            // 清除其他控制命令，确保巡线模式独占控制
            Move_X = 0;
            Move_Y = 0;
            Move_Z = 0;
            LED_TURN();
        } else if (strcmp(chassis_cmd.cmd_str, "9") == 0) {
            line_follow_enabled = 0; // 关闭巡线模式
			Move_X = 0;
            Move_Y = 0;
            Move_Z = 0;
            LED_TURN();
        } else if (!line_follow_enabled) {
            // 只有在巡线模式未启用时才处理其他底盘命令
            chassis_cmd_updated = 1;
        }
        
        chassis_data_ready = 0;
    }
}

// 检查是否有新的超声波数据
uint8_t USART2_UltrasonicUpdated(void) {
    if(ultrasonic_updated) {
        ultrasonic_updated = 0;
        return 1;
    }
    return 0;
}

// 获取超声波数据
UltrasonicData USART2_GetUltrasonicData(void) {
    return ultrasonic_data;
}

// 检查是否有新的底盘命令
uint8_t USART2_ChassisCmdUpdated(void) {
    if(chassis_cmd_updated) {
        chassis_cmd_updated = 0;
        return 1;
    }
    return 0;
}

// 获取底盘命令
ChassisCmdData USART2_GetChassisCmd(void) {
    return chassis_cmd;
}
