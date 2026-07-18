#include "i2c_ctl.h"
#include "bsp.h"

/* 这个地址只要与STM32外挂的I2C器件地址不一样即可 */
#define I2Cx_OWN_ADDRESS7 0X0A
#define I2C_DEVICE I2C1

// 定义I2C_ADDR为你的外部设备地址
#ifndef I2C_ADDR 
#define I2C_ADDR 0x5D  // 八路巡线模块的固定I2C地址
#endif

#define I2C_Speed 100000
#define I2CT_FLAG_TIMEOUT ((uint32_t)0x1000)
#define I2CT_LONG_TIMEOUT ((uint32_t)(10 * I2CT_FLAG_TIMEOUT))

static __IO uint32_t I2CTimeout = I2CT_LONG_TIMEOUT;
static void I2C_GPIO_Config(void)
{
    GPIO_InitTypeDef GPIO_InitStructure;

    /* 使能与 I2C_DEVICE 有关的时钟 */
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_I2C1, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOB | RCC_APB2Periph_AFIO, ENABLE);

    /* PB6-I2C1_SCL、PB7-I2C1_SDA */
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_OD; // 开漏输出
    GPIO_Init(GPIOB, &GPIO_InitStructure);

    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_7;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF_OD; // 开漏输出
    GPIO_Init(GPIOB, &GPIO_InitStructure);
}

static void I2C_Mode_Configu(void)
{
    I2C_InitTypeDef I2C_InitStructure;
    
    /* I2C 外设复位 */
    RCC_APB1PeriphResetCmd(RCC_APB1Periph_I2C1, ENABLE);
    RCC_APB1PeriphResetCmd(RCC_APB1Periph_I2C1, DISABLE);
    
    I2C_DeInit(I2C_DEVICE); // 复位I2C1

    /* I2C 配置 */
    I2C_InitStructure.I2C_Mode = I2C_Mode_I2C;
    I2C_InitStructure.I2C_DutyCycle = I2C_DutyCycle_2;
    I2C_InitStructure.I2C_OwnAddress1 = I2Cx_OWN_ADDRESS7;
    I2C_InitStructure.I2C_Ack = I2C_Ack_Enable;
    I2C_InitStructure.I2C_AcknowledgedAddress = I2C_AcknowledgedAddress_7bit;
    I2C_InitStructure.I2C_ClockSpeed = I2C_Speed;

    /* I2C1 初始化 */
    I2C_Init(I2C_DEVICE, &I2C_InitStructure);

    /* 使能 I2C1 */
    I2C_Cmd(I2C_DEVICE, ENABLE);
}

void I2C_Bus_Init(void)
{
    I2C_GPIO_Config();
    I2C_Mode_Configu();
}

/**
  * @brief  Basic management of the timeout situation.
  * @param  None.
  * @retval None.
  */
static uint8_t I2C_TIMEOUT_UserCallback(void)
{
    /* 超时处理 */
    I2C_GenerateSTOP(I2C_DEVICE, ENABLE);
    return 0;
}

/**
  * @brief   写一个字节到I2C设备中
  * @param   
  *		@arg WriteAddr: 寄存器地址
  *		@arg pBuffer: 要写入的值
  * @retval  正常返回1，异常返回0
  */
uint8_t I2C_ByteWrite(uint8_t WriteAddr, uint8_t pBuffer)
{
    I2CTimeout = I2CT_FLAG_TIMEOUT;
    while (I2C_GetFlagStatus(I2C_DEVICE, I2C_FLAG_BUSY))
    {
        if ((I2CTimeout--) == 0)
            return I2C_TIMEOUT_UserCallback();
    }

    /* 发送START条件 */
    I2C_GenerateSTART(I2C_DEVICE, ENABLE);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV5事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_MODE_SELECT))
    {
        if ((I2CTimeout--) == 0)
            return I2C_TIMEOUT_UserCallback();
    }

    /* 发送从机地址（写模式） */
    I2C_Send7bitAddress(I2C_DEVICE, I2C_ADDR, I2C_Direction_Transmitter);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV6事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED))
    {
        if ((I2CTimeout--) == 0)
            return I2C_TIMEOUT_UserCallback();
    }

    /* 发送要写入的寄存器地址 */
    I2C_SendData(I2C_DEVICE, WriteAddr);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV8事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_BYTE_TRANSMITTED))
    {
        if ((I2CTimeout--) == 0)
            return I2C_TIMEOUT_UserCallback();
    }

    /* 发送要写入的数据 */
    I2C_SendData(I2C_DEVICE, pBuffer);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV8事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_BYTE_TRANSMITTED))
    {
        if ((I2CTimeout--) == 0)
            return I2C_TIMEOUT_UserCallback();
    }

    /* 发送STOP条件 */
    I2C_GenerateSTOP(I2C_DEVICE, ENABLE);
    Delay_ms(1);

    return 1; // 正常返回1
}

