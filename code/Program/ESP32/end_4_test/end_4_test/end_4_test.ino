#include <U8g2lib.h>
#include <Wire.h>
#include <ESP32Servo.h>
#include <PubSubClient.h>
#include <WiFi.h>

// OLED显示屏对象
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
#define BUZZER_PIN 23  // 定义蜂鸣器连接到D23引脚

// 距离变量
volatile float distanceLeft;
volatile float distanceRight;

// 新增：四个超声波传感器数据变量
int frontLeftDistance = 0;
int frontDistance = 0;
int frontRightDistance = 0;
int backDistance = 0;

// 定义最小安全距离阈值（单位：厘米）
const float MIN_SAFE_DISTANCE = 35.0;

// 超声波测距函数
float checkDistance(int trigPin, int echoPin) {
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);
    return pulseIn(echoPin, HIGH) / 58.00; // 返回距离（单位：厘米）
}

// 显示距离信息
void displayDistances() {
    u8g2.setFont(u8g2_font_ncenR10_tf);
    u8g2.setFontPosTop();
    u8g2.setCursor(0, 0);
    u8g2.print("Distance(cm)");
    u8g2.setCursor(0, 20);
    u8g2.print("L:" + String(distanceLeft));
    u8g2.setCursor(65, 20);
    u8g2.print("R:" + String(distanceRight));
    
    // 新增：显示四个超声波数据
    u8g2.setCursor(0, 40);
    u8g2.print("FL:" + String(frontLeftDistance));
    u8g2.setCursor(40, 40);
    u8g2.print("F:" + String(frontDistance));
    u8g2.setCursor(80, 40);
    u8g2.print("FR:" + String(frontRightDistance));
    
    u8g2.setCursor(0, 55);
    u8g2.print("B:" + String(backDistance));
}

// 显示STOP
void displayStop() {
    u8g2.setFont(u8g2_font_ncenR10_tf);
    u8g2.setFontPosTop();
    u8g2.setCursor(45, 40); // 调整位置到右侧
    u8g2.print("STOP");
}

// 显示START
void displayStart() {
    u8g2.setFont(u8g2_font_ncenR10_tf);
    u8g2.setFontPosTop();
    u8g2.setCursor(40, 40); // 调整位置到右侧
    u8g2.print("START");
}

// 修改半身运动状态控制
enum HalfBodyState {
    HALFBODY_IDLE,
    HALFBODY_MOVING  // 新状态：同时运动
};
HalfBodyState halfBodyState = HALFBODY_IDLE;
unsigned long halfBodyStartTime = 0;
const long HALFBODY_MOVE_DURATION = 3500; // 运动持续时间2秒
bool halfBodyAction = false; // false表示复位，true表示起身

// 舵机对象
Servo servo_0;
Servo servo_1;
Servo servo_2;
Servo servo_3;
Servo servo_4;
Servo servo_5;
Servo servo_6;  // 新增六号舵机
// 新增：GPIO5和GPIO15的舵机
Servo servo_gpio5;
Servo servo_gpio15;

// MQTT 配置
const char *mqtt_broker = "mixio.mixly.cn";
const char *mqtt_username = "1593019617@qq.com";
const char *mqtt_password = "45ff8cd983fd9050dc8ad75f50d9a175";
const int mqtt_port = 1883;
const String project = "WiFi控制";

// WiFi 客户端和 MQTT 客户端
WiFiClient espClient;
PubSubClient client(espClient);

// WiFi配置（新增人体跟踪MQTT）
const char* human_tracking_ssid = "MTCPC";
const char* human_tracking_password = "mt12345mt";
WiFiClient humanTrackingClient;
PubSubClient humanTrackingMqttClient(humanTrackingClient);

// EMQX服务器配置（新增人体跟踪MQTT）
const char* human_tracking_mqtt_server = "192.168.13.225";
const int human_tracking_mqtt_port = 1883;
const char* human_tracking_mqtt_user = "sy";
const char* human_tracking_mqtt_password = "123";

// MQTT主题（新增人体跟踪）
const char* human_tracking_topic = "human_tracking_control";
const char* human_tracking_status_topic = "human_tracking_status";
const char* human_tracking_command_topic = "human_tracking/command";  // 接收人体跟踪控制指令

// 新增：人体跟踪控制标志
bool humanTrackingEnabled = false;
bool humanTrackingActive = false;
unsigned long lastHumanTrackingTime = 0;
const unsigned long HUMAN_TRACKING_TIMEOUT = 1000; // 1秒超时
char humanTrackingCommand = 0;

// 舵机角度变量
float servo0_angle = 0;
float servo1_angle = 0;
float servo2_angle = 0;
float current_servo0_angle = 0;
float current_servo1_angle = 0;
float current_servo2_angle = 0;
float servo3_angle = 0;
float servo4_angle = 0;
float current_servo3_angle = 0;
float current_servo4_angle = 0;
float servo5_angle = 0;
float current_servo5_angle = 0; // 修正错误
float servo6_angle = 0;      // 新增六号舵机角度
float current_servo6_angle = 0; // 新增六号舵机当前角度
// 新增：GPIO5和GPIO15舵机角度变量
float servo_gpio5_angle = 0;
float servo_gpio15_angle = 0;
float current_servo_gpio5_angle = 0;
float current_servo_gpio15_angle = 0;

// 舵机角度限制
const int servo0_min_angle = 28;
const int servo0_max_angle = 82;
const int servo1_min_angle = 36;
const int servo1_max_angle = 90;
const int servo2_min_angle = 35;
const int servo2_max_angle = 93;

const int servo3_min_angle = 40;
const int servo3_max_angle = 144;
const int servo4_min_angle = 20;
const int servo4_max_angle = 124;

const int servo5_min_angle = 14;
const int servo5_max_angle = 154;
const int servo6_min_angle = 36;
const int servo6_max_angle = 176;

// 新增：GPIO5和GPIO15舵机角度限制
const int servo_gpio5_min_angle = 0;
const int servo_gpio5_max_angle = 180;
const int servo_gpio15_min_angle = 0;
const int servo_gpio15_max_angle = 180;

// 改进的PID控制参数
const float Kp = 0.5;   //比例
const float Ki = 0.01;  //积分
const float Kd = 0.1;   //微分

// 新增：舵机3/4/5/6专用参数
const float Kp_34 = 8.0;
const float Kp_56 = 5.0;
const float maxStep_3456 = 1.5;

const float maxStep = 0.8;
const float minStep = 0.1;

// 新增：GPIO5和GPIO15舵机专门的速度参数
const float maxStep_gpio = 4;  // GPIO舵机的最大步长，设为2.5比原来的0.8快很多
const float Kp_gpio = 3;       // GPIO舵机的比例系数，增加响应速度

// PID误差变量
float error0 = 0, error1 = 0, error2 = 0, error3 = 0, error4 = 0, error5 = 0, error6 = 0;
float prev_error0 = 0, prev_error1 = 0, prev_error2 = 0, prev_error3 = 0, prev_error4 = 0, prev_error5 = 0, prev_error6 = 0;
float integral0 = 0, integral1 = 0, integral2 = 0, integral3 = 0, integral4 = 0, integral5 = 0, integral6 = 0;
// 新增：GPIO5和GPIO15舵机PID误差变量
float error_gpio5 = 0, error_gpio15 = 0;
float prev_error_gpio5 = 0, prev_error_gpio15 = 0;
float integral_gpio5 = 0, integral_gpio15 = 0;

// 时间控制变量
unsigned long previousMillis = 0;
const long interval = 15;

// 更新标志
bool update_servo0 = false;
bool update_servo1 = false;
bool update_servo2 = false;
bool update_servo3 = false;
bool update_servo4 = false;
bool update_servo5 = false;
bool update_servo6 = false;
// 新增：GPIO5和GPIO15舵机更新标志
bool update_servo_gpio5 = false;
bool update_servo_gpio15 = false;

// 按钮主题
const char *button_topic = "button";
const char *button1_topic = "button1";
const char *button2_topic = "button2";
const char *button3_topic = "button3";
const char *button4_topic = "button4";
const char *button5_topic = "button5"; // 新增按钮5主题
const char *button6_topic = "button6"; // 新增按钮6主题
const char *button7_topic = "button7"; // 新增按钮7主题
const char *button8_topic = "button8"; // 新增按钮8主题（语音控制开关）
const char *button9_topic = "button9"; // 新增按钮9主题
const char *button10_topic = "button10"; // 新增按钮10主题
const char *button11_topic = "button11"; // 新增按钮11主题
const char *button12_topic = "button12"; // 新增按钮12主题
const char *button13_topic = "button13"; // 新增按钮13主题（第三关节起身）
const char *button14_topic = "button14"; // 新增按钮14主题（第三关节复位）
const char *button15_topic = "button15"; // 新增按钮13主题（半身起身）
const char *button16_topic = "button16"; // 新增按钮14主题（半身复位）
const char *button17_topic = "button17"; // 新增按钮17主题

// 手柄主题
const char *body_topic = "body";

// 控制器主题
const char *controller_topic = "controller";

// 手柄控制主题
const char *move_topic = "move";
const String full_topic = String(mqtt_username) + "/" + project + "/" + move_topic;

// 定义舵机初始角度和起身角度
const int servo0_initial_angle = 82;
const int servo1_initial_angle = 90;
const int servo2_initial_angle = 35;
const int servo3_initial_angle = 144;
const int servo4_initial_angle = 20;
const int servo5_initial_angle = 154;
const int servo6_initial_angle = 36;

const int servo0_stand_angle = 28;
const int servo1_stand_angle = 36;
const int servo2_stand_angle = 93;
const int servo3_stand_angle = 40;
const int servo4_stand_angle = 124;
const int servo5_stand_angle = 44;
const int servo6_stand_angle = 146;

const int servo5_up_angle =89;
const int servo6_up_angle =101;

const int servo3_half_angle =80;
const int servo4_half_angle =84;
const int servo5_half_angle =14;
const int servo6_half_angle =176;

// 新增：GPIO5和GPIO15舵机角度定义
const int servo_gpio5_initial_angle = 0;   // 初始位置
const int servo_gpio15_initial_angle = 0;  // 初始位置
const int servo_gpio5_stand_angle = 60;    // 起身时旋转90度
const int servo_gpio15_stand_angle = 60;   // 起身时旋转90度

