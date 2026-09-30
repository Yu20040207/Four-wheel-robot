#include "asr.h"
extern "C"{ void * __dso_handle = 0 ;}
#include "setup.h"
#include "HardwareSerial.h"
#include "myLib/asr_event.h"

uint32_t snid;
String introduce;
void usart_init();
void ASR_CODE();
void voice_usart();
void voice_set();
void voice1_usart1();

//{speak:云儿-温柔女声,vol:6,speed:6,platform:haohaodada,version:V3}
//{playid:10001,voice:你好，我是小明同学}
//{playid:10002,voice:}

//{ID:10250,keyword:"命令词",ASR:"最大音量",ASRTO:"好的，已调到最大音量"}
//{ID:10251,keyword:"命令词",ASR:"音量调到中等",ASRTO:"好的，音量已调到中等"}
//{ID:10252,keyword:"命令词",ASR:"最小音量",ASRTO:"音量调整到最小"}
/*描述该功能...
*/
void usart_init(){
  setPinFun(13,SECOND_FUNCTION);
  setPinFun(14,SECOND_FUNCTION);
  Serial.begin(115200);
  setPinFun(2,FORTH_FUNCTION);
  setPinFun(3,FORTH_FUNCTION);
  Serial1.begin(115200);
  setPinFun(5,FORTH_FUNCTION);
  setPinFun(6,FORTH_FUNCTION);
  Serial2.begin(115200);
  Serial.setTimeout(10);
  Serial1.setTimeout(10);
  Serial2.setTimeout(10);
}

/*描述该功能...
*/
void ASR_CODE(){
  voice_usart();
  voice1_usart1();

}

/*描述该功能...
*/
void voice_usart(){
  set_state_enter_wakeup(3000000);
  if((snid) == 0){
    Serial.println(0,HEX);
  }
  if((snid) == 34){
    Serial.println(0,HEX);
  }
  if((snid) == 1){
    Serial.println(1,HEX);
  }
  if((snid) == 2){
    Serial.println(2,HEX);
  }
  if((snid) == 3){
    vol_set(1);
  }
  if((snid) == 4){
    exit_wakeup_deal(0);
  }
  if((snid) == 5){
    Serial.println(3,HEX);
  }
  if((snid) == 6){
    Serial.println(4,HEX);
  }
  if((snid) == 7){
    Serial.println(0,HEX);
  }
  if((snid) == 8){
    //{playid:10500,voice:奔驰}
    play_audio(10500);
  }
  if((snid) == 10){
    Serial.println(4,HEX);
  }
  if((snid) == 11){
    Serial.println(3,HEX);
  }
  if((snid) == 12){
    Serial.println(4,HEX);
  }
  if((snid) == 13){
    Serial.println(6,HEX);
  }
  if((snid) == 14){
    Serial.println(7,HEX);
  }
  if((snid) == 15){
    Serial.println(8,HEX);
  }
  if((snid) == 16){
    Serial.println(9,HEX);
  }
  if((snid) == 17){
    Serial.println(10,HEX);
  }
  if((snid) == 18){
    Serial.println(11,HEX);
  }
  if((snid) == 19){
    Serial.println("a");
  }
  if((snid) == 20){
    Serial.println("b");
  }
  if((snid) == 21){
    Serial.println("c");
  }
  if((snid) == 22){
    Serial.println("d");
  }
  if((snid) == 39){
    Serial.println("e");
  }
  if((snid) == 40){
    Serial.println("e");
  }
  if((snid) == 23){
    Serial.println(12,HEX);
  }
  if((snid) == 24){
    Serial.println(13,HEX);
  }
  if((snid) == 25){
    Serial.println(14,HEX);
  }
  if((snid) == 26){
    Serial.println(15,HEX);
  }
  if((snid) == 27){
    Serial.println(15,HEX);
  }
  if((snid) == 28){
    Serial.println(16,HEX);
  }
  if((snid) == 29){
    Serial.println(17,HEX);
  }
  if((snid) == 30){
    Serial.println(18,HEX);
  }
  if((snid) == 31){
    Serial.println(19,HEX);
  }
  if((snid) == 32){
    Serial.println(10,HEX);
  }
  if((snid) == 33){
    Serial.println(11,HEX);
  }
  if((snid) == 35){
    Serial.println(0,HEX);
  }
  if((snid) == 36){
    Serial.println(21,HEX);
  }
  if((snid) == 37){
    Serial.println(21,HEX);
  }
  if((snid) == 38){
    Serial.println(21,HEX);
  }
}

