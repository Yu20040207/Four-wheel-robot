#include "usart.h"	  

//加入以下代码,支持printf函数,而不需要选择use MicroLIB	  
#if 1
#pragma import(__use_no_semihosting)             
//标准库需要的支持函数                 
struct __FILE 
{ 
	int handle; 
	/* Whatever you require here. If the only file you are using is */ 
	/* standard output using printf() for debugging, no file handling */ 
	/* is required. */ 
}; 
/* FILE is typedef’ d in stdio.h. */ 
FILE __stdout;       
//定义_sys_exit()以避免使用半主机模式    
_sys_exit(int x) 
{ 
	x = x; 
} 
//重定义fputc函数 
int fputc(int ch, FILE *f)
{      
	while((USART1->SR&0X40)==0);//Flag_Show!=0  使用串口2   
	USART1->DR = (u8) ch;    
	return ch;
	
	//while((USART3->SR&0X40)==0);//Flag_Show!=0  使用串口2   
	//USART3->DR = (u8) ch;    
	//return ch;
}
#endif 
//end