// 用于存储串口接收到的数据
String serialData = "";

// 复位状态机
bool emergencyReset = false; // 新增：紧急复位标志
bool safetyTriggered = false; // 新增：安全距离触发标志

// 起身状态控制
enum StandupState {
    STANDUP_IDLE,
    STANDUP_START_GPIO,  // 新增：先运行GPIO舵机
    STANDUP_START,  // 然后运行其他舵机
    STANDUP_PAUSED  // 新增：暂停状态
};
StandupState standupState = STANDUP_IDLE;

// 新增：暂停计时变量
unsigned long pauseStartTime = 0;
const long pauseDuration = 5000; // 暂停5秒

// 安全检测计数器 - 优化为1次检测即触发
int unsafeCount = 0;
const int UNSAFE_THRESHOLD = 1; // 优化：连续1次不安全即触发

// 新增：串口控制变量
char currentCommand = 0;
unsigned long commandStartTime = 0;
const unsigned long COMMAND_DURATION = 3000; // 3秒持续时间

// 新增：超声波数据接收控制
bool ultrasonicDataReceiving = false; // 是否接收超声波数据
String serial2Data = ""; // 存储从串口2接收的数据

// 新增：语音控制开关状态
bool voiceControlEnabled = false; // 语音控制功能开关

// 新增：人体跟踪开关状态
bool humanTrackingButtonState = false; // false 表示关闭，true 表示打开

// 新增：动作队列状态机
enum ActionQueueState {
    ACTION_IDLE,
    ACTION_RESETTING,       // 正在复位
    ACTION_WAITING,         // 等待复位完成
    ACTION_EXECUTING_HALF,  // 执行半身动作
    ACTION_EXECUTING_UPPER, // 执行上身动作
    ACTION_RESETTING_FOR_STANDUP, // 新增：为起身而复位
    ACTION_RESETTING_FOR_UPPER,   // 新增：为上身启动而先复位半身
    ACTION_WAITING_FOR_UPPER_RESET,  // 新增：等待上身复位完成
    ACTION_RESETTING_UPPER_FOR_STANDUP, // 新增：上身复位完成后进行整体复位
    ACTION_UPPER_BODY_RESETTING  // 新增：上身复位状态
};
ActionQueueState actionQueueState = ACTION_IDLE;

// 新增：记录最后触发的按钮
int lastTriggeredButton = 0;

// 新增：半身状态标志
bool halfBodyActivated = false;

// 新增：上身状态标志
bool upperBodyActivated = false;

// 新增：起身完成标志
bool standupCompleted = false;

// 新增：上身复位完成检查变量
bool upperBodyResetComplete = false;

// 新增：动作执行完成标志位（根据您的需求修改）
bool fullBodyStandupCompleted = false;    // 整体起身完成标志 - 如果已完成，忽略相同指令
bool upperBodyStandupCompleted = false;   // 上身启动完成标志 - 如果已完成，忽略相同指令
bool halfBodyStandupCompleted = false;    // 半身启动完成标志 - 如果已完成，忽略相同指令

// 新增：GPIO5和GPIO15舵机控制函数
void controlGpioServos(bool isStandup) {
    if (isStandup) {
        // 起身动作：旋转90度
        servo_gpio5_angle = servo_gpio5_stand_angle;
        servo_gpio15_angle = servo_gpio15_stand_angle;
    } else {
        // 复位动作：回到初始位置
        servo_gpio5_angle = servo_gpio5_initial_angle;
        servo_gpio15_angle = servo_gpio15_initial_angle;
    }
    update_servo_gpio5 = true;
    update_servo_gpio15 = true;
}

// 检查上身是否复位完成
bool isUpperBodyResetComplete() {
    // 检查上身相关舵机是否复位完成（servo5, servo6, GPIO5, GPIO15）
    return (abs(current_servo5_angle - servo5_initial_angle) < 3.0 &&
            abs(current_servo6_angle - servo6_initial_angle) < 3.0 &&
            abs(current_servo_gpio5_angle - servo_gpio5_initial_angle) < 3.0 &&
            abs(current_servo_gpio15_angle - servo_gpio15_initial_angle) < 3.0);
}

// 检查全身是否复位完成
bool isFullBodyResetComplete() {
    return (abs(current_servo0_angle - servo0_initial_angle) < 3.0 &&
            abs(current_servo1_angle - servo1_initial_angle) < 3.0 &&
            abs(current_servo2_angle - servo2_initial_angle) < 3.0 &&
            abs(current_servo3_angle - servo3_initial_angle) < 3.0 &&
            abs(current_servo4_angle - servo4_initial_angle) < 3.0 &&
            abs(current_servo5_angle - servo5_initial_angle) < 3.0 &&
            abs(current_servo6_angle - servo6_initial_angle) < 3.0 &&
            abs(current_servo_gpio5_angle - servo_gpio5_initial_angle) < 3.0 &&
            abs(current_servo_gpio15_angle - servo_gpio15_initial_angle) < 3.0);
}

// 获取输出字符串的函数
String getOutputString(int value) {
    int absValue = abs(value);
    
    if (value >= 0) {
        if (absValue >= 0 && absValue < 20) return "L1";
        else if (absValue >= 20 && absValue < 40) return "L2";
        else if (absValue >= 40 && absValue < 60) return "L3";
        else if (absValue >= 60 && absValue < 80) return "L4";
        else return "L5";
    } else {
        if (absValue >= 0 && absValue < 20) return "R1";
        else if (absValue >= 20 && absValue < 40) return "R2";
        else if (absValue >= 40 && absValue < 60) return "R3";
        else if (absValue >= 60 && absValue < 80) return "R4";
        else return "R5";
    }
}

// 获取前进/后退字符串的函数
String getDirectionString(int value) {
    int absValue = abs(value);
    
    if (value >= 0) {
        if (absValue >= 0 && absValue < 20) return "G1";
        else if (absValue >= 20 && absValue < 40) return "G2";
        else if (absValue >= 40 && absValue < 60) return "G3";
        else if (absValue >= 60 && absValue < 80) return "G4";
        else return "G5";
    } else {
        if (absValue >= 0 && absValue < 20) return "B1";
        else if (absValue >= 20 && absValue < 40) return "B2";
        else if (absValue >= 40 && absValue < 60) return "B3";
        else if (absValue >= 60 && absValue < 80) return "B4";
        else return "B5";
    }
}

// 检查特殊手势的函数
String checkSpecialGestures(int frontValue, int backValue) {
    // 1. 如果两个值都在80-100之间
    if (frontValue >= 80 && frontValue <= 100 && 
        backValue >= 80 && backValue <= 100) {
        return "TL";
    }
    
    // 2. 如果第一个值在80-100，第二个值在-80到-100
    if (frontValue >= 80 && frontValue <= 100 && 
        backValue <= -80 && backValue >= -100) {
        return "TR";
    }
    
    // 3. 如果第一个值在-80到-100，第二个值在80-100
    if (frontValue <= -80 && frontValue >= -100 && 
        backValue >= 80 && backValue <= 100) {
        return "TL";
    }
    
    // 4. 如果两个值都在-80到-100之间
    if (frontValue <= -80 && frontValue >= -100 && 
        backValue <= -80 && backValue >= -100) {
        return "TR";
    }
    
    // 没有匹配的特殊手势
    return "";
}

// 用于记录开关状态
bool button6_state = false; // false 表示关闭，true 表示打开
bool button7_state = false; // false 表示关闭，true 表示打开
bool button8_state = false; // false 表示关闭，true 表示打开（语音控制开关）

// 超声波数据发送控制变量
unsigned long lastUltrasonicSendTime = 0;
const unsigned long ULTRASONIC_SEND_INTERVAL = 10; // 200ms发送间隔

// 新增：控制move主题是否允许发送的标志
bool moveTopicAllowed = true; // 初始允许发送move主题

// 新增：解析超声波数据函数
void parseUltrasonicData(String data) {
    data.trim();
    
    // 检查数据格式是否正确（应该有三个逗号分隔四个值）
    int commaCount = 0;
    for (int i = 0; i < data.length(); i++) {
        if (data[i] == ',') commaCount++;
    }
    
    if (commaCount == 3) {
        int firstComma = data.indexOf(',');
        int secondComma = data.indexOf(',', firstComma + 1);
        int thirdComma = data.indexOf(',', secondComma + 1);
        
        frontLeftDistance = data.substring(0, firstComma).toInt();
        frontDistance = data.substring(firstComma + 1, secondComma).toInt();
        frontRightDistance = data.substring(secondComma + 1, thirdComma).toInt();
        backDistance = data.substring(thirdComma + 1).toInt();
        
        // 组合六个超声波数据并发送（确保六个数据一组换行）
        String combinedData = String(frontLeftDistance) + "," + 
                              String(frontDistance) + "," + 
                              String(frontRightDistance) + "," + 
                              String(backDistance) + "," + 
                              String((int)distanceLeft) + "," + 
                              String((int)distanceRight);
        
        Serial2.println(combinedData); // 使用println确保每个数据组单独一行
    }
}

// 人体跟踪MQTT消息回调函数
void humanTrackingCallback(char* topic, byte* payload, unsigned int length) {
    String data = "";
    for (int i = 0; i < length; i++) {
        data += (char)payload[i];
    }
     
    
    String command = "S";
    
    if (data == "forward") {
        command = "G1";
        humanTrackingCommand = 'G';
    } else if (data == "backward") {
        command = "B1";
        humanTrackingCommand = 'B';
    } else if (data == "left") {
        command = "L1";
        humanTrackingCommand = 'L';
    } else if (data == "right") {
        command = "R1";
        humanTrackingCommand = 'R';
    } else if (data == "stop") {
        command = "S";
        humanTrackingCommand = 'S';
    } else {
        // 未知指令，尝试直接发送
        command = data;
    }
    
    // 发送到串口2
    Serial2.println(command);
    
    lastHumanTrackingTime = millis();
}

