#ifndef __USART_X_H
#define __USART_X_H

#include "sys.h"

#define HEADER_0 0xA5
#define HEADER_1 0x5A
#define Data_Length 0x3A

#define POINT_PER_PACK 16

#define FRAME_HEADER      0X7B //Frame_header //帧头
#define FRAME_TAIL        0X7D //Frame_tail   //帧尾
#define SEND_DATA_SIZE    24

/*****A structure for storing triaxial data of a gyroscope accelerometer*****/
/*****用于存放陀螺仪加速度计三轴数据的结构体*********************************/
typedef struct __Mpu6050_Data_ 
{
	short X_data; //2 bytes //2个字节
	short Y_data; //2 bytes //2个字节
	short Z_data; //2 bytes //2个字节
}Mpu6050_Data;

/*******The structure of the serial port sending data************/
/*******串口发送数据的结构体*************************************/
typedef struct _SEND_DATA_  
{
	unsigned char buffer[SEND_DATA_SIZE];
	struct _Sensor_Str_
	{
		unsigned char Frame_Header; //1个字节
		short X_speed;	            //2 bytes //2个字节
		short Y_speed;              //2 bytes //2个字节
		short Z_speed;              //2 bytes //2个字节
		short Power_Voltage;        //2 bytes //2个字节
		Mpu6050_Data Accelerometer; //6 bytes //6个字节
		Mpu6050_Data Gyroscope;     //6 bytes //6个字节	
		unsigned char Frame_Tail;   //1 bytes //1个字节
	}Sensor_Str;
}SEND_DATA;

//N10雷达参数结构体
typedef struct PointData
{
	uint8_t distance_h;
	uint8_t distance_l;
	uint8_t Peak;

}LidarPointStructDef;

typedef struct PackData
{
	uint8_t header_0;
	uint8_t header_1;
	uint8_t data_len;
	
	uint8_t speed_h;
	uint8_t speed_l;
	uint8_t start_angle_h;
	uint8_t start_angle_l;	
	LidarPointStructDef point[POINT_PER_PACK];
	uint8_t end_angle_h;
	uint8_t end_angle_l;
	uint8_t crc;
}LiDARFrameTypeDef;

typedef struct PointDataProcess_
{
	u16 distance;
	float angle;
}PointDataProcessDef;

extern SEND_DATA Send_Data;
extern PointDataProcessDef Dataprocess[1000] ;//更新50个数据
extern LiDARFrameTypeDef Pack_Data;


void Data_Send(void);
void usart1_send(u8 data);
void usart2_send(u8 data);
void Usart1_Init(u32 bound);
void Usart2_Init(u32 bound);
void Usart3_Init(u32 bound);

int USART1_IRQHandler(void);

void data_process(void);
u8 Check_Sum(unsigned char Count_Number,unsigned char Mode);
float XYZ_Target_Speed_transition(u8 High,u8 Low);



#endif
