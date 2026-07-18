#include "bsp.h"

// ���Ӷ��л������Դ洢�������
#define COMMAND_QUEUE_SIZE 10
static uint8_t command_queue[COMMAND_QUEUE_SIZE];
static uint8_t queue_head = 0;
static uint8_t queue_tail = 0;
static uint8_t command_count = 0;

// ģ���ڲ�״̬
static volatile bool data_received = false;      // ���ݽ��ձ�־(volatileȷ���ɼ���)
static volatile bool command_ready = false;      // ���������־

// ��ʼ�����ڴ���ģ��
void SerialDispose_Init(void)
{
    memset(command_queue, 0, sizeof(command_queue));
    queue_head = 0;
    queue_tail = 0;
    command_count = 0;
    data_received = false;
    command_ready = false;
    
    // ʹ��USART2�����ж�
    USART_ITConfig(USART2, USART_IT_RXNE, ENABLE);
    NVIC_EnableIRQ(USART2_IRQn);
}

// ���ڽ����жϷ�����
void USART2_IRQHandler(void)
{
    if (USART_GetITStatus(USART2, USART_IT_RXNE) != RESET) {
        // ��ȡ���յ�������
        uint8_t received_char = USART_ReceiveData(USART2);
        
        // �����ݴ������
        command_queue[queue_tail] = received_char;
        queue_tail = (queue_tail + 1) % COMMAND_QUEUE_SIZE;
        if (command_count < COMMAND_QUEUE_SIZE) {
            command_count++;
        } else {
            // ���������������������ݣ�ͷָ��ǰ����
            queue_head = (queue_head + 1) % COMMAND_QUEUE_SIZE;
        }
        
        data_received = true;
        command_ready = true;
        
        // ����жϱ�־
        USART_ClearITPendingBit(USART2, USART_IT_RXNE);
    }
}

// �����������ݣ�����ѭ���е��ã�
void SerialDispose_Process(void)
{
    // ������ѽ��յ�δ����������
    while (command_count > 0) {
        uint8_t received_char = command_queue[queue_head];
        queue_head = (queue_head + 1) % COMMAND_QUEUE_SIZE;
        command_count--;
        
        // ��������ִ����Ӧ����
        switch (received_char) {
            case '0': // ASCII '0'
                LED_OFF();
                performHandAction();  // ִ�л��ֶ���
                break;
                
            case '1': // ASCII '1'
                LED_ON();
                performHandshake();   // ִ�����ֶ���
                break;
                
            case '2': // ASCII '2'
                performSwingAction(); // ִ��˫�ֻӶ�����
                break;
                
            case '6': // �������������
                Ultrasonic_SetEnable(1);  // ʹ�ó�����ģ���API
                break;
                
            case '7': // �رճ��������
                Ultrasonic_SetEnable(0);  // ʹ�ó�����ģ���API
                break;
			
			case '3': 
                uplift_hand();  // ̧��
                break;
			
			case '4': 
                uplift_doublehand();  // ˫��̧��
                break;
			
			case '8': 
                alimbo_hand();  // ����
                break;
			
			case '9': 
                performReset();  // ��λ
                break;
			case 'A':
				uphand_adjust();
				break;
			
			case 'G': 
                dance_hand();  
				break;

            case 'P':  // �����������ּ�ȡǰ������
                performPickGarbage();
                break;

            case 'Q':  // ����������������������ڲ�
                performPlaceGarbageInternal();
                break;
                
            default:
                // δ֪�����
                break;
        }
    }
}

// ����Ƿ����µ���������
uint8_t SerialDispose_HasCommand(void)
{
    return command_ready;
}

// ��ȡ��ǰ��������
uint8_t SerialDispose_GetCommand(void)
{
    if (command_count == 0) {
        return 0; // û������
    }
    
    uint8_t cmd = command_queue[queue_head];
    queue_head = (queue_head + 1) % COMMAND_QUEUE_SIZE;
    command_count--;
    
    if (command_count == 0) {
        command_ready = false;
    }
    
    return cmd;
}