void callback(char *topic, byte *payload, unsigned int length) {
    String data = "";
    for (int i = 0; i < length; i++) {
        data += (char)payload[i];
    }

    // 安全距离检测只在起身过程中开启
    // 非起身状态下忽略安全距离检测
    if (standupState != STANDUP_IDLE && standupState != STANDUP_START_GPIO) {
        if (distanceLeft < MIN_SAFE_DISTANCE || distanceRight < MIN_SAFE_DISTANCE) {
            if (String(topic) == String(mqtt_username) + "/" + project + "/" + button_topic ||
                String(topic) == String(mqtt_username) + "/" + project + "/" + button1_topic ||
                String(topic) == String(mqtt_username) + "/" + project + "/" + button2_topic ||
                String(topic) == String(mqtt_username) + "/" + project + "/" + button3_topic ||
                String(topic) == String(mqtt_username) + "/" + project + "/" + button4_topic ||
                String(topic) == String(mqtt_username) + "/" + project + "/" + button5_topic ||
                String(topic) == String(mqtt_username) + "/" + project + "/" + button6_topic || // 添加button6
                String(topic) == String(mqtt_username) + "/" + project + "/" + button7_topic || // 添加button7
                String(topic) == String(mqtt_username) + "/" + project + "/" + button8_topic || // 添加button8
                String(topic) == String(mqtt_username) + "/" + project + "/" + button9_topic || // 添加button9
                String(topic) == String(mqtt_username) + "/" + project + "/" + button10_topic || // 添加button10
                String(topic) == String(mqtt_username) + "/" + project + "/" + button11_topic || // 添加button11
                String(topic) == String(mqtt_username) + "/" + project + "/" + button12_topic || // 添加button12
                String(topic) == String(mqtt_username) + "/" + project + "/" + button13_topic || // 添加button13
                String(topic) == String(mqtt_username) + "/" + project + "/" + button14_topic || // 添加button14
                String(topic) == String(mqtt_username) + "/" + project + "/" + button15_topic || // 添加button15
                String(topic) == String(mqtt_username) + "/" + project + "/" + button16_topic || // 添加button16
                String(topic) == String(mqtt_username) + "/" + project + "/" + button17_topic || // 添加button17

                String(topic) == String(mqtt_username) + "/" + project + "/" + controller_topic ||
                String(topic) == String(mqtt_username) + "/" + project + "/" + body_topic ||
                String(topic) == full_topic) {
                return;
            }
        }
    }

    // 处理button17开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button17_topic)) {
        // 当button17按下时，从串口1发送10
        Serial.println("G");
        return;
    }

    // 处理button6开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button6_topic)) {
        // 切换开关状态
        button6_state = !button6_state;
        moveTopicAllowed = !button6_state; // 当button6开启时，禁止move主题发送
        ultrasonicDataReceiving = button6_state; // 控制超声波数据接收
        
        if (button6_state) {
            Serial.println("6"); // 开启开关，发送6
            // 清空上一次发送时间，确保立即发送
            lastUltrasonicSendTime = 0;
            shortBeep(); // 短蜂鸣提示开启
        } else {
            Serial.println("7"); // 关闭开关，发送7
            Serial2.println("S"); // 发送停止
            shortBeep(); // 短蜂鸣提示关闭
            shortBeep();
        }
        return;
    }

    // 处理button7开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button7_topic)) {
        // 切换开关状态
        button7_state = !button7_state;
        
        if (button7_state) {
            Serial2.println("8"); // 开启开关，发送8到串口2
            shortBeep(); // 短蜂鸣提示开启
        } else {
            Serial2.println("9"); // 关闭开关，发送9到串口2
            shortBeep(); // 短蜂鸣提示关闭
            shortBeep();
        }
        return;
    }

    // 处理button8开关（语音控制开关）
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button8_topic)) {
        // 切换开关状态
        button8_state = !button8_state;
        voiceControlEnabled = button8_state; // 设置语音控制状态
        
        if (button8_state) {
            Serial.println("A"); // 开启语音控制，发送A
            shortBeep(); // 短蜂鸣提示开启
        } else {
            Serial.println("B"); // 关闭语音控制，发送B
            shortBeep(); // 短蜂鸣提示关闭
            shortBeep();
        }
        return;
    }

    // 处理button9开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button9_topic)) {
        Serial.println("3"); // 发送3到串口1
        return;
    }

    // 处理button10开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button10_topic)) {
        Serial.println("4"); // 发送4到串口1
        return;
    }

    // 处理button11开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button11_topic)) {
        Serial.println("8"); // 发送8到串口1
        return;
    }

    // 处理button12开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button12_topic)) {
        Serial.println("9"); // 发送9到串口1
        return;
    }

    // 处理button13开关（第三关节起身）- 修改：如果已经完成，直接忽略
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button13_topic)) {
        
        // 检查上身启动是否已经完成，如果已完成，直接忽略指令
        if (upperBodyStandupCompleted) {
            // 忽略指令，不执行任何操作
            return;
        }
        
        // 检查是否处于半身启动状态
        if (halfBodyActivated || actionQueueState == ACTION_EXECUTING_HALF) {
            // 如果处于半身启动状态，先执行半身复位，然后执行上身启动
            
            // 设置动作队列状态为复位中（为了上身启动）
            actionQueueState = ACTION_RESETTING_FOR_UPPER;
            
            // 执行半身复位
            Serial.println("9");  // 发送数据让机械臂复位
            
            // 设置半身相关舵机为初始角度
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;
            
            // 启动半身运动状态机进行复位
            halfBodyState = HALFBODY_MOVING;
            halfBodyStartTime = millis();
            halfBodyAction = false; // 标记为复位动作
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            // 设置lastTriggeredButton为13，表示半身复位后要执行上身启动
            lastTriggeredButton = 13;
            
            // 清除半身激活标志
            halfBodyActivated = false;
            halfBodyStandupCompleted = false; // 清除半身完成标志
            
            return;
        } else {
            // 原来的逻辑：如果不在半身启动状态，直接执行上身启动
            actionQueueState = ACTION_RESETTING;
            
            // 发送9让机械臂复位
            Serial.println("9");
            
            // 设置所有舵机为初始角度
            servo0_angle = servo0_initial_angle;
            servo1_angle = servo1_initial_angle;
            servo2_angle = servo2_initial_angle;
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;

            update_servo0 = true;
            update_servo1 = true;
            update_servo2 = true;
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;

            // 设置GPIO5和GPIO15舵机为初始位置
            controlGpioServos(false);

            // 重置状态
            standupState = STANDUP_IDLE;
            safetyTriggered = false;
            emergencyReset = false;
            
            // 标记为上身动作
            lastTriggeredButton = 13;
            upperBodyActivated = true;  // 标记上身已激活
            halfBodyActivated = false;  // 清除半身标志
            
            // 清除其他完成标志
            fullBodyStandupCompleted = false;
            halfBodyStandupCompleted = false;
            
            return;
        }
    }


    // 处理button14开关（第三关节复位）- 修改：先复位上身，再发送9复位机械臂
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button14_topic)) {
        // 先复位上身相关舵机
        servo5_angle = servo5_initial_angle;
        servo6_angle = servo6_initial_angle;
        update_servo5 = true;
        update_servo6 = true;
        
        // 控制GPIO5和GPIO15舵机复位
        controlGpioServos(false);
        
        // 设置状态为上身复位中
        actionQueueState = ACTION_UPPER_BODY_RESETTING;
        
        // 清除完成标志
        upperBodyStandupCompleted = false;
        upperBodyActivated = false;
        
        return;
    }

    // 处理button15开关（半身起身）- 修改：如果已经完成，直接忽略
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button15_topic)) {
        
        // 检查半身启动是否已经完成，如果已完成，直接忽略指令
        if (halfBodyStandupCompleted) {
            // 忽略指令，不执行任何操作
            return;
        }
        
        // 设置动作队列状态为复位中
        actionQueueState = ACTION_RESETTING;
        
        // 发送9让机械臂复位
        Serial.println("9");
        
        // 设置所有舵机为初始角度
        servo0_angle = servo0_initial_angle;
        servo1_angle = servo1_initial_angle;
        servo2_angle = servo2_initial_angle;
        servo3_angle = servo3_initial_angle;
        servo4_angle = servo4_initial_angle;
        servo5_angle = servo5_initial_angle;
        servo6_angle = servo6_initial_angle;

        update_servo0 = true;
        update_servo1 = true;
        update_servo2 = true;
        update_servo3 = true;
        update_servo4 = true;
        update_servo5 = true;
        update_servo6 = true;

        // 设置GPIO5和GPIO15舵机为初始位置
        controlGpioServos(false);

        // 重置状态
        standupState = STANDUP_IDLE;
        safetyTriggered = false;
        emergencyReset = false;
        
        // 标记为半身动作
        lastTriggeredButton = 15;
        halfBodyActivated = true;  // 标记半身已激活
        upperBodyActivated = false;  // 清除上身标志
        
        // 清除其他完成标志
        fullBodyStandupCompleted = false;
        upperBodyStandupCompleted = false;
        
        return;
    }

    // 处理button16开关（半身复位）
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button16_topic)) {
        Serial.println("9");  //发送数据先让机械臂复位
        // 设置所有舵机目标角度
        servo3_angle = servo3_initial_angle;
        servo4_angle = servo4_initial_angle;
        servo5_angle = servo5_initial_angle;
        servo6_angle = servo6_initial_angle;
        
        update_servo3 = true;
        update_servo4 = true;
        update_servo5 = true;
        update_servo6 = true;
        
        // 启动半身运动状态机
        halfBodyState = HALFBODY_MOVING;
        halfBodyStartTime = millis();
        halfBodyAction = false; // 标记为复位动作
        
        // 新增：控制GPIO5和GPIO15舵机复位
        controlGpioServos(false);
        
        halfBodyActivated = false;  // 清除半身激活标志
        halfBodyStandupCompleted = false; // 清除半身完成标志
        
        return;
    }

    // 处理button4开关（起身命令）- 修改：如果已经完成，直接忽略
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button4_topic)) {
        
        // 检查整体起身是否已经完成，如果已完成，直接忽略指令
        if (fullBodyStandupCompleted) {
            // 忽略指令，不执行任何操作
            return;
        }
        
        // 检查是否正在执行半身或上身动作
        if (upperBodyActivated || actionQueueState == ACTION_EXECUTING_UPPER) {
            // 如果处于上身启动状态，先复位上身，等待复位完成后再进行整体起身
            
            // 设置上身相关舵机为初始角度
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            update_servo5 = true;
            update_servo6 = true;
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            // 设置状态为等待上身复位完成
            actionQueueState = ACTION_WAITING_FOR_UPPER_RESET;
            lastTriggeredButton = 4; // 记录按钮4被触发
            
            // 清除上身激活标志
            upperBodyActivated = false;
            upperBodyStandupCompleted = false; // 清除上身完成标志
            
            return;
        } else if (halfBodyActivated || actionQueueState == ACTION_EXECUTING_HALF) {
            // 如果处于半身启动状态，先执行半身复位，再执行整体复位，最后起身
            Serial.println("9");  //发送数据先让机械臂半身复位
            
            // 设置半身相关舵机为初始角度
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;
            
            // 启动半身运动状态机
            halfBodyState = HALFBODY_MOVING;
            halfBodyStartTime = millis();
            halfBodyAction = false; // 标记为复位动作
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            // 标记半身复位完成，等待整体复位
            halfBodyActivated = false;  // 清除半身激活标志
            halfBodyStandupCompleted = false; // 清除半身完成标志
            actionQueueState = ACTION_RESETTING_FOR_STANDUP;
            
        } else {
            // 不在执行动作，直接进入GPIO舵机运动阶段
            standupState = STANDUP_START_GPIO;

            // 先设置GPIO5和GPIO15舵机为站立角度
            controlGpioServos(true);
            
            // 清除完成标志
            fullBodyStandupCompleted = false;
        }
        return;
    }

    // 处理move主题前检查是否允许发送
    if (String(topic) == full_topic) {
        // 如果不允许发送move主题，直接发送停止指令并返回
        if (!moveTopicAllowed) {
            return;
        }
        
        int commaIndex = data.indexOf(',');
        if (commaIndex != -1) {
            String value1 = data.substring(0, commaIndex);
            String value2 = data.substring(commaIndex + 1);

            int value1Int = -value1.toInt();
            int value2Int = value2.toInt(); // 第二个值不取反

            if (value1Int == 0 && value2Int == 0) {
                Serial2.println("S"); // 发送stop
                return;
            }

            int frontValue = value2Int; // 逗号前面的值（原始第二个值）
            int backValue = value1Int;   // 逗号后面的值（原始第一个值取反）

            String specialGesture = checkSpecialGestures(frontValue, backValue);
            if (specialGesture != "") {
                Serial2.println(specialGesture);
                return; // 特殊手势匹配，直接返回不再处理其他逻辑
            }

            if (abs(frontValue) > abs(backValue)) {
                Serial2.println(getDirectionString(frontValue));
            } else {
                Serial2.println(getOutputString(backValue));
            }
        } else {
            Serial2.println(data);
        }
        return; // 处理完move主题后返回
    }

    if (String(topic) == String(mqtt_username) + "/" + project + "/controller") {
        int commaIndex = data.indexOf(',');
        if (commaIndex != -1) {
            int parsed_left_right = data.substring(0, commaIndex).toInt();
            parsed_left_right = -parsed_left_right;

            float new_servo0_angle = current_servo0_angle + parsed_left_right;
            float new_servo1_angle = current_servo1_angle + parsed_left_right;
            float new_servo2_angle = current_servo2_angle - parsed_left_right;

            new_servo0_angle = constrain(new_servo0_angle, servo0_min_angle, servo0_max_angle);
            new_servo1_angle = constrain(new_servo1_angle, servo1_min_angle, servo1_max_angle);
            new_servo2_angle = constrain(new_servo2_angle, servo2_min_angle, servo2_max_angle);

            servo0_angle = new_servo0_angle;
            servo1_angle = new_servo1_angle;
            servo2_angle = new_servo2_angle;

            update_servo0 = true;
            update_servo1 = true;
            update_servo2 = true;

            int parsed_up_down = data.substring(commaIndex + 1).toInt();
            parsed_up_down = -parsed_up_down;

            float new_servo3_angle = current_servo3_angle + parsed_up_down;
            float new_servo4_angle = current_servo4_angle - parsed_up_down;

            new_servo3_angle = constrain(new_servo3_angle, servo3_min_angle, servo3_max_angle);
            new_servo4_angle = constrain(new_servo4_angle, servo4_min_angle, servo4_max_angle);

            servo3_angle = new_servo3_angle;
            servo4_angle = new_servo4_angle;

            update_servo3 = true;
            update_servo4 = true;
        }
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button_topic) {
        Serial.println("0");
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button1_topic) {
        Serial.println("1");
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button2_topic) {
        Serial.println("2");
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button3_topic) {
        if (halfBodyActivated) {
            // 如果半身已激活，则执行半身复位
            Serial.println("9");
            // 设置半身相关舵机为初始角度
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;
            
            // 启动半身运动状态机
            halfBodyState = HALFBODY_MOVING;
            halfBodyStartTime = millis();
            halfBodyAction = false;
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            halfBodyActivated = false;  // 清除标志
            halfBodyStandupCompleted = false; // 清除完成标志
        } else if (upperBodyActivated) {
            // 如果上身已激活，则执行上身复位
            // 先复位上身相关舵机
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            update_servo5 = true;
            update_servo6 = true;
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            // 设置状态为上身复位中
            actionQueueState = ACTION_UPPER_BODY_RESETTING;
            
            upperBodyActivated = false;  // 清除标志
            upperBodyStandupCompleted = false; // 清除完成标志
        } else {
            // 原来的整体复位逻辑
            Serial.println("9");
            delay(1000);
            servo0_angle = servo0_initial_angle;
            servo1_angle = servo1_initial_angle;
            servo2_angle = servo2_initial_angle;
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;

            update_servo0 = true;
            update_servo1 = true;
            update_servo2 = true;
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;

            controlGpioServos(false);

            standupState = STANDUP_IDLE;
            safetyTriggered = false;
            emergencyReset = false;
            
            // 清除所有完成标志
            fullBodyStandupCompleted = false;
            upperBodyStandupCompleted = false;
            halfBodyStandupCompleted = false;
        }
        return;
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button5_topic) {
        Serial.println("5");
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + body_topic) {
        int parsed_servo_angle = data.toInt();
        parsed_servo_angle = -parsed_servo_angle;

        float new_servo5_angle = current_servo5_angle + parsed_servo_angle;
        new_servo5_angle = constrain(new_servo5_angle, servo5_min_angle, servo5_max_angle);

        float new_servo6_angle = servo6_max_angle - (new_servo5_angle - servo5_min_angle);

        servo5_angle = new_servo5_angle;
        servo6_angle = new_servo6_angle;

        update_servo5 = true;
        update_servo6 = true;
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + controller_topic) {
    }
}

