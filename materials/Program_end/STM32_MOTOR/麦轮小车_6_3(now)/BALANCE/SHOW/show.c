#include "show.h"

void Show(void)
{
	memset(OLED_GRAM,0, 128*8*sizeof(u8));
	/*************************第一行************************/
	OLED_ShowString(00, 00, "Mec");
	if(Mode==Normal_Mode)								OLED_ShowString(80, 00, "     ");
	else if(Mode==Lidar_Mode)						OLED_ShowString(80, 00, "Lidar");
	/*************************第二行************************/
	OLED_ShowString(00, 10, "A:");
	if(MOTOR_A.Encoder>0)	OLED_ShowString(18, 10, "+"),
												OLED_ShowNumber(30, 10, MOTOR_A.Encoder*1000, 5, 12);
	else									OLED_ShowString(18, 10, "-"),
												OLED_ShowNumber(30, 10, -MOTOR_A.Encoder*1000, 5, 12);
	
	if(MOTOR_A.Target>0)	OLED_ShowString(78, 10, "+"),
												OLED_ShowNumber(90, 10, MOTOR_A.Target*1000, 5, 12);
	else									OLED_ShowString(78, 10, "-"),
												OLED_ShowNumber(90, 10, -MOTOR_A.Target*1000, 5, 12);
	/*************************第三行************************/
	OLED_ShowString(00, 20, "B:");
	if(MOTOR_B.Encoder>0)	OLED_ShowString(18, 20, "+"),
												OLED_ShowNumber(30, 20, MOTOR_B.Encoder*1000, 5, 12);
	else									OLED_ShowString(18, 20, "-"),
												OLED_ShowNumber(30, 20, -MOTOR_B.Encoder*1000, 5, 12);
	
	if(MOTOR_B.Target>0)	OLED_ShowString(78, 20, "+"),
												OLED_ShowNumber(90, 20, MOTOR_B.Target*1000, 5, 12);
	else									OLED_ShowString(78, 20, "-"),
												OLED_ShowNumber(90, 20, -MOTOR_B.Target*1000, 5, 12);
	/*************************第四行************************/
	OLED_ShowString(00, 30, "C:");
	if(MOTOR_C.Encoder>0)	OLED_ShowString(18, 30, "+"),
												OLED_ShowNumber(30, 30, MOTOR_C.Encoder*1000, 5, 12);
	else									OLED_ShowString(18, 30, "-"),
												OLED_ShowNumber(30, 30, -MOTOR_C.Encoder*1000, 5, 12);
	
	if(MOTOR_C.Target>0)	OLED_ShowString(78, 30, "+"),
												OLED_ShowNumber(90, 30, MOTOR_C.Target*1000, 5, 12);
	else									OLED_ShowString(78, 30, "-"),
												OLED_ShowNumber(90, 30, -MOTOR_C.Target*1000, 5, 12);
	/*************************第五行************************/
	OLED_ShowString(00, 40, "D:");
	if(MOTOR_D.Encoder>0)	OLED_ShowString(18, 40, "+"),
												OLED_ShowNumber(30, 40, MOTOR_D.Encoder*1000, 5, 12);
	else									OLED_ShowString(18, 40, "-"),
												OLED_ShowNumber(30, 40, -MOTOR_D.Encoder*1000, 5, 12);
	
	if(MOTOR_D.Target>0)	OLED_ShowString(78, 40, "+"),
												OLED_ShowNumber(90, 40, MOTOR_D.Target*1000, 5, 12);
	else									OLED_ShowString(78, 40, "-"),
												OLED_ShowNumber(90, 40, -MOTOR_D.Target*1000, 5, 12);

	/*************************第六行************************/
	if(Mode==Normal_Mode)											
	{
		if(Car_Mode==APP_Mode)							OLED_ShowString(00, 50, "APP   ");
		else if(Car_Mode==ROS_Mode)					OLED_ShowString(00, 50, "ROS   ");
	}									
	else if(Mode==Lidar_Mode)
	{
		if(Car_Mode==Lidar_Avoid_Mode)						OLED_ShowString(00, 50, "Avoid ");
		else if(Car_Mode==Lidar_Along_Mode)				OLED_ShowString(00, 50, "Along ");
		else if(Car_Mode==Lidar_Follow_Mode)			OLED_ShowString(00, 50, "Follow");
	}
	
	OLED_ShowString(54, 50, "Vol:");
	OLED_ShowNumber(84, 50, voltage/100, 2, 12);
	OLED_ShowString(96, 50, ".");
	OLED_ShowNumber(102, 50, voltage%100, 2, 12);
	OLED_ShowString(114, 50, "V");
		
	OLED_Refresh_Gram();
}

void APP_Show(void)
{
	static u8 flag_show;
	 int Left_Figure,Right_Figure,Voltage_Show;
	
	//读取ADC通道11的ADC值
	adc_val = Get_adc_Average(11, 2);
	//ADC值转化为电源电压
	voltage = adc_val*3.3*11*100/4096;
	
	 //The battery voltage is processed as a percentage
	 //对电池电压处理成百分比形式
	 Voltage_Show=(voltage*1000-10000)/27;
	 if(Voltage_Show>100)Voltage_Show=100; 
	
	 //Wheel speed unit is converted to 0.01m/s for easy display in APP
	 //车轮速度单位转换为0.01m/s，方便在APP显示
	 Left_Figure=MOTOR_A.Encoder*100;  if(Left_Figure<0)Left_Figure=-Left_Figure;	
	 Right_Figure=MOTOR_B.Encoder*100; if(Right_Figure<0)Right_Figure=-Right_Figure;
	
	 //Used to alternately print APP data and display waveform
	 //用于交替打印APP数据和显示波形
	 flag_show=!flag_show;
	 
	 if(PID_Send==1) 
	 {	 
		 if(Mode==Lidar_Mode)
		 {
			 if(Car_Mode == Lidar_Along_Mode)  //走直线模式下APP调整PID参数
			 {
					 printf("{C%d:%d:%d}$",(int)Along_Distance_KP,(int)Along_Distance_KD,(int)Along_Distance_KI);
			 }
				else if(Car_Mode == Lidar_Follow_Mode)   //跟随模式下APP调整PID距离参数
			 {
				 printf("{C%d:%d:%d:%d:%d:%d}$",(int)Distance_KP,(int)Distance_KD,(int)Distance_KI,(int)Follow_KP,(int)Follow_KD,(int)Follow_KI);
			 }
		 }
		 else
		 {
				//Send parameters to the APP, the APP is displayed in the debug screen
				//发送参数到APP，APP在调试界面显示
				//printf("{C%d:%d:%d}$",(int)RC_Velocity,(int)Velocity_KP,(int)Velocity_KI);
				printf("{C%d:%d:%d}$",(int)Velocity_KP,(int)Velocity_KI,(int)RC_Velocity);
			 // printf("{B%d}$",(int)PointDataProcess[i].distance);
		 }
		 PID_Send=0;
	 }
    else if(flag_show==0)
		 {
			 //Send parameters to the APP and the APP will be displayed on the front page
			 //发送参数到APP，APP在首页显示
		   printf("{A%d:%d:%d}$",(u8)Left_Figure,(u8)Right_Figure,Voltage_Show);
		 }
		 else
	 {
		 //Send parameters to the APP, the APP is displayed in the waveform interface
		 //发送参数到APP，APP在波形界面显示，把需要显示的波形填进相应的位置即可，最多可以显示5个波形
	   printf("{B%d:%d:%d}$",(int)RC_Velocity,(u8)Left_Figure,(u8)Right_Figure);
	 }
}



