#include "LineFollow.h"
#include "usart2_handler.h"
#include "string.h"
#include "stdio.h"


// �ڲ�״̬����
static volatile uint8_t sensor_levels = 0;  // �洢8λ��ƽֵ
static volatile uint8_t new_data_available = 0;  // �����ݿ��ñ�־

// ״̬��״̬
static volatile uint8_t rx_state = 0; // 0:�ȴ�֡ͷ1, 1:�ȴ�֡ͷ2, 2:�ȴ�ָ��, 3:�ȴ����ݳ���, 4:�ȴ�����, 5:�ȴ�У���
static volatile uint8_t expected_length = 0;
static volatile uint8_t checksum_calculated = 0;
static volatile uint8_t rx_buffer[32];
static volatile uint8_t rx_index = 0;

// �ڲ���������
static void Send_AutoMode_Command(void);
static uint8_t Calculate_Checksum(uint8_t* data, uint8_t length);
static void USART2_SendByte(uint8_t data);
static void USART2_SendString(char *str);
static uint8_t reverse_bits(uint8_t n); // ��������λ��ת����

// ��ʼ������
void LineFollow_Init(void)
{
    // ��ʼ���ڲ�����
    sensor_levels = 0;
    new_data_available = 0;
    rx_state = 0;
    expected_length = 0;
    checksum_calculated = 0;
    rx_index = 0;
    
    // ��ʼ���˶����Ʊ���
    Move_X = 0;
    Move_Y = 0;
    Move_Z = 0;
    
    // �ȴ�һ��ʱ��ȷ��USART3�ѳ�ʼ�����
    delay_ms(100);
    
    // ��������ָ����ô�����Ϊ�Զ����͵�ƽֵģʽ
    Send_AutoMode_Command();
    
    // ʹ��USART3�����ж�
    USART_ITConfig(USART3, USART_IT_RXNE, ENABLE);
    
    USART2_SendString("Line Follower Sensor Initialized\r\n");
    USART2_SendString("Mode: Auto Level (1)\r\n");
}

// �������� - ����ѭ���е���
void LineFollow_Process(void)
{
    char buffer[50];
    int i;
    
    // ����Ƿ�����Ѳ��ģʽ
    if (!line_follow_enabled) {
        Move_X = 0;
        Move_Y = 0;
        Move_Z = 0;
        return;
    }
    
    // ����Ƿ����µĴ���������
    if (new_data_available) {
        // ��ת���������ݵ�λ˳��
        uint8_t reversed_sensors = reverse_bits(sensor_levels);
        
        // ���ʹ��������ݵ�USART2���е���
        USART2_SendString("Sensor Levels: ");
        for(i = 7; i >= 0; i--) {
            // �����λ�����λ��ʾ����Ӧ�����ҵĴ�����
            if(reversed_sensors & (1 << i)) {
                USART2_SendString("1 ");
            } else {
                USART2_SendString("0 ");
            }
        }
        sprintf(buffer, "(0x%02X -> 0x%02X)\r\n", sensor_levels, reversed_sensors);
        USART2_SendString(buffer);
        
        // ���ݷ�ת��Ĵ���������ִ��Ѳ���߼�
        // ���1: ���д���������⵽���߻�û�м�⵽ - ֹͣ
        if (reversed_sensors == 0xFF || reversed_sensors == 0x00) {
            Move_X = 0;
            Move_Y = 0;
            Move_Z = 0;
            USART2_SendString("Action: Stop\r\n");
        }
        // ���2: �м䴫������⵽���� - ֱ��
        else if ((reversed_sensors & 0x18) == 0x18) { // λ3��λ4
            Move_X = 0.5;
            Move_Y = 0;
            Move_Z = 0;
            USART2_SendString("Action: Forward\r\n");
        }
        // ���3: ��ഫ������⵽���� - ��ת
        else if (reversed_sensors & 0xE0) { // λ5,6,7 (���)
            Move_X = 0;
            Move_Y = -0.4;
            Move_Z = 0;
            USART2_SendString("Action: Turn Left\r\n");
        }
        // ���4: �Ҳഫ������⵽���� - ��ת
        else if (reversed_sensors & 0x07) { // λ0,1,2 (�Ҳ�)
            Move_X = 0;
            Move_Y = 0.4;
            Move_Z = 0;
            USART2_SendString("Action: Turn Right\r\n");
        }
        // ���5: ֻ������ഫ������⵽ - ��ƽ��
        else if (reversed_sensors == 0x80) { // ��λ7 (�����)
            Move_X = 0;
            Move_Y = 0;
            Move_Z = 2.5;
            USART2_SendString("Action: Strafe Left\r\n");
        }
        // ���6: ֻ�����Ҳഫ������⵽ - ��ƽ��
        else if (reversed_sensors == 0x01) { // ��λ0 (���Ҳ�)
            Move_X = 0;
            Move_Y = 0;
            Move_Z = -2.5;
            USART2_SendString("Action: Strafe Right\r\n");
        }
        // Ĭ�����: ֹͣ
        else {
            Move_X = 0;
            Move_Y = 0;
            Move_Z = 0;
            USART2_SendString("Action: Unknown - Stop\r\n");
        }
        
        // ���ñ�־
        new_data_available = 0;
    }
}

// �����Զ�ģʽ����ָ��
static void Send_AutoMode_Command(void)
{
    uint8_t config_frame[5];
    char buffer[20];
    uint8_t i;
    
    // ��������ָ��֡: 0x55, 0xAA, 1, 0, ~(1 + 0)
    config_frame[0] = LINEFOLLOW_HEADER1;
    config_frame[1] = LINEFOLLOW_HEADER2;
    config_frame[2] = 1; // 自动发送电平值模式
    config_frame[3] = 0; // 数据长度为0
    config_frame[4] = Calculate_Checksum((uint8_t *)&config_frame[2], 2);
    
    // ��������ָ��
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

// ����У���
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

// USART2����һ���ֽ�
static void USART2_SendByte(uint8_t data)
{
    USART_SendData(USART2, data);
    while(USART_GetFlagStatus(USART2, USART_FLAG_TXE) == RESET);
}

// USART2�����ַ���
static void USART2_SendString(char *str)
{
    while(*str)
    {
        USART2_SendByte(*str++);
    }
}

// λ��ת����
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

// USART3�жϷ������
void USART3_IRQHandler(void)
{
    uint8_t received_byte;
    
    // ���������ж�
    if(USART_GetITStatus(USART3, USART_IT_RXNE) != RESET)
    {
        received_byte = USART_ReceiveData(USART3);
        
        // ֱ�Ӵ������յ����ֽ�
        sensor_levels = received_byte;
        new_data_available = 1;
        
        // ����жϱ�־
        USART_ClearITPendingBit(USART3, USART_IT_RXNE);
    }
}