void resetServos() {
    servo0_angle = servo0_initial_angle;
    servo1_angle = servo1_initial_angle;
    servo2_angle = servo2_initial_angle;
    servo3_angle = servo3_initial_angle;
    servo4_angle = servo4_initial_angle;
    servo5_angle = servo5_initial_angle;
    servo6_angle = servo6_initial_angle;

    current_servo0_angle = servo0_initial_angle;
    current_servo1_angle = servo1_initial_angle;
    current_servo2_angle = servo2_initial_angle;
    current_servo3_angle = servo3_initial_angle;
    current_servo4_angle = servo4_initial_angle;
    current_servo5_angle = servo5_initial_angle;
    current_servo6_angle = servo6_initial_angle;

    update_servo0 = true;
    update_servo1 = true;
    update_servo2 = true;
    update_servo3 = true;
    update_servo4 = true;
    update_servo5 = true;
    update_servo6 = true;

    // 新增：复位GPIO5和GPIO15舵机
    servo_gpio5_angle = servo_gpio5_initial_angle;
    servo_gpio15_angle = servo_gpio15_initial_angle;
    current_servo_gpio5_angle = servo_gpio5_initial_angle;
    current_servo_gpio15_angle = servo_gpio15_initial_angle;
    update_servo_gpio5 = true;
    update_servo_gpio15 = true;
}

// 初始化人体跟踪MQTT连接
void initHumanTrackingMQTT() {

    
    // 连接WiFi
    WiFi.begin(human_tracking_ssid, human_tracking_password);
    int wifiTimeout = 0;
    while (WiFi.status() != WL_CONNECTED && wifiTimeout < 20) {
        delay(500);
        Serial.print(".");
        wifiTimeout++;
    }
    
    
    // 设置MQTT回调函数
    humanTrackingMqttClient.setServer(human_tracking_mqtt_server, human_tracking_mqtt_port);
    humanTrackingMqttClient.setCallback(humanTrackingCallback);
    
    // 连接MQTT服务器
    String client_id = "esp32-human-";
    client_id += String(WiFi.macAddress());
    
    if (humanTrackingMqttClient.connect(client_id.c_str(), human_tracking_mqtt_user, human_tracking_mqtt_password)) {
        
        // 订阅人体跟踪控制主题
        humanTrackingMqttClient.subscribe(human_tracking_command_topic);

        
        // 发布连接状态
        humanTrackingMqttClient.publish(human_tracking_status_topic, "connected");
    } else {

    }
}

