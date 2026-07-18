/*
  该程序作用是使用 LEDC 外设控制舵机
  在线文档：https://docs.geeksman.com/esp32/Arduino/17.esp32-arduino-servo.html
*/
#define FREQ        50
#define CHANNEL     0
#define RESOLUTION  8
#define SERVO       13


int calculatePWM(int degree) {
  
  int min_width = 0.5 / 20 * pow(2, RESOLUTION);
  int max_width = 2.5 / 20 * pow(2, RESOLUTION);
   
  return (max_width - min_width) * degree / 180 + min_width;
}

void setup() {
  // 建立 LEDC 通道
  ledcSetup(CHANNEL, FREQ, RESOLUTION);
  // 关联 GPIO 口与 LEDC 通道
  ledcAttachPin(SERVO, CHANNEL);
}


void loop() {
  for (int i = 0;i<=180; i+=10) {
    // 输出 PWM，设置占空比
    ledcWrite(CHANNEL, calculatePWM(i));
    delay(500);
    }
}
