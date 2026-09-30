#include "asr.h"
extern "C"{ void * __dso_handle = 0 ;}
#include "setup.h"
#include "HardwareSerial.h"
#include "myLib/asr_event.h"

uint32_t snid;
void UART();
String introduce;
void usart_init();
void app();
void ASR_CODE();
void voice_usart();
void voice_set();

//{speak:云儿-温柔女声,vol:10,speed:6,platform:haohaodada,version:V3}
//{playid:10001,voice:}
//{playid:10002,voice:}

void UART(){
  while (1) {
    if(Serial.available() > 0){
      introduce = Serial.readString();
      if(introduce == "000"){
        delay(2);
        Serial.println(0,HEX);
        //{playid:10500,voice:你好思宇}
        play_audio(10500);
      }
      if(introduce == "001"){
        delay(2);
        Serial.println(0,HEX);
        //{playid:10501,voice:曹总你好}
        play_audio(10501);
      }
      if(introduce == "002"){
        delay(2);
        Serial.println(0,HEX);
        //{playid:10502,voice:九号你好}
        play_audio(10502);
      }
      if(introduce == "003"){
        delay(2);
        Serial.println(0,HEX);
        //{playid:10503,voice:阿楠你好}
        play_audio(10503);
      }
      if(introduce == "0"){
        delay(2);
        //{playid:10504,voice:请正对摄像头}
        play_audio(10504);
      }
      if(introduce == "1"){
        delay(2);
        //{playid:10505,voice:人脸录入完毕}
        play_audio(10505);
      }
      introduce = "";
    }
    delay(2);
  }
  vTaskDelete(NULL);
}

//{ID:10250,keyword:"命令词",ASR:"最大音量",ASRTO:""}
//{ID:10251,keyword:"命令词",ASR:"音量调到中等",ASRTO:""}
//{ID:10252,keyword:"命令词",ASR:"最小音量",ASRTO:""}
/*描述该功能...
*/
void usart_init(){
  setPinFun(13,SECOND_FUNCTION);
  setPinFun(14,SECOND_FUNCTION);
  Serial.begin(115200);
  Serial.setTimeout(10);
}

void app(){
  if(digitalRead(6) == 0){
    //{playid:10506,voice:电量低，请及时充电}
    play_audio(10506);
    delay(5000);
    //{playid:10507,voice:电量低，请及时充电}
    play_audio(10507);
    delay(5000);
    //{playid:10508,voice:电量低，请及时充电}
    play_audio(10508);
  }
  delay(2);
  vTaskDelete(NULL);
}

/*描述该功能...
*/
void ASR_CODE(){
  voice_usart();

}

/*描述该功能...
*/
void voice_usart(){
  set_state_enter_wakeup(3000000);
  if((snid) == 1){
    Serial.print(0);
  }
  if((snid) == 2){
    Serial.print(0);
  }
  if((snid) == 3){
    Serial.print(0);
  }
  if((snid) == 4){
    Serial.print(1);
  }
  if((snid) == 5){
    Serial.print(1);
  }
  if((snid) == 6){
    Serial.print(1);
  }
  if((snid) == 8){
    Serial.print(1);
  }
  if((snid) == 7){
    Serial.print(6);
  }
  if((snid) == 9){
    Serial.print(6);
  }
  if((snid) == 10){
    Serial.print(6);
  }
  if((snid) == 11){
    Serial.print(6);
  }
  if((snid) == 12){
    Serial.print(2);
  }
  if((snid) == 13){
    Serial.print(3);
  }
  if((snid) == 14){
    Serial.print(4);
  }
  if((snid) == 15){
    Serial.print(5);
  }
  if((snid) == 16){
    Serial.print(7);
  }
  if((snid) == 17){
    Serial.print(8);
  }
  if((snid) == 18){
    Serial.print(9);
  }
  if((snid) == 19){
    Serial.print(9);
  }
  if((snid) == 20){
    Serial.print("A");
  }
}

/*描述该功能...
*/
void voice_set(){
  //{ID:1,keyword:"唤醒词",ASR:"小明同学",ASRTO:""}
  //{ID:2,keyword:"唤醒词",ASR:"嗨佬麦",ASRTO:""}
  //{ID:3,keyword:"唤醒词",ASR:"同志们好",ASRTO:""}
  //{ID:4,keyword:"命令词",ASR:"起身",ASRTO:""}
  //{ID:5,keyword:"命令词",ASR:"起来吧",ASRTO:""}
  //{ID:6,keyword:"命令词",ASR:"半身启动",ASRTO:""}
  //{ID:7,keyword:"命令词",ASR:"半身复位",ASRTO:""}
  //{ID:8,keyword:"命令词",ASR:"上身启动",ASRTO:""}
  //{ID:9,keyword:"命令词",ASR:"上身复位",ASRTO:""}
  //{ID:10,keyword:"命令词",ASR:"复位",ASRTO:""}
  //{ID:11,keyword:"命令词",ASR:"退下吧",ASRTO:""}
  //{ID:12,keyword:"命令词",ASR:"打开人脸识别",ASRTO:"好的"}
  //{ID:13,keyword:"命令词",ASR:"关闭人脸识别",ASRTO:"好的"}
  //{ID:14,keyword:"命令词",ASR:"打开打卡系统",ASRTO:"好的"}
  //{ID:15,keyword:"命令词",ASR:"关闭打卡系统",ASRTO:"好的"}
  //{ID:16,keyword:"命令词",ASR:"头部归位",ASRTO:"好的，头部已归位"}
  //{ID:17,keyword:"命令词",ASR:"开始录入人脸",ASRTO:"好的，请正对摄像头开始录入人脸"}
  //{ID:18,keyword:"命令词",ASR:"开启跟踪",ASRTO:"好的"}
  //{ID:19,keyword:"命令词",ASR:"跟着我",ASRTO:"好呀"}
  //{ID:20,keyword:"命令词",ASR:"关闭跟踪",ASRTO:"好的"}
}

void hardware_init(){
  xTaskCreate(UART,"UART",128,NULL,4,NULL);
  vol_set(7);
  xTaskCreate(app,"app",128,NULL,4,NULL);
  vTaskDelete(NULL);
}

void setup()
{
  usart_init();
  voice_set();
  setPinFun(6,FIRST_FUNCTION);
  pinMode(6,input);
  dpmu_set_io_pull(pinToFun[6],DPMU_IO_PULL_UP);
}
