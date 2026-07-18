#include "adc.h"

void ADC1_Init(void)
{
	GPIO_InitTypeDef GPIO_InitStructure;
	ADC_InitTypeDef ADC_InitStructure;
	//使能时钟
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_GPIOC, ENABLE);
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_ADC1, ENABLE);
	
	RCC_ADCCLKConfig(RCC_PCLK2_Div6);   //设置ADC分频因子6 72M/6=12,ADC最大时间不能超过14M
	
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AIN;
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_1;
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
	GPIO_Init(GPIOC, &GPIO_InitStructure);
	
	ADC_InitStructure.ADC_ScanConvMode = DISABLE;							//非扫描模式
	ADC_InitStructure.ADC_ContinuousConvMode = DISABLE;				//连续转换
	ADC_InitStructure.ADC_DataAlign = ADC_DataAlign_Right;		//右对齐
	ADC_InitStructure.ADC_ExternalTrigConv = ADC_ExternalTrigConv_None;		//使用软件触发
	ADC_InitStructure.ADC_Mode = ADC_Mode_Independent;				//独立模式
	ADC_InitStructure.ADC_NbrOfChannel = 1;										//只转换规则序列1
	ADC_Init(ADC1, &ADC_InitStructure);
	
	ADC_Cmd(ADC1, ENABLE);
	
	//复位ADC校准寄存器
	ADC_ResetCalibration(ADC1);
	//获取ADC校准寄存器状态
	while(ADC_GetResetCalibrationStatus(ADC1));
	//启动ADC校准
	ADC_StartCalibration(ADC1);
	//获取ADC启动校准寄存器状态
	while(ADC_GetCalibrationStatus(ADC1));
	
//	ADC_SoftwareStartConvCmd(ADC1, ENABLE);
}

//读取ADC数值
u16 Get_Adc1(u8 ch)
{
	ADC_RegularChannelConfig(ADC1, ch, 1, ADC_SampleTime_239Cycles5);
	
	ADC_SoftwareStartConvCmd(ADC1, ENABLE);
	
	while(!(ADC_GetFlagStatus(ADC1, ADC_FLAG_EOC)));
	
	return ADC_GetConversionValue(ADC1);
}

//连续读取ADC后取平均值
u16 Get_adc_Average(u8 ch, u8 count)
{
	u32 temp_val = 0;
	u8 i;
	
	for(i=0; i<count; i++)
	{
		temp_val += Get_Adc1(ch);
		delay_ms(5);
	}
	
	return temp_val/count;	
}
















