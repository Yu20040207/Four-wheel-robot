#include "LineFollow.h"
#include "usart2_handler.h"
#include "string.h"
#include "stdio.h"


// 内部状态变量
static volatile uint8_t sensor_levels = 0;  // 存储8位电平值
static volatile uint8_t new_data_available = 0;  // 新数据可用标志

// 状态机状态
static volatile uint8_t rx_state = 0; // 0:等待帧头1, 1:等待帧头2, 2:等待指令, 3:等待数据长度, 4:等待数据, 5:等待校验和
static volatile uint8_t expected_length = 0;
static volatile uint8_t checksum_calculated = 0;
static volatile uint8_t rx_buffer[32];
static volatile uint8_t rx_index = 0;

// 内部函数声明
static void Send_AutoMode_Command(void);
static uint8_t Calculate_Checksum(uint8_t* data, uint8_t length);
static void USART2_SendByte(uint8_t data);
static void USART2_SendString(char *str);
static uint8_t reverse_bits(uint8_t n); // 重新添加位反转函数

// 初始化函数
void LineFollow_Init(void)
{
    // 初始化内部变量
    sensor_levels = 0;
    new_data_available = 0;
    rx_state = 0;
    expected_length = 0;
    checksum_calculated = 0;
    rx_index = 0;
    
    // 初始化运动控制变量
    Move_X = 0;
    Move_Y = 0;
    Move_Z = 0;
    
    // 等待一段时间确保USART3已初始化完成
    delay_ms(100);
    
    // 发送配置指令，设置传感器为自动发送电平值模式
    Send_AutoMode_Command();
    
    // 使能USART3接收中断
    USART_ITConfig(USART3, USART_IT_RXNE, ENABLE);
    
    USART2_SendString("Line Follower Sensor Initialized\r\n");
    USART2_SendString("Mode: Auto Level (1)\r\n");
}

// 处理函数 - 在主循环中调用
void LineFollow_Process(void)
{
    char buffer[50];
    int i;
    
    // 检查是否启用巡线模式
    if (!line_follow_enabled) {
        Move_X = 0;
        Move_Y = 0;
        Move_Z = 0;
        return;
    }
    
    // 检查是否有新的传感器数据
    if (new_data_available) {
        // 反转传感器数据的位顺序
        uint8_t reversed_sensors = reverse_bits(sensor_levels);
        
        // 发送传感器数据到USART2进行调试
        USART2_SendString("Sensor Levels: ");
        for(i = 7; i >= 0; i--) {
            // 从最高位到最低位显示，对应从左到右的传感器
            if(reversed_sensors & (1 << i)) {
                USART2_SendString("1 ");
            } else {
                USART2_SendString("0 ");
            }
        }
        sprintf(buffer, "(0x%02X -> 0x%02X)\r\n", sensor_levels, reversed_sensors);
        USART2_SendString(buffer);
        
        // 根据反转后的传感器数据执行巡线逻辑
        // 情况1: 所有传感器都检测到黑线或都没有检测到 - 停止
        if (reversed_sensors == 0xFF || reversed_sensors == 0x00) {
            Move_X = 0;
            Move_Y = 0;
            Move_Z = 0;
            USART2_SendString("Action: Stop\r\n");
        }
        // 情况2: 中间传感器检测到黑线 - 直行
        else if ((reversed_sensors & 0x18) == 0x18) { // 位3和位4
            Move_X = 0.5;
            Move_Y = 0;
            Move_Z = 0;
            USART2_SendString("Action: Forward\r\n");
        }
        // 情况3: 左侧传感器检测到黑线 - 左转
        else if (reversed_sensors & 0xE0) { // 位5,6,7 (左侧)
            Move_X = 0;
            Move_Y = 0.4;
            Move_Z = 0;
            USART2_SendString("Action: Turn Left\r\n");
        }
        // 情况4: 右侧传感器检测到黑线 - 右转
        else if (reversed_sensors & 0x07) { // 位0,1,2 (右侧)
            Move_X = 0;
            Move_Y = -0.4;
            Move_Z = 0;
            USART2_SendString("Action: Turn Right\r\n");
        }
        // 情况5: 只有最左侧传感器检测到 - 左平移
        else if (reversed_sensors == 0x80) { // 仅位7 (最左侧)
            Move_X = 0;
            Move_Y = 0;
            Move_Z = 2.5;
            USART2_SendString("Action: Strafe Left\r\n");
        }
        // 情况6: 只有最右侧传感器检测到 - 右平移
        else if (reversed_sensors == 0x01) { // 仅位0 (最右侧)
            Move_X = 0;
            Move_Y = 0;
            Move_Z = -2.5;
            USART2_SendString("Action: Strafe Right\r\n");
        }
        // 默认情况: 停止
        else {
            Move_X = 0;
            Move_Y = 0;
            Move_Z = 0;
            USART2_SendString("Action: Unknown - Stop\r\n");
        }
        
        // 重置标志
        new_data_available = 0;
    }
}

// 发送自动模式配置指令
static void Send_AutoMode_Command(void)
{
    uint8_t config_frame[5];
    char buffer[20];
    uint8_t i;
    
    // 构建配置指令帧: 0x55, 0xAA, 1, 0, ~(1 + 0)
    config_frame[0] = LINEFOLLOW_HEADER1;
    config_frame[1] = LINEFOLLOW_HEADER2;
    config_frame[2] = 1; // 自动发送电平值模式
    config_frame[3] = 0; // 数据长度为0
    config_frame[4] = ~(1 + 0); // 校验和
    
    // 发送配置指令
    USART2_SendString("Sending auto mode command: ");
    for(i = 0; i < 5; i++)
    {
        sprintf(buffer, "%02X ", config_frame[i]);
        USART2_SendString(buffer);
        USART_SendData(USART3, config_frame[i]);
        while(USART_GetFlagStatus(USART3, USART_FLAG_TXE) == RESET);
    }
    USART2_SendString("\r\n");
}

// 计算校验和
static uint8_t Calculate_Checksum(uint8_t* data, uint8_t length)
{
    uint8_t i;
    uint8_t sum = 0;
    
    for(i = 0; i < length; i++)
    {
        sum += data[i];
    }
    
    return ~sum;
}

// USART2发送一个字节
static void USART2_SendByte(uint8_t data)
{
    USART_SendData(USART2, data);
    while(USART_GetFlagStatus(USART2, USART_FLAG_TXE) == RESET);
}

// USART2发送字符串
static void USART2_SendString(char *str)
{
    while(*str)
    {
        USART2_SendByte(*str++);
    }
}

// 位反转函数
static uint8_t reverse_bits(uint8_t n) {
    uint8_t rev = 0;
    int i;
    for (i = 0; i < 8; i++) {
        rev <<= 1;
        rev |= (n & 1);
        n >>= 1;
    }
    return rev;
}

// USART3中断服务程序
void USART3_IRQHandler(void)
{
    uint8_t received_byte;
    
    // 处理接收中断
    if(USART_GetITStatus(USART3, USART_IT_RXNE) != RESET)
    {
        received_byte = USART_ReceiveData(USART3);
        
        // 直接处理接收到的字节
        sensor_levels = received_byte;
        new_data_available = 1;
        
        // 清除中断标志
        USART_ClearITPendingBit(USART3, USART_IT_RXNE);
    }
}