/*描述该功能...
*/
void voice_set(){
  //{ID:9999,keyword:"唤醒词",ASR:"小明同学",ASRTO:""}
  //{ID:9997,keyword:"命令词",ASR:"同志们好",ASRTO:"首长好"}
  //{ID:9996,keyword:"命令词",ASR:"你好奔驰",ASRTO:"主驾请将"}
  //{ID:9995,keyword:"命令词",ASR:"给我叫",ASRTO:"我警告你，别给我在这哇哇叫"}
  //{ID:0,keyword:"命令词",ASR:"挥手",ASRTO:"你好呀"}
  //{ID:1,keyword:"命令词",ASR:"握手",ASRTO:"很高兴认识你"}
  //{ID:2,keyword:"命令词",ASR:"双手挥动",ASRTO:"好呀"}
  //{ID:3,keyword:"命令词",ASR:"关闭声音",ASRTO:"好的，那我不说话了"}
  //{ID:4,keyword:"命令词",ASR:"退下吧",ASRTO:"那我走啦，想我的话叫我小明同学"}
  //{ID:5,keyword:"命令词",ASR:"复位",ASRTO:""}
  //{ID:6,keyword:"命令词",ASR:"起身",ASRTO:""}
  //{ID:7,keyword:"命令词",ASR:"做个自我介绍",ASRTO:"大家好，我的名字是小明同学，是由添波动力公司设计的一款服务型机器人，有什么需求可以叫我哦"}
  //{ID:8,keyword:"命令词",ASR:"奔驰能替我说话吗",ASRTO:"当然，当你从奔驰车上下来的那一刻，就算你衣着普通，样貌平凡，在人群中，都是焦点，就算你生性内向，不言善语，在别人眼中也都是优点"}
  //{playid:9,voice:奔驰}
  //{ID:10,keyword:"命令词",ASR:"起来吧",ASRTO:""}
  //{ID:11,keyword:"命令词",ASR:"退下吧",ASRTO:"好的，我先退下啦"}
  //{ID:12,keyword:"命令词",ASR:"平身",ASRTO:"好的"}
  //{ID:13,keyword:"命令词",ASR:"打开避障模式",ASRTO:"避障模式已开启"}
  //{ID:14,keyword:"命令词",ASR:"关闭避障模式",ASRTO:"避障模式已关闭"}
  //{ID:15,keyword:"命令词",ASR:"打开巡线模式",ASRTO:"巡线模式已开启"}
  //{ID:16,keyword:"命令词",ASR:"关闭巡线模式",ASRTO:"巡线模式已关闭"}
  //{ID:17,keyword:"命令词",ASR:"打开语音控制",ASRTO:"语音控制已开启"}
  //{ID:18,keyword:"命令词",ASR:"关闭语音控制",ASRTO:"语音控制已关闭"}
  //{ID:19,keyword:"命令词",ASR:"前进",ASRTO:""}
  //{ID:20,keyword:"命令词",ASR:"后退",ASRTO:""}
  //{ID:21,keyword:"命令词",ASR:"左转",ASRTO:""}
  //{ID:22,keyword:"命令词",ASR:"右转",ASRTO:""}
  //{ID:23,keyword:"命令词",ASR:"抬手",ASRTO:"好的"}
  //{ID:24,keyword:"命令词",ASR:"双手抬起",ASRTO:"好的"}
  //{ID:25,keyword:"命令词",ASR:"叉腰",ASRTO:""}
  //{ID:26,keyword:"命令词",ASR:"放手",ASRTO:"好的"}
  //{ID:27,keyword:"命令词",ASR:"放下手",ASRTO:"好的"}
  //{ID:28,keyword:"命令词",ASR:"上身启动",ASRTO:""}
  //{ID:29,keyword:"命令词",ASR:"上身复位",ASRTO:""}
  //{ID:30,keyword:"命令词",ASR:"半身启动",ASRTO:""}
  //{ID:31,keyword:"命令词",ASR:"半身复位",ASRTO:""}
  //{ID:32,keyword:"命令词",ASR:"语音控制开启",ASRTO:"语音控制已开启"}
  //{ID:33,keyword:"命令词",ASR:"语音控制关闭",ASRTO:"语音控制已关闭"}
  //{ID:34,keyword:"命令词",ASR:"给我们打个招呼吧",ASRTO:"大家好呀"}
  //{ID:35,keyword:"命令词",ASR:"打招呼",ASRTO:"大家好呀"}
  //{ID:36,keyword:"命令词",ASR:"跳个舞吧",ASRTO:"好呀"}
  //{ID:37,keyword:"命令词",ASR:"表演一下",ASRTO:"好呀"}
  //{ID:38,keyword:"命令词",ASR:"跳个舞",ASRTO:"好呀"}
  //{ID:39,keyword:"命令词",ASR:"停",ASRTO:"好的"}
  //{ID:40,keyword:"命令词",ASR:"停止",ASRTO:"好的"}
}

/*描述该功能...
*/
void voice1_usart1(){
  set_state_enter_wakeup(60000);
  if((snid) == 9999){
    Serial1.print(0);
  }
  if((snid) == 9998){
    Serial1.print(0);
  }
  if((snid) == 9997){
    Serial1.print(0);
  }
  if((snid) == 9996){
    Serial1.print(0);
  }
  if((snid) == 9996){
    Serial1.print(0);
  }
  if((snid) == 28){
    Serial1.print(1);
  }
  if((snid) == 30){
    Serial1.print(1);
  }
  // 起身
  if((snid) == 6){
    Serial1.print(1);
  }
  // 起身
  if((snid) == 10){
    Serial1.print(1);
  }
  if((snid) == 34){
    Serial1.print(2);
  }
  if((snid) == 35){
    Serial1.print(3);
  }
  if((snid) == 5){
    Serial1.print(4);
  }
  if((snid) == 11){
    Serial1.print(4);
  }
  if((snid) == 29){
    Serial1.print(4);
  }
  if((snid) == 31){
    Serial1.print(4);
  }
}

void hardware_init(){
  vol_set(7);
  vTaskDelete(NULL);
}

void setup()
{
  usart_init();
  voice_set();
}