void setup() {
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);
    Serial.begin(115200);
    Serial2.begin(115200, SERIAL_8N1, 16, 17);
    u8g2.setI2CAddress(0x3C * 2);
    u8g2.begin();
    distanceLeft = 0;
    distanceRight = 0;

    pinMode(2, OUTPUT);
    pinMode(4, INPUT);
    pinMode(12, OUTPUT);
    pinMode(14, INPUT);

    u8g2.enableUTF8Print();

    WiFi.begin("MTCPC", "mt12345mt");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
    }

    servo_0.attach(32);
    servo_1.attach(33);
    servo_2.attach(25);
    servo_3.attach(26);
    servo_4.attach(27);

    servo_5.attach(19);
    servo_6.attach(18);

    // 新增：初始化GPIO5和GPIO15舵机
    servo_gpio5.attach(5);
    servo_gpio15.attach(15);

    current_servo0_angle = servo0_initial_angle;
    current_servo1_angle = servo1_initial_angle;
    current_servo2_angle = servo2_initial_angle;
    current_servo3_angle = servo3_initial_angle;
    current_servo4_angle = servo4_initial_angle;
    current_servo5_angle = servo5_initial_angle;
    current_servo6_angle = servo6_initial_angle;

    // 新增：初始化GPIO5和GPIO15舵机当前角度
    current_servo_gpio5_angle = servo_gpio5_initial_angle;
    current_servo_gpio15_angle = servo_gpio15_initial_angle;

    servo_0.write(servo0_initial_angle);
    servo_1.write(servo1_initial_angle);
    servo_2.write(servo2_initial_angle);
    servo_3.write(servo3_initial_angle);
    servo_4.write(servo4_initial_angle);
    servo_5.write(servo5_initial_angle);
    servo_6.write(servo6_initial_angle);

    // 新增：初始化GPIO5和GPIO15舵机位置
    servo_gpio5.write(servo_gpio5_initial_angle);
    servo_gpio15.write(servo_gpio15_initial_angle);

    resetServos();

    emergencyReset = false;
    standupState = STANDUP_IDLE;
    unsafeCount = 0;
    button6_state = false; // 初始化按钮6状态为关闭
    button7_state = false; // 初始化按钮7状态为关闭
    button8_state = false; // 初始化按钮8状态为关闭
    voiceControlEnabled = false; // 初始化语音控制状态为关闭
    ultrasonicDataReceiving = false; // 初始化超声波数据接收状态为关闭
    lastUltrasonicSendTime = 0; // 初始化超声波发送时间
    moveTopicAllowed = true; // 初始化允许发送move主题

    // 初始化串口控制变量
    currentCommand = 0;
    commandStartTime = 0;

    // 初始化人体跟踪变量
    humanTrackingEnabled = false;
    humanTrackingActive = false;
    humanTrackingButtonState = false;
    lastHumanTrackingTime = 0;
    humanTrackingCommand = 0;

    // 初始化动作队列状态
    actionQueueState = ACTION_IDLE;
    lastTriggeredButton = 0;
    halfBodyActivated = false;
    upperBodyActivated = false;
    standupCompleted = false; // 初始化起身完成标志为false
    upperBodyResetComplete = false; // 初始化上身复位完成标志
    
    // 初始化动作完成标志位
    fullBodyStandupCompleted = false;
    upperBodyStandupCompleted = false;
    halfBodyStandupCompleted = false;

    // 初始化主MQTT连接
    client.setServer(mqtt_broker, mqtt_port);
    client.setCallback(callback);

    String client_id = "esp-client-";
    client_id += String(WiFi.macAddress());
    while (!client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
        delay(2000);
    }

    client.subscribe(String(String(mqtt_username) + "/" + project + "/controller").c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button1_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button2_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button3_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button4_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button5_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button6_topic).c_str()); // 添加button6订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button7_topic).c_str()); // 添加button7订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button8_topic).c_str()); // 添加button8订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button9_topic).c_str()); // 添加button9订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button10_topic).c_str()); // 添加button10订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button11_topic).c_str()); // 添加button11订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button12_topic).c_str()); // 添加button12订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button13_topic).c_str()); // 添加button13订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button14_topic).c_str()); // 添加button14订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button15_topic).c_str()); // 添加button15订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button16_topic).c_str()); // 添加button16订阅
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button17_topic).c_str()); // 添加button17订阅

    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + body_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + controller_topic).c_str());
    client.subscribe(full_topic.c_str());

    // 初始化人体跟踪MQTT连接
    initHumanTrackingMQTT();

    // 现在调用蜂鸣器提示音
    buzzer_on();
}

void buzzer_on() {
    digitalWrite(BUZZER_PIN, HIGH);   // 高电平触发，蜂鸣器响
    delay(500);                       // 持续500ms
    digitalWrite(BUZZER_PIN, LOW);  // 输出低电平，蜂鸣器不响
}

// 添加shortBeep函数定义
void shortBeep() {
    digitalWrite(BUZZER_PIN, HIGH);   // 高电平触发，蜂鸣器响
    delay(200);                       // 持续200ms
    digitalWrite(BUZZER_PIN, LOW);  // 输出低电平，蜂鸣器不响
}

void longBeep() {
    digitalWrite(BUZZER_PIN, HIGH);   // 高电平触发，蜂鸣器响
    delay(500);                       // 持续500ms
    digitalWrite(BUZZER_PIN, LOW);  // 输出低电平，蜂鸣器不响
}

// 修改点：修复串口接收到"4"时的逻辑
void processSerialData(String data) {
    data.trim();
    if (data == "0") {
        char topic[100];
        sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button_topic);
        if (client.connected()) {
            client.publish(topic, "0");
        } else {
        }
    } else if (data == "1") {
        char topic[100];
        sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button1_topic);
        if (client.connected()) {
            client.publish(topic, "1");
        } 
    } else if (data == "2") {
        char topic[100];
        sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button2_topic);
        if (client.connected()) {
            client.publish(topic, "2");
        } 
    } else if (data == "3") {
        char topic[100];
        sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button3_topic);
        if (client.connected()) {
            client.publish(topic, "3");
        } 
    } else if (data == "4") {
        // 检查整体起身是否已经完成，如果已完成，直接忽略指令
        if (fullBodyStandupCompleted) {
            // 忽略指令，不执行任何操作
            return;
        }
        
        // 修改：根据当前状态执行不同的复位逻辑
        if (upperBodyActivated || actionQueueState == ACTION_EXECUTING_UPPER) {
            // 如果处于上身启动状态，先复位上身，等待复位完成后再进行整体起身
            
            // 设置上身相关舵机为初始角度
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            update_servo5 = true;
            update_servo6 = true;
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            // 设置状态为等待上身复位完成
            actionQueueState = ACTION_WAITING_FOR_UPPER_RESET;
            lastTriggeredButton = 4; // 记录按钮4被触发
            
            // 清除上身激活标志
            upperBodyActivated = false;
            upperBodyStandupCompleted = false;
            
        } else if (halfBodyActivated || actionQueueState == ACTION_EXECUTING_HALF) {
            // 如果处于半身启动状态，先执行半身复位，再执行整体复位，最后起身
            Serial.println("9");  //发送数据先让机械臂半身复位
            
            // 设置半身相关舵机为初始角度
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;
            
            // 启动半身运动状态机
            halfBodyState = HALFBODY_MOVING;
            halfBodyStartTime = millis();
            halfBodyAction = false; // 标记为复位动作
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            // 标记半身复位完成，等待整体复位
            halfBodyActivated = false;  // 清除半身激活标志
            halfBodyStandupCompleted = false;
            actionQueueState = ACTION_RESETTING_FOR_STANDUP;
            
        } else {
            // 不在执行动作，直接进入GPIO舵机运动阶段
            standupState = STANDUP_START_GPIO;

            // 先设置GPIO5和GPIO15舵机为站立角度
            controlGpioServos(true);
            
            // 清除完成标志
            fullBodyStandupCompleted = false;
        }
        return;
    } else if (data == "5") {
        char topic[100];
        sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button5_topic);
        if (client.connected()) {
            client.publish(topic, "5");
        } 
    } else if (data == "6") {
        // 接收到6，开启button6开关避障功能
        button6_state = true;
        ultrasonicDataReceiving = true;
        moveTopicAllowed = false;
        lastUltrasonicSendTime = 0; // 清空上一次发送时间，确保立即发送
        shortBeep(); // 短蜂鸣提示开启
        Serial.println("6"); // 发送6到串口
    } else if (data == "7") {
        // 接收到7，关闭button6开关避障功能
        Serial2.println("S"); // 发送停止
        button6_state = false;
        ultrasonicDataReceiving = false;
        moveTopicAllowed = true;
        shortBeep(); // 短蜂鸣提示关闭
        shortBeep();
        Serial.println("7"); // 发送7到串口
    } else if (data == "8") {
        // 接收到8，发送8到串口2
        Serial2.println("8");
    } else if (data == "9") {
        // 接收到9，发送9到串口2
        Serial2.println("9");
    } else if (data == "A") {
        // 接收到A，开启语音控制功能
        voiceControlEnabled = true;
        button8_state = true;
        shortBeep(); // 短蜂鸣提示开启
    } else if (data == "B") {
        // 接收到B，关闭语音控制功能
        voiceControlEnabled = false;
        button8_state = false;
        shortBeep(); // 短蜂鸣提示关闭
        shortBeep();
    } else if (data == "C") {
        // 接收到C，发送3到串口1
        Serial.println("3");
    } else if (data == "D") {
        // 接收到D，发送4到串口1
        Serial.println("4");
    } else if (data == "E") {
        // 接收到E，发送8到串口1
        Serial.println("8");
    } else if (data == "F") {
        // 接收到F，发送9到串口1
        Serial.println("9");
    } else if (data == "G") {
        // 接收到G，开启人体跟踪功能
        humanTrackingEnabled = true;
        humanTrackingActive = true;
        humanTrackingButtonState = true;
        longBeep(); // 长蜂鸣提示开启
        
        // 发布人体跟踪状态
        if (humanTrackingMqttClient.connected()) {
            humanTrackingMqttClient.publish(human_tracking_status_topic, "tracking_active");
        }
    } else if (data == "H") {
        // 接收到H，关闭人体跟踪功能
        humanTrackingEnabled = false;
        humanTrackingActive = false;
        humanTrackingButtonState = false;
        Serial2.println("S"); // 发送停止指令
        shortBeep(); // 短蜂鸣提示关闭
        shortBeep();
        
        // 发布人体跟踪状态
        if (humanTrackingMqttClient.connected()) {
            humanTrackingMqttClient.publish(human_tracking_status_topic, "tracking_inactive");
        }
    } else if (data == "10") {
        // 检查上身启动是否已经完成，如果已完成，直接忽略指令
        if (upperBodyStandupCompleted) {
            // 忽略指令，不执行任何操作
            return;
        }
        
        // 检查是否处于半身启动状态

        if (halfBodyActivated || actionQueueState == ACTION_EXECUTING_HALF) {
            // 如果处于半身启动状态，先执行半身复位，然后执行上身启动
            
            // 设置动作队列状态为复位中（为了上身启动）
            actionQueueState = ACTION_RESETTING_FOR_UPPER;
            
            // 执行半身复位
            Serial.println("9");  // 发送数据让机械臂复位
            
            // 设置半身相关舵机为初始角度
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;
            
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;
            
            // 启动半身运动状态机进行复位
            halfBodyState = HALFBODY_MOVING;
            halfBodyStartTime = millis();
            halfBodyAction = false; // 标记为复位动作
            
            // 控制GPIO5和GPIO15舵机复位
            controlGpioServos(false);
            
            // 设置lastTriggeredButton为13，表示半身复位后要执行上身启动
            lastTriggeredButton = 13;
            
            // 清除半身激活标志
            halfBodyActivated = false;
            halfBodyStandupCompleted = false; // 清除半身完成标志
            
            // 不再发送MQTT消息，直接处理
            return;
        } else {
            // 如果不在半身启动状态，发送MQTT消息触发上身启动
            char topic[100];
            sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button13_topic);
            if (client.connected()) {
                client.publish(topic, "13");
            }
        }
        return;
    } else if (data == "11") {
        // 接收到11，触发上身复位
        // 先复位上身相关舵机
        servo5_angle = servo5_initial_angle;
        servo6_angle = servo6_initial_angle;
        update_servo5 = true;
        update_servo6 = true;
        
        // 控制GPIO5和GPIO15舵机复位
        controlGpioServos(false);
        
        // 设置状态为上身复位中
        actionQueueState = ACTION_UPPER_BODY_RESETTING;
        
        // 清除完成标志
        upperBodyStandupCompleted = false;
        upperBodyActivated = false;
        
        return;
    } else if (data == "12") {
        // 检查半身启动是否已经完成，如果已完成，直接忽略指令
        if (halfBodyStandupCompleted) {
            // 忽略指令，不执行任何操作
            return;
        }
        
        // 接收到12，触发半身起身
        char topic[100];
        sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button15_topic);
        if (client.connected()) {
            client.publish(topic, "15");
        } 
    } else if (data == "13") {
        // 接收到13，触发半身复位
        char topic[100];
        sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), button16_topic);
        if (client.connected()) {
            client.publish(topic, "16");
        }
    } else if (data == "15") {
        // 接收到15，从串口1发送10
        Serial.println("G");
        return;
    } else if (data == "a" || data == "b" || data == "c" || data == "d" || data == "e") {
        // 只有在语音控制开启时才处理a,b,c,d,e指令
        if (voiceControlEnabled) {
            if (data == "e") {
                // 接收到e，立即发送停止指令S
                // 打断当前正在执行的任何命令
                currentCommand = 0;  // 重置当前命令状态
                commandStartTime = 0; // 重置命令开始时间
                Serial2.println("S"); // 立即发送停止指令
                longBeep(); 
                return; // 直接返回，不执行其他逻辑
            } 
            
            // 只有在当前没有活动命令或e命令已打断时，才执行a,b,c,d命令
            if (data == "a") {
                // 接收到a，发送G5指令
                currentCommand = 'a';
                commandStartTime = millis();
                Serial2.println("G5");
            } else if (data == "b") {
                // 接收到b，发送B5指令
                currentCommand = 'b';
                commandStartTime = millis();
                Serial2.println("B5");
            } else if (data == "c") {
                // 接收到c，发送TL指令（左旋转）
                currentCommand = 'c';
                commandStartTime = millis();
                Serial2.println("TL");
            } else if (data == "d") {
                // 接收到d，发送TR指令（右旋转）
                currentCommand = 'd';
                commandStartTime = millis();
                Serial2.println("TR");
            }
            // 如果语音控制关闭，忽略这些指令
        }
    }
}


