#ifndef __SYS_H
#define __SYS_H	
#include "stm32f10x.h"
/***********************************************
公司：轮趣科技（东莞）有限公司
品牌：WHEELTEC
官网：wheeltec.net
淘宝店铺：shop114407458.taobao.com 
速卖通: https://minibalance.aliexpress.com/store/4455017
版本：V1.0
修改时间：2023-01-04

Brand: WHEELTEC
Website: wheeltec.net
Taobao shop: shop114407458.taobao.com 
Aliexpress: https://minibalance.aliexpress.com/store/4455017
Version: V1.0
Update：2023-01-04

All rights reserved
***********************************************/	 

//0,不支持ucos
//1,支持ucos
#define SYSTEM_SUPPORT_OS		0		//定义系统文件夹是否支持UCOS
														// 在 sys.h 中定义方向标志
extern uint8_t Flag_Direction;  // 使用项目原有的定义			    
	 
//位带操作,实现51类似的GPIO控制功能
//具体实现思想,参考<<CM3权威指南>>第五章(87页~92页).
//IO口操作宏定义
#define BITBAND(addr, bitnum) ((addr & 0xF0000000)+0x2000000+((addr &0xFFFFF)<<5)+(bitnum<<2)) 
#define MEM_ADDR(addr)  *((volatile unsigned long  *)(addr)) 
#define BIT_ADDR(addr, bitnum)   MEM_ADDR(BITBAND(addr, bitnum)) 
//IO口地址映射
#define GPIOA_ODR_Addr    (GPIOA_BASE+12) //0x4001080C 
#define GPIOB_ODR_Addr    (GPIOB_BASE+12) //0x40010C0C 
#define GPIOC_ODR_Addr    (GPIOC_BASE+12) //0x4001100C 
#define GPIOD_ODR_Addr    (GPIOD_BASE+12) //0x4001140C 
#define GPIOE_ODR_Addr    (GPIOE_BASE+12) //0x4001180C 
#define GPIOF_ODR_Addr    (GPIOF_BASE+12) //0x40011A0C    
#define GPIOG_ODR_Addr    (GPIOG_BASE+12) //0x40011E0C    

#define GPIOA_IDR_Addr    (GPIOA_BASE+8) //0x40010808 
#define GPIOB_IDR_Addr    (GPIOB_BASE+8) //0x40010C08 
#define GPIOC_IDR_Addr    (GPIOC_BASE+8) //0x40011008 
#define GPIOD_IDR_Addr    (GPIOD_BASE+8) //0x40011408 
#define GPIOE_IDR_Addr    (GPIOE_BASE+8) //0x40011808 
#define GPIOF_IDR_Addr    (GPIOF_BASE+8) //0x40011A08 
#define GPIOG_IDR_Addr    (GPIOG_BASE+8) //0x40011E08 
 
//IO口操作,只对单一的IO口!
//确保n的值小于16!
#define PAout(n)   BIT_ADDR(GPIOA_ODR_Addr,n)  //输出 
#define PAin(n)    BIT_ADDR(GPIOA_IDR_Addr,n)  //输入 

#define PBout(n)   BIT_ADDR(GPIOB_ODR_Addr,n)  //输出 
#define PBin(n)    BIT_ADDR(GPIOB_IDR_Addr,n)  //输入 

#define PCout(n)   BIT_ADDR(GPIOC_ODR_Addr,n)  //输出 
#define PCin(n)    BIT_ADDR(GPIOC_IDR_Addr,n)  //输入 

#define PDout(n)   BIT_ADDR(GPIOD_ODR_Addr,n)  //输出 
#define PDin(n)    BIT_ADDR(GPIOD_IDR_Addr,n)  //输入 

#define PEout(n)   BIT_ADDR(GPIOE_ODR_Addr,n)  //输出 
#define PEin(n)    BIT_ADDR(GPIOE_IDR_Addr,n)  //输入

#define PFout(n)   BIT_ADDR(GPIOF_ODR_Addr,n)  //输出 
#define PFin(n)    BIT_ADDR(GPIOF_IDR_Addr,n)  //输入

#define PGout(n)   BIT_ADDR(GPIOG_ODR_Addr,n)  //输出 
#define PGin(n)    BIT_ADDR(GPIOG_IDR_Addr,n)  //输入
/////////////////////////////////////////////////////////////////////////////
//Ex_NVIC_Config专用定义
#define GPIO_A 0
#define GPIO_B 1
#define GPIO_C 2
#define GPIO_D 3
#define GPIO_E 4
#define GPIO_F 5
#define GPIO_G 6 
#define SERVO_INIT 1500
#define FTIR   1  //下降沿触发
#define RTIR   2  //上升沿触发

#include "delay.h"
#include "usart.h"
#include "adc.h"
#include "KEY.h"
#include "LED.h"
#include "usart_x.h"
#include "TIM.h"
#include "I2C.h"
#include "ICM20948.h"
#include "conctrl.h"
#include "oled.h"
#include "motor.h"
#include "Encoder.h"
#include "show.h"
#include "control.h"
#include "avoidance.h"