/**
  * @brief   从I2C设备读取多个字节 
  * @param   
  *		@arg reg_addr: 要读取的寄存器地址
  *		@arg pBuffer: 存放读取数据的缓冲区指针
  *		@arg NumByteToRead: 要读取的字节数
  * @retval  正常返回1，异常返回0
  */
uint8_t I2C_BufferRead(uint8_t reg_addr, uint8_t *pBuffer, uint8_t NumByteToRead)
{
    I2CTimeout = I2CT_LONG_TIMEOUT;
    uint8_t status = 1;
    
    /* 等待总线空闲 */
    while (I2C_GetFlagStatus(I2C_DEVICE, I2C_FLAG_BUSY))
    {
        if ((I2CTimeout--) == 0) {
            Usart_SendString((uint8_t *)"Error: Bus busy timeout!\r\n");
            status = 0;
            goto cleanup;
        }
    }

    /* 发送START条件 */
    I2C_GenerateSTART(I2C_DEVICE, ENABLE);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV5事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_MODE_SELECT))
    {
        if ((I2CTimeout--) == 0) {
            Usart_SendString((uint8_t *)"Error: EV5 timeout (START)!\r\n");
            status = 0;
            goto cleanup;
        }
    }

    /* 发送从机地址（写模式） - 修正地址移位问题 */
    I2C_Send7bitAddress(I2C_DEVICE, I2C_ADDR << 1, I2C_Direction_Transmitter);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV6事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED))
    {
        if ((I2CTimeout--) == 0) {
            Usart_SendString((uint8_t *)"Error: EV6 timeout (Addr TX)!\r\n");
            status = 0;
            goto cleanup;
        }
    }

    /* 发送要读取的寄存器地址 */
    I2C_SendData(I2C_DEVICE, reg_addr);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV8事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_BYTE_TRANSMITTED))
    {
        if ((I2CTimeout--) == 0) {
            Usart_SendString((uint8_t *)"Error: EV8 timeout (Reg TX)!\r\n");
            status = 0;
            goto cleanup;
        }
    }

    /* 发送重复START条件 */
    I2C_GenerateSTART(I2C_DEVICE, ENABLE);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV5事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_MODE_SELECT))
    {
        if ((I2CTimeout--) == 0) {
            Usart_SendString((uint8_t *)"Error: EV5 timeout (ReSTART)!\r\n");
            status = 0;
            goto cleanup;
        }
    }

    /* 发送从机地址（读模式） - 修正地址移位问题 */
    I2C_Send7bitAddress(I2C_DEVICE, (I2C_ADDR << 1) | 0x01, I2C_Direction_Receiver);

    I2CTimeout = I2CT_FLAG_TIMEOUT;
    /* 检查EV6事件 */
    while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_RECEIVER_MODE_SELECTED))
    {
        if ((I2CTimeout--) == 0) {
            Usart_SendString((uint8_t *)"Error: EV6 timeout (Addr RX)!\r\n");
            status = 0;
            goto cleanup;
        }
    }

    /* 读取多个字节 */
    while (NumByteToRead)
    {
        if (NumByteToRead == 1)
        {
            /* 读取最后一个字节时禁用应答 */
            I2C_AcknowledgeConfig(I2C_DEVICE, DISABLE);
            /* 发送STOP条件 */
            I2C_GenerateSTOP(I2C_DEVICE, ENABLE);
        }

        /* 检查EV7事件 */
        I2CTimeout = I2CT_FLAG_TIMEOUT;
        while (!I2C_CheckEvent(I2C_DEVICE, I2C_EVENT_MASTER_BYTE_RECEIVED))
        {
            if ((I2CTimeout--) == 0) {
                Usart_SendString((uint8_t *)"Error: EV7 timeout (Data RX)!\r\n");
                status = 0;
                goto cleanup;
            }
        }

        /* 读取数据 */
        *pBuffer = I2C_ReceiveData(I2C_DEVICE);
        pBuffer++;
        NumByteToRead--;
    }

cleanup:
    /* 重新使能应答 */
    I2C_AcknowledgeConfig(I2C_DEVICE, ENABLE);
    
    // 如果发生错误，发送STOP条件
    if(status == 0) {
        I2C_GenerateSTOP(I2C_DEVICE, ENABLE);
    }
    
    // 调试信息：显示操作结果
    if(status) {
        //Usart_SendString((uint8_t *)"I2C read successful!\r\n");
    } else {
        Usart_SendString((uint8_t *)"I2C read failed!\r\n");
    }

    return status;
}
