#ifndef __LINEFOLLOW_H
#define __LINEFOLLOW_H

#include "stm32f10x.h"

// 定义传感器结果类型为 uint8_t
typedef uint8_t SensorResult;

// 定义错误代码常量
#define SENSOR_ERROR_CODE 0xFF
uint8_t I2C_ByteWrite(uint8_t WriteAddr, uint8_t pBuffer);
uint8_t I2C_BufferRead(uint8_t reg_addr, uint8_t *pBuffer, uint8_t NumByteToRead);
void I2C_Bus_Init(void);

void LineSensor_Init(void);
SensorResult LineSensor_ReadData(void);
void LineSensor_PrintData(SensorResult data);

#endif
