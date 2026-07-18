#include <ESP32Servo.h>


#define SERVO_PIN   5
#define MAX_WIDTH   2500
#define MIN_WIDTH   500

// 定义 servo 对象
Servo my_servo;

void setup() {
  // 分配硬件定时器
  ESP32PWM::allocateTimer(0);
  // 设置频率
  my_servo.setPeriodHertz(50);
  // 关联 servo 对象与 GPIO 引脚，设置脉宽范围
  my_servo.attach(SERVO_PIN, MIN_WIDTH, MAX_WIDTH);
}


void loop() {
  
  //my_servo.write(180);
  //delay(1000);

  my_servo.write(0);
  delay(1000);

  my_servo.write(90);
  delay(1000);
}