/**************************************小车各模式定义*****************************/
#define Normal_Mode								0
#define Lidar_Mode								1

#define ROS_Mode				          0
#define APP_Mode									1

#define Lidar_Avoid_Mode					0
#define Lidar_Follow_Mode					1
#define Lidar_Along_Mode				  2	
/****************************************************************************/
//圆周率
#define Pi									3.14159265358979f	

//Encoder data reading frequency
//编码器数据读取频率
#define   CONTROL_FREQUENCY 100

/**********************************电机相关参数********************************/
//The encoder octave depends on the encoder initialization Settings
//编码器倍频数，取决于编码器初始化设置
#define   EncoderMultiples  4
//Motor_gear_ratio
//电机减速比（注意：原减速比为60，这里存储的值为减速比的一半，即30；现减速比为56，所以改为28）
#define   HALL_30F    28
//Number_of_encoder_lines
//编码器线数（原13线，现11线）
#define	  Hall_13     11
//
//霍尔电机每转动一圈能读取到的读数（即车轮转一圈编码器读取的数值）
//计算公式：EncoderMultiples * 减速比 * 编码器线数
//原值1560 = 4 * 30 * 13
//新值 = 4 * 28 * 11 = 1232
#define Encoder_precision	(EncoderMultiples*HALL_30F*Hall_13)

/**********************************车轮相关参数*********************************/
//Wheelspacing, Mec_Car is half wheelspacing
//轮距 麦轮是一半
#define MEC_wheelspacing         0.093
//Axlespacing, Mec_Car is half axlespacing
//轴距 麦轮是一半
#define MEC_axlespacing           0.085
//Mecanum wheel tire diameter series
//麦轮轮胎直径
#define		Mecanum_75  0.075
//
//麦轮周长（直径*Pi）
#define Wheel_perimeter Mecanum_75*Pi

//默认遥控速度，单位mm/s
#define Default_Velocity					350			
//遥控控制前后速度最大值
#define MAX_RC_Velocity						800
//遥控控制前后速度最小值
#define MINI_RC_Velocity					210
//前进加减速幅度值，每次遥控加减的步进值
#define X_Step								25
/*******************************ROS协议相关信息*********************************/
//Frame_header 
//帧头
#define FRAME_HEADER      0X7B 
//Frame_tail   
//帧尾
#define FRAME_TAIL        0X7D 
/*******************************雷达模式下相关参数*********************************/
#define Follow_Distance 1600  //跟随距离
#define Keep_Follow_Distance 400  //跟随保持距离

#define Avoid_Min_Distance 300  //避障最小距离
#define Avoid_Distance 450     //避障距离
#define forward_velocity 0.3  //Move_X速度

#define corner_velocity 0.5    //Move_Y速度
#define other_corner_velocity 1.0    //Move_Y速度

#define amplitude_limiting 0.6   //速度限幅

#define limit_distance 100   //限制走直线模式下雷达探测距离



extern int Count;
extern u32 voltage;
extern u16 adc_val;
extern u8 Car_Mode,Mode;
extern float Axle_spacing;
extern float Wheel_spacing;
extern float Velocity_KP,Velocity_KI;
extern float Along_Distance_KP,Along_Distance_KI,Along_Distance_KD;
extern float Distance_KP,Distance_KI,Distance_KD;
extern float Follow_KP,Follow_KI,Follow_KD;
extern float Move_X, Move_Y, Move_Z;
extern float RC_Velocity;
extern u8 Flag_Direction;
extern u8 PID_Send;
extern u8 Flag_Left, Flag_Right, Flag_Direction;
extern u8 Receive_Data[12];
extern u8 Lidar_Success_Receive_flag;
extern volatile uint32_t system_tick;

//JTAG模式设置定义
#define JTAG_SWD_DISABLE   0X02
#define SWD_ENABLE         0X01
#define JTAG_SWD_ENABLE    0X00	   


/////////////////////////////////////////////////////////////////  
void Stm32_Clock_Init(u8 PLL);  //时钟初始化  
void Sys_Soft_Reset(void);      //系统软复位
void Sys_Standby(void);         //待机模式 	
void MY_NVIC_SetVectorTable(u32 NVIC_VectTab, u32 Offset);//设置偏移地址
void MY_NVIC_PriorityGroupConfig(u8 NVIC_Group);//设置NVIC分组
void MY_NVIC_Init(u8 NVIC_PreemptionPriority,u8 NVIC_SubPriority,u8 NVIC_Channel,u8 NVIC_Group);//设置中断
void Ex_NVIC_Config(u8 GPIOx,u8 BITx,u8 TRIM);//外部中断配置函数(只对GPIOA~G)
void JTAG_Set(u8 mode);
//////////////////////////////////////////////////////////////////////////////
//以下为汇编函数
void WFI_SET(void);		//执行WFI指令
void INTX_DISABLE(void);//关闭所有中断
void INTX_ENABLE(void);	//开启所有中断
void MSR_MSP(u32 addr);	//设置堆栈地址
#include <string.h> 
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#endif