void loop() {
    // 测量距离
    distanceLeft = checkDistance(2, 4);
    distanceRight = checkDistance(12, 14);

    // 如果超声波数据接收开启，处理串口2的数据
    if (ultrasonicDataReceiving) {
        while (Serial2.available()) {
            char c = Serial2.read();
            if (c == '\n') {
                // 解析接收到的数据
                parseUltrasonicData(serial2Data);
                serial2Data = "";
            } else {
                serial2Data += c;
            }
        }
    }

    // 显示距离和状态
    u8g2.firstPage();
    do {
        displayDistances();
        // 只在起身过程中显示STOP/START状态
        if (standupState != STANDUP_IDLE) {
            if (distanceLeft < MIN_SAFE_DISTANCE || distanceRight < MIN_SAFE_DISTANCE) {
                displayStop();
            } else {
                displayStart();
            }
        }
    } while (u8g2.nextPage());

    // 安全距离检测 - 只在起身过程中开启（包括暂停状态）
    // 起身完成后不再进行安全检测
    if (standupState != STANDUP_IDLE && standupState != STANDUP_START_GPIO) {
        if (distanceLeft < MIN_SAFE_DISTANCE || distanceRight < MIN_SAFE_DISTANCE) {
            unsafeCount++;
            if (unsafeCount >= UNSAFE_THRESHOLD && !safetyTriggered) {
                safetyTriggered = true;
                emergencyReset = true;
                shortBeep(); // 蜂鸣器警报一声
                
                // 进入暂停状态
                standupState = STANDUP_PAUSED;
                pauseStartTime = millis();
                unsafeCount = 0; // 重置计数
            }
        } else {
            unsafeCount = 0; // 安全，重置计数
        }
    }

    // 处理暂停状态
    if (standupState == STANDUP_PAUSED) {
        if (millis() - pauseStartTime >= pauseDuration) {
            // 5秒后重新检测安全距离
            if (distanceLeft >= MIN_SAFE_DISTANCE && distanceRight >= MIN_SAFE_DISTANCE) {
                safetyTriggered = false;
                emergencyReset = false;
                unsafeCount = 0; // 重置不安全计数
                
                // 重新进入GPIO舵机运动阶段
                standupState = STANDUP_START_GPIO;
                controlGpioServos(true);
            } else {
                // 仍然不安全，继续暂停
                pauseStartTime = millis(); // 重置暂停计时器
                shortBeep(); // 再次警报
            }
        }
    }

    // 处理半身运动状态机
    if (halfBodyState == HALFBODY_MOVING) {
        if (millis() - halfBodyStartTime >= HALFBODY_MOVE_DURATION) {
            halfBodyState = HALFBODY_IDLE; // 运动完成
        }
    }

    // 处理串口命令持续时间
    if (currentCommand != 0 && millis() - commandStartTime >= COMMAND_DURATION) {
        // 3秒后发送停止指令
        Serial2.println("S");
        currentCommand = 0; // 重置命令状态
    }
    
    // 处理人体跟踪命令超时
    if (humanTrackingActive && humanTrackingCommand != 0 && millis() - lastHumanTrackingTime > HUMAN_TRACKING_TIMEOUT) {
        // 1秒内没有收到新的跟踪指令，发送停止指令
        Serial2.println("S");
        humanTrackingCommand = 0;
    }

    // 处理主MQTT连接
    if (!client.connected()) {
        String client_id = "esp-client-";
        client_id += String(WiFi.macAddress());
        if (client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
            client.subscribe(String(String(mqtt_username) + "/" + project + "/controller").c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button_topic).c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button1_topic).c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button2_topic).c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button3_topic).c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button4_topic).c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button5_topic).c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button6_topic).c_str()); // 添加button6订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button7_topic).c_str()); // 添加button7订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button8_topic).c_str()); // 添加button8订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button9_topic).c_str()); // 添加button9订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button10_topic).c_str()); // 添加button10订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button11_topic).c_str()); // 添加button11订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button12_topic).c_str()); // 添加button12订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button13_topic).c_str()); // 添加button13订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button14_topic).c_str()); // 添加button14订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button15_topic).c_str()); // 添加button15订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button16_topic).c_str()); // 添加button16订阅
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button17_topic).c_str()); // 添加button17订阅

            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + body_topic).c_str());
            client.subscribe(String(String(mqtt_username) + "/" + project + "/" + controller_topic).c_str());
            client.subscribe(full_topic.c_str());
        }
    }
    
    // 处理人体跟踪MQTT连接
    if (!humanTrackingMqttClient.connected()) {
        String client_id = "esp32-human-tracking-";
        client_id += String(WiFi.macAddress());
        if (humanTrackingMqttClient.connect(client_id.c_str(), human_tracking_mqtt_user, human_tracking_mqtt_password)) {
            humanTrackingMqttClient.subscribe(human_tracking_command_topic);
            humanTrackingMqttClient.publish(human_tracking_status_topic, "reconnected");
        }
    }

    client.loop();
    humanTrackingMqttClient.loop(); // 处理人体跟踪MQTT消息

    // 串口数据读取和处理
    if (Serial.available() > 0) {
        int serialChar = Serial.read();
        if (serialChar == '\n') {
            processSerialData(serialData);
            serialData = "";
        } else {
            serialData += (char)serialChar;
        }
    }

    // 起身状态机处理
    if (standupState == STANDUP_START_GPIO) {
        // 检查GPIO舵机是否到达目标位置
        if (abs(current_servo_gpio5_angle - servo_gpio5_stand_angle) < 2.0 &&
            abs(current_servo_gpio15_angle - servo_gpio15_stand_angle) < 2.0) {
            // GPIO舵机到位，进入下一个阶段：运行其他舵机
            standupState = STANDUP_START;
            
            // 设置其他舵机为站立角度
            servo0_angle = servo0_stand_angle;
            servo1_angle = servo1_stand_angle;
            servo2_angle = servo2_stand_angle;
            servo3_angle = servo3_stand_angle;
            servo4_angle = servo4_stand_angle;
            servo5_angle = servo5_stand_angle;
            servo6_angle = servo6_stand_angle;
            
            update_servo0 = true;
            update_servo1 = true;
            update_servo2 = true;
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;
        }
    }
    else if (standupState == STANDUP_START) {
        // 检查所有舵机是否到达目标位置
        if (abs(current_servo0_angle - servo0_stand_angle) < 1.0 &&
            abs(current_servo1_angle - servo1_stand_angle) < 1.0 &&
            abs(current_servo2_angle - servo2_stand_angle) < 1.0 &&
            abs(current_servo3_angle - servo3_stand_angle) < 1.0 &&
            abs(current_servo4_angle - servo4_stand_angle) < 1.0 &&
            abs(current_servo5_angle - servo5_stand_angle) < 1.0 &&
            abs(current_servo6_angle - servo6_stand_angle) < 1.0) {
            
            // 起身完成，复位GPIO5和GPIO15舵机
            controlGpioServos(false);
            standupCompleted = true; // 设置起身完成标志
            fullBodyStandupCompleted = true; // 设置整体起身完成标志
            
            standupState = STANDUP_IDLE;
            // 重置安全触发标志和计数器
            safetyTriggered = false;
            emergencyReset = false;
            unsafeCount = 0;
        }
    }

    // 处理动作队列状态机 - 新增：处理上身复位状态
    if (actionQueueState == ACTION_UPPER_BODY_RESETTING) {
        // 检查上身是否复位完成
        if (isUpperBodyResetComplete()) {
            // 上身复位完成，发送9让机械臂复位
            Serial.println("9");
            actionQueueState = ACTION_IDLE;
            
            // 如果复位后需要重新执行上身启动
            if (lastTriggeredButton == 13) {
                // 等待复位完成，然后重新执行上身启动
                delay(1000);
                actionQueueState = ACTION_EXECUTING_UPPER;
                
                // 执行上身启动动作（第三关节起身）
                Serial.println("A");  // 机械臂张手
                delay(2000);  // 等待2秒，让机械臂张开完成
                
                // 设置第三关节（servo5和servo6）为站立角度
                servo5_angle = servo5_up_angle;
                servo6_angle = servo6_up_angle;
                update_servo5 = true;
                update_servo6 = true;
                
                // 控制GPIO5和GPIO15舵机旋转90度
                controlGpioServos(true);
                
                // 设置标志
                upperBodyActivated = true;
                
                shortBeep(); // 提示动作开始
            }
        }
    }
    else if (actionQueueState == ACTION_WAITING_FOR_UPPER_RESET) {
        // 检查上身是否复位完成
        if (isUpperBodyResetComplete()) {
            // 上身复位完成，开始整体复位
            actionQueueState = ACTION_RESETTING_UPPER_FOR_STANDUP;
            
            // 发送9让机械臂整体复位
            Serial.println("9");
            
            // 设置所有舵机为初始角度
            servo0_angle = servo0_initial_angle;
            servo1_angle = servo1_initial_angle;
            servo2_angle = servo2_initial_angle;
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;

            update_servo0 = true;
            update_servo1 = true;
            update_servo2 = true;
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;

            // 设置GPIO5和GPIO15舵机为初始位置（已经复位，再次确认）
            controlGpioServos(false);

            // 重置状态
            standupState = STANDUP_IDLE;
            safetyTriggered = false;
            emergencyReset = false;
        }
    }
    else if (actionQueueState == ACTION_RESETTING_UPPER_FOR_STANDUP) {
        // 检查整体复位是否完成
        if (isFullBodyResetComplete()) {
            // 整体复位完成，开始起身
            actionQueueState = ACTION_IDLE;
            standupState = STANDUP_START_GPIO;
            controlGpioServos(true);
        }
    }
    else if (actionQueueState == ACTION_RESETTING) {
        // 检查复位是否完成（所有舵机是否到达初始位置）
        if (abs(current_servo0_angle - servo0_initial_angle) < 3.0 &&
            abs(current_servo1_angle - servo1_initial_angle) < 3.0 &&
            abs(current_servo2_angle - servo2_initial_angle) < 3.0 &&
            abs(current_servo3_angle - servo3_initial_angle) < 3.0 &&
            abs(current_servo4_angle - servo4_initial_angle) < 3.0 &&
            abs(current_servo5_angle - servo5_initial_angle) < 3.0 &&
            abs(current_servo6_angle - servo6_initial_angle) < 3.0 &&
            abs(current_servo_gpio5_angle - servo_gpio5_initial_angle) < 3.0 &&
            abs(current_servo_gpio15_angle - servo_gpio15_initial_angle) < 3.0) {
            // 复位完成，等待500ms确保稳定
            actionQueueState = ACTION_WAITING;
            delay(500);
        }
    } 
    else if (actionQueueState == ACTION_RESETTING_FOR_STANDUP) {
        // 检查半身复位是否完成（等待半身复位状态机完成）
        if (halfBodyState == HALFBODY_IDLE) {
            // 半身复位完成，现在执行整体复位
            // 发送9让机械臂整体复位
            Serial.println("9");
            
            // 设置所有舵机为初始角度
            servo0_angle = servo0_initial_angle;
            servo1_angle = servo1_initial_angle;
            servo2_angle = servo2_initial_angle;
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;

            update_servo0 = true;
            update_servo1 = true;
            update_servo2 = true;
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;

            // 设置GPIO5和GPIO15舵机为初始位置
            controlGpioServos(false);

            // 重置状态
            standupState = STANDUP_IDLE;
            safetyTriggered = false;
            emergencyReset = false;
            
            // 等待整体复位完成
            delay(1000);
            
            // 整体复位完成后，进入GPIO舵机运动阶段开始起身
            actionQueueState = ACTION_IDLE;
            standupState = STANDUP_START_GPIO;
            controlGpioServos(true);
        }
    }
    else if (actionQueueState == ACTION_RESETTING_FOR_UPPER) {
        // 检查半身复位是否完成（等待半身复位状态机完成）
        if (halfBodyState == HALFBODY_IDLE) {
            // 半身复位完成，现在执行整体复位
            Serial.println("9");  // 发送数据让机械臂整体复位
            
            // 设置所有舵机为初始角度
            servo0_angle = servo0_initial_angle;
            servo1_angle = servo1_initial_angle;
            servo2_angle = servo2_initial_angle;
            servo3_angle = servo3_initial_angle;
            servo4_angle = servo4_initial_angle;
            servo5_angle = servo5_initial_angle;
            servo6_angle = servo6_initial_angle;

            update_servo0 = true;
            update_servo1 = true;
            update_servo2 = true;
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;

            // 设置GPIO5和GPIO15舵机为初始位置
            controlGpioServos(false);

            // 重置状态
            standupState = STANDUP_IDLE;
            safetyTriggered = false;
            emergencyReset = false;
            
            // 等待整体复位完成
            delay(1000);
            
            // 整体复位完成后，执行上身启动
            actionQueueState = ACTION_EXECUTING_UPPER;
            
            // 执行上身启动动作（第三关节起身）
            Serial.println("A");  // 机械臂张手
            delay(2000);  // 等待2秒，让机械臂张开完成
            
            // 设置第三关节（servo5和servo6）为站立角度
            servo5_angle = servo5_up_angle;
            servo6_angle = servo6_up_angle;
            update_servo5 = true;
            update_servo6 = true;
            
            // 控制GPIO5和GPIO15舵机旋转90度
            controlGpioServos(true);
            
            // 设置标志
            upperBodyActivated = true;
            
            shortBeep(); // 提示动作开始
        }
    }
    else if (actionQueueState == ACTION_WAITING) {
        // 等待完成，现在根据触发的按钮执行相应的动作
        if (lastTriggeredButton == 13) {  // 上身启动
            actionQueueState = ACTION_EXECUTING_UPPER;
            
            // 执行上身启动动作（第三关节起身）
            Serial.println("A");  // 机械臂张手
            delay(2000);  // 等待2秒，让机械臂张开完成
            
            // 设置第三关节（servo5和servo6）为站立角度
            servo5_angle = servo5_up_angle;
            servo6_angle = servo6_up_angle;
            update_servo5 = true;
            update_servo6 = true;
            
            // 控制GPIO5和GPIO15舵机旋转90度
            controlGpioServos(true);
            
            // 设置标志
            upperBodyActivated = true;
            
            shortBeep(); // 提示动作开始
            
        } else if (lastTriggeredButton == 15) {  // 半身启动
            actionQueueState = ACTION_EXECUTING_HALF;
            
            // 执行半身起身动作
            servo3_angle = servo3_half_angle;
            servo4_angle = servo4_half_angle;
            servo5_angle = servo5_half_angle;
            servo6_angle = servo6_half_angle;
            
            update_servo3 = true;
            update_servo4 = true;
            update_servo5 = true;
            update_servo6 = true;
            
            // 启动半身运动状态机
            halfBodyState = HALFBODY_MOVING;
            halfBodyStartTime = millis();
            halfBodyAction = true;
            
            // 控制GPIO5和GPIO15舵机旋转90度
            controlGpioServos(true);
            
            // 设置标志
            halfBodyActivated = true;
            
            shortBeep(); // 提示动作开始
        }
    }
    else if (actionQueueState == ACTION_EXECUTING_HALF) {
        // 检查半身动作是否完成
        if (halfBodyState == HALFBODY_IDLE) {
            // 半身起身完成，复位GPIO5和GPIO15舵机
            controlGpioServos(false);
            standupCompleted = true; // 设置起身完成标志
            halfBodyStandupCompleted = true; // 设置半身启动完成标志
            
            actionQueueState = ACTION_IDLE;
            lastTriggeredButton = 0;
            shortBeep(); // 提示动作完成
            shortBeep();
        }
    }
    else if (actionQueueState == ACTION_EXECUTING_UPPER) {
        // 检查上身动作是否完成
        // 上身动作没有使用halfBodyState，我们检查舵机是否到达目标位置
        if (abs(current_servo5_angle - servo5_up_angle) < 3.0 &&
            abs(current_servo6_angle - servo6_up_angle) < 3.0 &&
            abs(current_servo_gpio5_angle - servo_gpio5_stand_angle) < 3.0 &&
            abs(current_servo_gpio15_angle - servo_gpio15_stand_angle) < 3.0) {
            
            // 上身启动完成，复位GPIO5和GPIO15舵机
            controlGpioServos(false);
            standupCompleted = true; // 设置起身完成标志
            upperBodyStandupCompleted = true; // 设置上身启动完成标志
            
            actionQueueState = ACTION_IDLE;
            lastTriggeredButton = 0;
            shortBeep(); // 提示动作完成
            shortBeep();
        }
    }

    unsigned long currentMillis = millis();

    // 在暂停状态下不更新舵机
    if (standupState == STANDUP_PAUSED) {
        previousMillis = currentMillis; // 防止PID控制继续执行
        return; // 跳过舵机更新
    }

    // 定义容差和死区
    const float tolerance = 0.5;   // 容差范围
    const float deadzone = 0.3;    // 死区阈值

    if (currentMillis - previousMillis >= interval) {
        float deltaT = (currentMillis - previousMillis) / 1000.0; // 计算时间差（秒）
        previousMillis = currentMillis;

        // 舵机0更新逻辑
        if (update_servo0) {
            error0 = servo0_angle - current_servo0_angle;
            
            // 死区控制：误差小于阈值时不调整
            if (fabs(error0) < deadzone) {
                // 不更新舵机，保持当前位置
                current_servo0_angle = servo0_angle;
                integral0 = 0;
                prev_error0 = 0;
            }
            // 容差范围：直接设置到目标位置
            else if (fabs(error0) < tolerance) {
                current_servo0_angle = servo0_angle;
                integral0 = 0;
                prev_error0 = 0;
            } else {
                integral0 += error0 * deltaT;
                float derivative0 = (error0 - prev_error0) / deltaT;
                prev_error0 = error0;

                float output0 = Kp * error0 + Ki * integral0 + Kd * derivative0;
                output0 = constrain(output0, -maxStep, maxStep);

                current_servo0_angle += output0;
                current_servo0_angle = constrain(current_servo0_angle, servo0_min_angle, servo0_max_angle);
            }
        }

        // 舵机1更新逻辑
        if (update_servo1) {
            error1 = servo1_angle - current_servo1_angle;
            if (fabs(error1) < deadzone) {
                current_servo1_angle = servo1_angle;
                integral1 = 0;
                prev_error1 = 0;
            } else if (fabs(error1) < tolerance) {
                current_servo1_angle = servo1_angle;
                integral1 = 0;
                prev_error1 = 0;
            } else {
                integral1 += error1 * deltaT;
                float derivative1 = (error1 - prev_error1) / deltaT;
                prev_error1 = error1;

                float output1 = Kp * error1 + Ki * integral1 + Kd * derivative1;
                output1 = constrain(output1, -maxStep, maxStep);

                current_servo1_angle += output1;
                current_servo1_angle = constrain(current_servo1_angle, servo1_min_angle, servo1_max_angle);
            }
        }

        // 舵机2更新逻辑
        if (update_servo2) {
            error2 = servo2_angle - current_servo2_angle;
            if (fabs(error2) < deadzone) {
                current_servo2_angle = servo2_angle;
                integral2 = 0;
                prev_error2 = 0;
            } else if (fabs(error2) < tolerance) {
                current_servo2_angle = servo2_angle;
                integral2 = 0;
                prev_error2 = 0;
            } else {
                integral2 += error2 * deltaT;
                float derivative2 = (error2 - prev_error2) / deltaT;
                prev_error2 = error2;

                float output2 = Kp * error2 + Ki * integral2 + Kd * derivative2;
                output2 = constrain(output2, -maxStep, maxStep);

                current_servo2_angle += output2;
                current_servo2_angle = constrain(current_servo2_angle, servo2_min_angle, servo2_max_angle);
            }
        }

        // 舵机3更新逻辑
        if (update_servo3) {
            error3 = servo3_angle - current_servo3_angle;
            if (fabs(error3) < deadzone) {
                current_servo3_angle = servo3_angle;
                integral3 = 0;
                prev_error3 = 0;
            } else if (fabs(error3) < tolerance) {
                current_servo3_angle = servo3_angle;
                integral3 = 0;
                prev_error3 = 0;
            } else {
                integral3 += error3 * deltaT;
                float derivative3 = (error3 - prev_error3) / deltaT;
                prev_error3 = error3;

                float output3 = Kp_34 * Kp * error3 + Ki * integral3 + Kd * derivative3;
                output3 = constrain(output3, -maxStep_3456, maxStep_3456);

                current_servo3_angle += output3;
                current_servo3_angle = constrain(current_servo3_angle, servo3_min_angle, servo3_max_angle);
            }
        }

        // 舵机4更新逻辑
        if (update_servo4) {
            error4 = servo4_angle - current_servo4_angle;
            if (fabs(error4) < deadzone) {
                current_servo4_angle = servo4_angle;
                integral4 = 0;
                prev_error4 = 0;
            } else if (fabs(error4) < tolerance) {
                current_servo4_angle = servo4_angle;
                integral4 = 0;
                prev_error4 = 0;
            } else {
                integral4 += error4 * deltaT;
                float derivative4 = (error4 - prev_error4) / deltaT;
                prev_error4 = error4;

                float output4 = Kp_34 * Kp * error4 + Ki * integral4 + Kd * derivative4;
                output4 = constrain(output4, -maxStep_3456, maxStep_3456);

                current_servo4_angle += output4;
                current_servo4_angle = constrain(current_servo4_angle, servo4_min_angle, servo4_max_angle);
            }
        }

            // 舵机5更新逻辑
        if (update_servo5) {
            error5 = servo5_angle - current_servo5_angle;
            if (fabs(error5) < deadzone) {
                current_servo5_angle = servo5_angle;
                integral5 = 0;
                prev_error5 = 0;
            } else if (fabs(error5) < tolerance) {
                current_servo5_angle = servo5_angle;
                integral5 = 0;
                prev_error5 = 0;
            } else {
                integral5 += error5 * deltaT;
                float derivative5 = (error5 - prev_error5) / deltaT;
                prev_error5 = error5;

                // 半身运动状态下加快速度
                float speedMultiplier = 1.0;
                if (halfBodyState != HALFBODY_IDLE) {
                    speedMultiplier = 2.2; // 加快50%
                }

                float output5 = Kp_56 * Kp * error5 * speedMultiplier + Ki * integral5 + Kd * derivative5;
                output5 = constrain(output5, -maxStep_3456 * speedMultiplier, maxStep_3456 * speedMultiplier);

                current_servo5_angle += output5;
                current_servo5_angle = constrain(current_servo5_angle, servo5_min_angle, servo5_max_angle);
            }
        }

        // 舵机6更新逻辑
        if (update_servo6) {
            error6 = servo6_angle - current_servo6_angle;
            if (fabs(error6) < deadzone) {
                current_servo6_angle = servo6_angle;
                integral6 = 0;
                prev_error6 = 0;
            } else if (fabs(error6) < tolerance) {
                current_servo6_angle = servo6_angle;
                integral6 = 0;
                prev_error6 = 0;
            } else {
                integral6 += error6 * deltaT;
                float derivative6 = (error6 - prev_error6) / deltaT;
                prev_error6 = error6;

                // 半身运动状态下加快速度
                float speedMultiplier = 1.0;
                if (halfBodyState != HALFBODY_IDLE) {
                    speedMultiplier = 2.2; // 加快50%
                }

                float output6 = Kp_56 * Kp * error6 * speedMultiplier + Ki * integral6 + Kd * derivative6;
                output6 = constrain(output6, -maxStep_3456 * speedMultiplier, maxStep_3456 * speedMultiplier);

                current_servo6_angle += output6;
                current_servo6_angle = constrain(current_servo6_angle, servo6_min_angle, servo6_max_angle);
            }
        }

        // 新增：GPIO5舵机更新逻辑
        if (update_servo_gpio5) {
            error_gpio5 = servo_gpio5_angle - current_servo_gpio5_angle;
            if (fabs(error_gpio5) < deadzone) {
                current_servo_gpio5_angle = servo_gpio5_angle;
                integral_gpio5 = 0;
                prev_error_gpio5 = 0;
            } else if (fabs(error_gpio5) < tolerance) {
                current_servo_gpio5_angle = servo_gpio5_angle;
                integral_gpio5 = 0;
                prev_error_gpio5 = 0;
            } else {
                integral_gpio5 += error_gpio5 * deltaT;
                float derivative_gpio5 = (error_gpio5 - prev_error_gpio5) / deltaT;
                prev_error_gpio5 = error_gpio5;

                // 使用专门为GPIO舵机设置的更快参数
                float output_gpio5 = Kp_gpio * error_gpio5 + Ki * integral_gpio5 + Kd * derivative_gpio5;
                output_gpio5 = constrain(output_gpio5, -maxStep_gpio, maxStep_gpio);

                current_servo_gpio5_angle += output_gpio5;
                current_servo_gpio5_angle = constrain(current_servo_gpio5_angle, servo_gpio5_min_angle, servo_gpio5_max_angle);
            }
        }

        // 新增：GPIO15舵机更新逻辑
        if (update_servo_gpio15) {
            error_gpio15 = servo_gpio15_angle - current_servo_gpio15_angle;
            if (fabs(error_gpio15) < deadzone) {
                current_servo_gpio15_angle = servo_gpio15_angle;
                integral_gpio15 = 0;
                prev_error_gpio15 = 0;
            } else if (fabs(error_gpio15) < tolerance) {
                current_servo_gpio15_angle = servo_gpio15_angle;
                integral_gpio15 = 0;
                prev_error_gpio15 = 0;
            } else {
                integral_gpio15 += error_gpio15 * deltaT;
                float derivative_gpio15 = (error_gpio15 - prev_error_gpio15) / deltaT;
                prev_error_gpio15 = error_gpio15;

                // 使用专门为GPIO舵机设置的更快参数
                float output_gpio15 = Kp_gpio * error_gpio15 + Ki * integral_gpio15 + Kd * derivative_gpio15;
                output_gpio15 = constrain(output_gpio15, -maxStep_gpio, maxStep_gpio);

                current_servo_gpio15_angle += output_gpio15;
                current_servo_gpio15_angle = constrain(current_servo_gpio15_angle, servo_gpio15_min_angle, servo_gpio15_max_angle);
            }
        }

        // 统一写入所有舵机角度
        servo_0.write(round(current_servo0_angle));
        servo_1.write(round(current_servo1_angle)); 
        servo_2.write(round(current_servo2_angle));
        servo_3.write(round(current_servo3_angle));
        servo_4.write(round(current_servo4_angle));
        servo_5.write(round(current_servo5_angle));
        servo_6.write(round(current_servo6_angle));
        
        // 写入GPIO5和GPIO15舵机角度
        servo_gpio5.write(round(current_servo_gpio5_angle));
        servo_gpio15.write(round(current_servo_gpio15_angle));
    }
}

