#include "bsp.h"

// 增加队列缓冲区以存储多个命令
#define COMMAND_QUEUE_SIZE 10
static uint8_t command_queue[COMMAND_QUEUE_SIZE];
static uint8_t queue_head = 0;
static uint8_t queue_tail = 0;
static uint8_t command_count = 0;

// 模块内部状态
static volatile bool data_received = false;      // 数据接收标志(volatile确保可见性)
static volatile bool command_ready = false;      // 命令就绪标志

// 初始化串口处理模块
void SerialDispose_Init(void)
{
    memset(command_queue, 0, sizeof(command_queue));
    queue_head = 0;
    queue_tail = 0;
    command_count = 0;
    data_received = false;
    command_ready = false;
    
    // 使能USART2接收中断
    USART_ITConfig(USART2, USART_IT_RXNE, ENABLE);
    NVIC_EnableIRQ(USART2_IRQn);
}

// 串口接收中断服务函数
void USART2_IRQHandler(void)
{
    if (USART_GetITStatus(USART2, USART_IT_RXNE) != RESET) {
        // 读取接收到的数据
        uint8_t received_char = USART_ReceiveData(USART2);
        
        // 将数据存入队列
        command_queue[queue_tail] = received_char;
        queue_tail = (queue_tail + 1) % COMMAND_QUEUE_SIZE;
        if (command_count < COMMAND_QUEUE_SIZE) {
            command_count++;
        } else {
            // 队列已满，丢弃队首数据（头指针前进）
            queue_head = (queue_head + 1) % COMMAND_QUEUE_SIZE;
        }
        
        data_received = true;
        command_ready = true;
        
        // 清除中断标志
        USART_ClearITPendingBit(USART2, USART_IT_RXNE);
    }
}

// 处理串口数据（在主循环中调用）
void SerialDispose_Process(void)
{
    // 如果有已接收但未处理的命令
    while (command_count > 0) {
        uint8_t received_char = command_queue[queue_head];
        queue_head = (queue_head + 1) % COMMAND_QUEUE_SIZE;
        command_count--;
        
        // 根据命令执行相应动作
        switch (received_char) {
            case '0': // ASCII '0'
                LED_OFF();
                performHandAction();  // 执行挥手动作
                break;
                
            case '1': // ASCII '1'
                LED_ON();
                performHandshake();   // 执行握手动作
                break;
                
            case '2': // ASCII '2'
                performSwingAction(); // 执行双手挥动动作
                break;
                
            case '6': // 开启超声波检测
                Ultrasonic_SetEnable(1);  // 使用超声波模块的API
                break;
                
            case '7': // 关闭超声波检测
                Ultrasonic_SetEnable(0);  // 使用超声波模块的API
                break;
			
			case '3': 
                uplift_hand();  // 抬手
                break;
			
			case '4': 
                uplift_doublehand();  // 双手抬起
                break;
			
			case '8': 
                alimbo_hand();  // 叉腰
                break;
			
			case '9': 
                performReset();  // 复位
				timer_delay_ms(DELAY_TIME);
				performReset();  // 确保复位
                break;
			case 'A':
				uphand_adjust();
				break;
			
			case 'G': 
                dance_hand();  
				break;
                
            default:
                // 未知命令处理
                break;
        }
    }
}

// 检查是否有新的语音命令
uint8_t SerialDispose_HasCommand(void)
{
    return command_ready;
}

// 获取当前语音命令
uint8_t SerialDispose_GetCommand(void)
{
    if (command_count == 0) {
        return 0; // 没有命令
    }
    
    uint8_t cmd = command_queue[queue_head];
    queue_head = (queue_head + 1) % COMMAND_QUEUE_SIZE;
    command_count--;
    
    if (command_count == 0) {
        command_ready = false;
    }
    
    return cmd;
}
