#include <U8g2lib.h>
#include <Wire.h>
#include <ESP32Servo.h>
#include <PubSubClient.h>
#include <WiFi.h>
// OLED显示屏对象
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
#define BUZZER_PIN 23  // 定义蜂鸣器连接到D23引脚
#define BUZZER_ACTIVE_LOW 0  // 0=高电平触发(原硬件)，1=低电平触发
#define BOARD_LED_PIN 2        // ESP32 开发板板载 LED（与左超声波 Trig 共用）
#define BOARD_LED_ACTIVE_LOW 0 // 多数开发板低电平点亮


#define WAIST_FOLD_SWITCH_CHECK_ENABLED 0  // 腰部折叠安全触动开关：1=启用检测，0=关闭(调试时可设为0跳过检测)
#define WAIST_FOLD_SWITCH1_PIN 13   // INPUT_PULLUP，按下接 GND
#define WAIST_FOLD_SWITCH2_PIN 34   // 仅输入，需外接 10k 上拉到 3.3V
#define WAIST_FOLD_SWITCH3_PIN 35   // 同 GPIO34
const unsigned long WAIST_SWITCH_DEBOUNCE_MS = 30;

// 24V 电池电压监测（100k + 15k 分压 → GPIO36）
#define BATTERY_MONITOR_ENABLED 1       // 1=启用，0=关闭(未接线时可设0)
#define BATTERY_ADC_PIN 36              // VP，仅输入 ADC 引脚
#define BATTERY_R1_OHM 100000.0f
#define BATTERY_R2_OHM 15000.0f
// 万用表标定：显示 25.3V、实测 24.3V → 24.3/25.3 ≈ 0.9605
#define BATTERY_CAL_FACTOR 0.9605f
#define BATTERY_SAMPLE_COUNT 16
#define BATTERY_UPDATE_INTERVAL_MS 1000
// 24V 铅酸（12 节 / 两组 12V）：静置满电约 25.2V，不是标称 24V=100%
// 充电中可达 27~28.8V，静置后回落到约 25.2V 才是满电
#define BATTERY_V_FULL 25.2f            // 静置满电 ≈ 100%
#define BATTERY_V_EMPTY 21.6f           // 放电截止 ≈ 0%
#define BATTERY_V_WARN 22.8f
#define BATTERY_V_LOW 22.2f
#define BATTERY_V_CRITICAL 21.6f
#define BATTERY_LOW_BEEP_INTERVAL_MS 30000
#define BATTERY_CRIT_BEEP_INTERVAL_MS 15000

const unsigned long STATUS_LED_WIFI_ON_MS = 1000;
const unsigned long STATUS_LED_WIFI_OFF_MS = 1000;
const unsigned long STATUS_LED_MQTT_ON_MS = 500;
const unsigned long STATUS_LED_MQTT_OFF_MS = 1000;


const unsigned long WIFI_CONNECT_TIMEOUT_MS = 8000;
const unsigned long MQTT_CONNECT_TIMEOUT_MS = 3000;
const unsigned long WIFI_RETRY_INTERVAL_MS = 30000;      // 无网时降低重连频率，避免卡顿
const unsigned long MQTT_RETRY_INTERVAL_MS = 15000;
const unsigned long ROBOT_HEARTBEAT_INTERVAL_MS = 10000;
unsigned long lastRobotHeartbeatMs = 0;
const uint8_t MQTT_SOCKET_TIMEOUT_SEC = 1;               // 缩短阻塞上限（秒）
const unsigned long ULTRASONIC_PULSE_TIMEOUT_US = 30000;
const unsigned long ULTRASONIC_PULSE_TIMEOUT_FAST_US = 8000;
const unsigned long DISPLAY_REFRESH_INTERVAL_MS = 200;
const unsigned long ULTRASONIC_IDLE_INTERVAL_MS = 80;

unsigned long lastWiFiRetryMs = 0;
unsigned long lastMainMqttRetryMs = 0;
unsigned long lastHumanMqttRetryMs = 0;
unsigned long lastDisplayRefreshMs = 0;
unsigned long lastUltrasonicSampleMs = 0;
unsigned long actionDelayUntilMs = 0;
uint8_t mqttConnectTurn = 0;  // 0=main, 1=human，每次只尝试一个，限制单次阻塞
bool wifiConnectStarted = false;
bool wifiDisplayUpdated = false;

int statusLedMode = -1;
bool statusLedOn = false;
unsigned long statusLedLastChangeMs = 0;

void callback(char *topic, byte *payload, unsigned int length);
void subscribeMainMqttTopics();
void resetServos();
extern PubSubClient client;  

// 距离变量
volatile float distanceLeft;
volatile float distanceRight;

// 六路超声波（单位 cm）：
// 机械臂四路：frontLeftDistance 左前(斜前左)、frontDistance 正前、
//             frontRightDistance 右前(斜前右)、backDistance 正后
// ESP32 两路：distanceLeft 正左、distanceRight 正右
// 转发到底盘顺序：左前,正前,右前,正后,正左,正右
int frontLeftDistance = 0;
int frontDistance = 0;
int frontRightDistance = 0;
int backDistance = 0;
int rearLeftDistance = 0;
int rearRightDistance = 0;

// 定义最小安全距离阈值（单位：厘米）
const float MIN_SAFE_DISTANCE = 35.0;

float batteryVoltage = 0.0f;
int batteryPercent = 0;
bool batteryValid = false;
bool batteryLow = false;
bool batteryCritical = false;
unsigned long lastBatterySampleMs = 0;
unsigned long lastBatteryBeepMs = 0;

// 超声波测距函数（timeoutUs 可缩短，避免无回波时长时间卡住舵机）
float checkDistance(int trigPin, int echoPin, unsigned long timeoutUs = ULTRASONIC_PULSE_TIMEOUT_US) {
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);
    unsigned long duration = pulseIn(echoPin, HIGH, timeoutUs);
    if (duration == 0) {
        return 999.0;
    }
    return duration / 58.00;
}

void buzzerWrite(bool active) {
#if BUZZER_ACTIVE_LOW
    digitalWrite(BUZZER_PIN, active ? LOW : HIGH);
#else
    digitalWrite(BUZZER_PIN, active ? HIGH : LOW);
#endif
}

void buzzerIdle() {
    buzzerWrite(false);
}

void buzzer_on() {
    buzzerWrite(true);
    delay(500);
    buzzerIdle();
}

void shortBeep() {
    buzzerWrite(true);
    delay(200);
    buzzerIdle();
}

void longBeep() {
    buzzerWrite(true);
    delay(500);
    buzzerIdle();
}

void boardLedWrite(bool on) {
#if BOARD_LED_ACTIVE_LOW
    digitalWrite(BOARD_LED_PIN, on ? LOW : HIGH);
#else
    digitalWrite(BOARD_LED_PIN, on ? HIGH : LOW);
#endif
}

// 板载 LED 网络状态：全连接常亮 / WiFi 断 1s 闪 / 仅 MQTT 断 0.5s 亮 1s 灭
void updateStatusLed() {
    unsigned long now = millis();
    bool wifiOk = WiFi.status() == WL_CONNECTED;
    bool mqttOk = client.connected();

    int mode;
    if (wifiOk && mqttOk) {
        mode = 0;
    } else if (!wifiOk) {
        mode = 1;
    } else {
        mode = 2;
    }

    if (mode != statusLedMode) {
        statusLedMode = mode;
        statusLedLastChangeMs = now;
        statusLedOn = (mode == 0);
        boardLedWrite(statusLedOn);
        return;
    }

    if (mode == 0) {
        boardLedWrite(true);
        return;
    }

    unsigned long holdMs;
    if (mode == 1) {
        holdMs = statusLedOn ? STATUS_LED_WIFI_ON_MS : STATUS_LED_WIFI_OFF_MS;
    } else {
        holdMs = statusLedOn ? STATUS_LED_MQTT_ON_MS : STATUS_LED_MQTT_OFF_MS;
    }

    if (now - statusLedLastChangeMs >= holdMs) {
        statusLedOn = !statusLedOn;
        statusLedLastChangeMs = now;
        boardLedWrite(statusLedOn);
    }
}

void updateDisplayMessage(const String& line1, const String& line2 = "") {
    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_ncenR10_tf);
    u8g2.setFontPosTop();
    u8g2.setCursor(0, 0);
    u8g2.print(line1);
    if (line2.length() > 0) {
        u8g2.setCursor(0, 20);
        u8g2.print(line2);
    }
    u8g2.sendBuffer();
}

bool initDisplay() {
    Wire.begin(21, 22);
    u8g2.setI2CAddress(0x3C * 2);
    if (!u8g2.begin()) {
        return false;
    }
    u8g2.enableUTF8Print();
    updateDisplayMessage("ESP32 Boot", "Display OK");
    return true;
}

// 显示距离信息
void initBatteryMonitor() {
#if BATTERY_MONITOR_ENABLED
    analogReadResolution(12);
    analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db);
#endif
}

float readBatteryAdcVolts() {
    uint32_t sum = 0;
    for (int i = 0; i < BATTERY_SAMPLE_COUNT; i++) {
        sum += (uint32_t)analogRead(BATTERY_ADC_PIN);
        delayMicroseconds(150);
    }
    float adc = sum / (float)BATTERY_SAMPLE_COUNT;
    return adc * 3.3f / 4095.0f;
}

int calcBatteryPercent(float volts) {
    float pct = (volts - BATTERY_V_EMPTY) / (BATTERY_V_FULL - BATTERY_V_EMPTY) * 100.0f;
    if (pct > 100.0f) {
        pct = 100.0f;
    }
    if (pct < 0.0f) {
        pct = 0.0f;
    }
    return (int)(pct + 0.5f);
}

void updateBatteryMonitor() {
#if !BATTERY_MONITOR_ENABLED
    batteryValid = false;
    return;
#endif

    unsigned long now = millis();
    if (now - lastBatterySampleMs < BATTERY_UPDATE_INTERVAL_MS) {
        return;
    }
    lastBatterySampleMs = now;

    float dividerRatio = (BATTERY_R1_OHM + BATTERY_R2_OHM) / BATTERY_R2_OHM;
    float vAdc = readBatteryAdcVolts();
    batteryVoltage = vAdc * dividerRatio * BATTERY_CAL_FACTOR;

    if (batteryVoltage < 10.0f) {
        batteryValid = false;
        batteryLow = false;
        batteryCritical = false;
        return;
    }

    batteryValid = true;
    batteryPercent = calcBatteryPercent(batteryVoltage);
    batteryLow = batteryVoltage < BATTERY_V_WARN;
    batteryCritical = batteryVoltage < BATTERY_V_CRITICAL;

    if (batteryCritical) {
        if (now - lastBatteryBeepMs >= BATTERY_CRIT_BEEP_INTERVAL_MS) {
            lastBatteryBeepMs = now;
            longBeep();
            Serial2.println("S");
        }
    } else if (batteryVoltage < BATTERY_V_LOW) {
        if (now - lastBatteryBeepMs >= BATTERY_LOW_BEEP_INTERVAL_MS) {
            lastBatteryBeepMs = now;
            shortBeep();
        }
    }

    publishBatteryStatus();
}

void drawBatteryStatusLine() {
#if BATTERY_MONITOR_ENABLED
    u8g2.setCursor(0, 0);
    if (!batteryValid) {
        u8g2.print("Bat: --");
        return;
    }

    u8g2.print("Bat:");
    u8g2.print(batteryVoltage, 1);
    u8g2.print("V ");
    u8g2.print(batteryPercent);
    u8g2.print("%");

    if (batteryCritical) {
        u8g2.print(" CRIT");
    } else if (batteryLow) {
        u8g2.print(" LOW");
    }
#endif
}

void displayDistances() {
    u8g2.setFont(u8g2_font_ncenR10_tf);
    u8g2.setFontPosTop();
    drawBatteryStatusLine();
    u8g2.setCursor(0, 14);
    u8g2.print("Dist L:" + String(distanceLeft, 0));
    u8g2.setCursor(72, 14);
    u8g2.print("R:" + String(distanceRight, 0));

    u8g2.setCursor(0, 28);
    u8g2.print("FL:" + String(frontLeftDistance));
    u8g2.setCursor(40, 28);
    u8g2.print("F:" + String(frontDistance));
    u8g2.setCursor(80, 28);
    u8g2.print("FR:" + String(frontRightDistance));

    u8g2.setCursor(0, 42);
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

// 垃圾捡取 MQTT 主题
const char* garbage_tracking_command_topic = "garbage_tracking/command";  // 接收垃圾跟踪底盘指令
const char* garbage_pickup_sequence_topic = "garbage_pickup/sequence";      // 接收服务器触发捡取序列
const char* garbage_pickup_mode_topic = "garbage_pickup/mode";              // 发布/订阅避障垃圾模式
const char* garbage_pickup_status_topic = "garbage_pickup/status";          // 回报捡取状态（legacy）

// ========== 自建 Web 服务器：每台机器人唯一 ID（与管理后台录入的 robot_id 一致）==========
const char* ROBOT_ID = "R001";

String robotTopicPrefix;
String robotCmdHumanTracking;
String robotCmdGarbageTracking;
String robotCmdGarbagePickupMode;
String robotCmdGarbagePickupSequence;
String robotStatusGarbagePickup;
String robotStatusHumanTracking;
String robotStatusGarbageMode;
String robotStatusBattery;

void initRobotMqttTopics() {
    robotTopicPrefix = String("robots/") + ROBOT_ID;
    robotCmdHumanTracking = robotTopicPrefix + "/cmd/human_tracking/command";
    robotCmdGarbageTracking = robotTopicPrefix + "/cmd/garbage_tracking/command";
    robotCmdGarbagePickupMode = robotTopicPrefix + "/cmd/garbage_pickup/mode";
    robotCmdGarbagePickupSequence = robotTopicPrefix + "/cmd/garbage_pickup/sequence";
    robotStatusGarbagePickup = robotTopicPrefix + "/status/garbage_pickup";
    robotStatusHumanTracking = robotTopicPrefix + "/status/human_tracking";
    robotStatusGarbageMode = robotTopicPrefix + "/status/garbage_pickup/mode";
    robotStatusBattery = robotTopicPrefix + "/status/battery";
}

void subscribeRobotMqttTopics() {
    if (!humanTrackingMqttClient.connected()) {
        return;
    }
    humanTrackingMqttClient.subscribe(robotCmdHumanTracking.c_str());
    humanTrackingMqttClient.subscribe(robotCmdGarbageTracking.c_str());
    humanTrackingMqttClient.subscribe(robotCmdGarbagePickupSequence.c_str());
    humanTrackingMqttClient.subscribe(robotCmdGarbagePickupMode.c_str());
}

void publishRobotOnlineStatus(const char* state) {
    if (!humanTrackingMqttClient.connected()) {
        return;
    }
    String payload = String("{\"robot_id\":\"") + ROBOT_ID + "\",\"state\":\"" + state + "\"}";
    humanTrackingMqttClient.publish(robotStatusHumanTracking.c_str(), payload.c_str());
}

bool publishRobotOnlineStatusChecked(const char* state) {
    if (!humanTrackingMqttClient.connected()) {
        return false;
    }
    String payload = String("{\"robot_id\":\"") + ROBOT_ID + "\",\"state\":\"" + state + "\"}";
    return humanTrackingMqttClient.publish(robotStatusHumanTracking.c_str(), payload.c_str());
}

void publishBatteryStatus() {
#if !BATTERY_MONITOR_ENABLED
    return;
#endif
    if (!humanTrackingMqttClient.connected()) {
        return;
    }

    char payload[160];
    if (batteryValid) {
        const char* level = "normal";
        if (batteryCritical) {
            level = "critical";
        } else if (batteryLow) {
            level = "low";
        }
        snprintf(payload, sizeof(payload),
                 "{\"robot_id\":\"%s\",\"state\":\"online\",\"voltage\":%.2f,\"percent\":%d,\"level\":\"%s\",\"valid\":true}",
                 ROBOT_ID, batteryVoltage, batteryPercent, level);
    } else {
        snprintf(payload, sizeof(payload),
                 "{\"robot_id\":\"%s\",\"state\":\"online\",\"valid\":false}",
                 ROBOT_ID);
    }
    humanTrackingMqttClient.publish(robotStatusBattery.c_str(), payload);
}

// 新增：人体跟踪控制标志
bool humanTrackingEnabled = false;
bool humanTrackingActive = false;
unsigned long lastHumanTrackingTime = 0;
const unsigned long HUMAN_TRACKING_TIMEOUT = 1000; // 1秒超时
char humanTrackingCommand = 0;

// ---------- 垃圾捡取可调参数（后期调试修改） ----------
const int GARBAGE_TARGET_DISTANCE_CM = 25;       // 正前方超声波停车距离(cm)
const unsigned long GARBAGE_APPROACH_TIMEOUT = 8000;  // 接近超时(ms)
const unsigned long GARBAGE_PICKUP_STEP_DELAY = 3500; // 各步骤间隔(ms)，等腰部/机械臂动作
const unsigned long ARM_RESET_WAIT_MS = 3500;         // 机械臂收到"9"后，等待其复位完成再动身体
// ----------------------------------------------------

enum GarbagePickupState {
    GARBAGE_IDLE,
    GARBAGE_TRACKING,      // 服务器控制底盘对准
    GARBAGE_APPROACH,      // 超声波测距前进
    GARBAGE_BEND,          // 腰部弯下
    GARBAGE_PICK,          // 机械臂捡取
    GARBAGE_PLACE,         // 放入体内
    GARBAGE_STANDUP        // 腰部起身
};

GarbagePickupState garbagePickupState = GARBAGE_IDLE;
bool garbageTrackingEnabled = false;
bool garbagePickupActive = false;
unsigned long garbagePhaseStartTime = 0;
int garbageTargetDistanceCm = GARBAGE_TARGET_DISTANCE_CM;
unsigned long lastGarbageCommandTime = 0;
const unsigned long GARBAGE_COMMAND_TIMEOUT = 1000;
char garbageTrackingCommand = 0;

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

// 主循环优化后不再被 WiFi/OLED/超声波拖慢，PID 实际触发频率升高。
// 用此系数把“单步角度”压回优化前的体感速度（可在 0.25~0.45 间微调）。
const float SERVO_SPEED_SCALE = 0.35f;

// 新增：舵机3/4/5/6专用参数
const float Kp_34 = 8.0;
const float Kp_56 = 5.0;
const float maxStep_3456 = 1.5f * SERVO_SPEED_SCALE;

const float maxStep = 0.8f * SERVO_SPEED_SCALE;
const float minStep = 0.1;

// 新增：GPIO5和GPIO15舵机专门的速度参数
const float maxStep_gpio = 4.0f * SERVO_SPEED_SCALE;
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

bool waistFoldSafetyLocked = false;  // true=开关未全部按下，禁止舵机动作
bool bodyServosAttached = false;

// 舵机稳定控制：到位后停止PID并仅在角度变化时写PWM，减少抖动
const float servo_settle_threshold = 1.0f;
const float integral_max = 15.0f;
const int SERVO_WRITE_COUNT = 9;
int lastWrittenServoAngle[SERVO_WRITE_COUNT];

void initLastWrittenServoAngles() {
    for (int i = 0; i < SERVO_WRITE_COUNT; i++) {
        lastWrittenServoAngle[i] = -1;
    }
}

void writeServoIfChanged(Servo &servo, int index, float angle) {
    int rounded = (int)round(angle);
    if (rounded != lastWrittenServoAngle[index]) {
        servo.write(rounded);
        lastWrittenServoAngle[index] = rounded;
    }
}

void settleServo(float target, float &current, float &integral, float &prev_error, bool &update_flag) {
    current = target;
    integral = 0;
    prev_error = 0;
    update_flag = false;
}

void lockAllBodyServosAtTarget() {
    settleServo(servo0_angle, current_servo0_angle, integral0, prev_error0, update_servo0);
    settleServo(servo1_angle, current_servo1_angle, integral1, prev_error1, update_servo1);
    settleServo(servo2_angle, current_servo2_angle, integral2, prev_error2, update_servo2);
    settleServo(servo3_angle, current_servo3_angle, integral3, prev_error3, update_servo3);
    settleServo(servo4_angle, current_servo4_angle, integral4, prev_error4, update_servo4);
    settleServo(servo5_angle, current_servo5_angle, integral5, prev_error5, update_servo5);
    settleServo(servo6_angle, current_servo6_angle, integral6, prev_error6, update_servo6);
    settleServo(servo_gpio5_angle, current_servo_gpio5_angle, integral_gpio5, prev_error_gpio5, update_servo_gpio5);
    settleServo(servo_gpio15_angle, current_servo_gpio15_angle, integral_gpio15, prev_error_gpio15, update_servo_gpio15);

    writeServoIfChanged(servo_0, 0, current_servo0_angle);
    writeServoIfChanged(servo_1, 1, current_servo1_angle);
    writeServoIfChanged(servo_2, 2, current_servo2_angle);
    writeServoIfChanged(servo_3, 3, current_servo3_angle);
    writeServoIfChanged(servo_4, 4, current_servo4_angle);
    writeServoIfChanged(servo_5, 5, current_servo5_angle);
    writeServoIfChanged(servo_6, 6, current_servo6_angle);
    writeServoIfChanged(servo_gpio5, 7, current_servo_gpio5_angle);
    writeServoIfChanged(servo_gpio15, 8, current_servo_gpio15_angle);
}

#if WAIST_FOLD_SWITCH_CHECK_ENABLED
void initWaistFoldSwitchPins() {
    pinMode(WAIST_FOLD_SWITCH1_PIN, INPUT_PULLUP);
    pinMode(WAIST_FOLD_SWITCH2_PIN, INPUT);
    pinMode(WAIST_FOLD_SWITCH3_PIN, INPUT);
}

bool readWaistFoldSwitchPressed(int pin) {
    return digitalRead(pin) == LOW;
}

bool areAllWaistFoldSwitchesPressed() {
    static unsigned long lastCheckMs = 0;
    static bool lastResult = false;
    unsigned long now = millis();
    if (now - lastCheckMs < WAIST_SWITCH_DEBOUNCE_MS) {
        return lastResult;
    }
    lastCheckMs = now;
    lastResult = readWaistFoldSwitchPressed(WAIST_FOLD_SWITCH1_PIN) &&
                 readWaistFoldSwitchPressed(WAIST_FOLD_SWITCH2_PIN) &&
                 readWaistFoldSwitchPressed(WAIST_FOLD_SWITCH3_PIN);
    return lastResult;
}

void displayWaistFoldLocked() {
    u8g2.setFont(u8g2_font_ncenR10_tf);
    u8g2.setFontPosTop();
    u8g2.setCursor(0, 0);
    u8g2.print("Fold Waist!");
    u8g2.setCursor(0, 18);
    u8g2.print("SW1:");
    u8g2.print(readWaistFoldSwitchPressed(WAIST_FOLD_SWITCH1_PIN) ? "OK" : "--");
    u8g2.print(" SW2:");
    u8g2.print(readWaistFoldSwitchPressed(WAIST_FOLD_SWITCH2_PIN) ? "OK" : "--");
    u8g2.setCursor(0, 36);
    u8g2.print("SW3:");
    u8g2.print(readWaistFoldSwitchPressed(WAIST_FOLD_SWITCH3_PIN) ? "OK" : "--");
    u8g2.setCursor(0, 52);
    u8g2.print("Servos Locked");
}
#endif

bool isWaistFoldSafetyBlocking() {
#if WAIST_FOLD_SWITCH_CHECK_ENABLED
    return waistFoldSafetyLocked;
#else
    return false;
#endif
}

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
const char *left_90_topic = "left_90";
const char *right_90_topic = "right_90";
const char *forward_1m_topic = "forward_1m";
const char *retreat_1m_topic = "retreat_1m";

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
unsigned long currentCommandDuration = 0;
const unsigned long PRESET_TRANSLATE_1M_DURATION_MS = 1500;
const unsigned long PRESET_TURN_90_DURATION_MS = 650;
const unsigned long PRESET_ULTRASONIC_WAIT_MS = 1000;
char presetMotionPending = 0;
unsigned long presetMotionRequestTime = 0;
unsigned long lastUltrasonicFrameMs = 0;
bool presetMotionSafetyEnabled = false;
bool presetMotionOwnsVoiceSafety = false;

// 新增：超声波数据接收控制
bool ultrasonicDataReceiving = false; // 是否接收超声波数据
String serial2Data = ""; // 存储从串口2接收的数据

// 新增：语音控制开关状态
bool voiceControlEnabled = false; // 语音控制功能开关

// 用于记录开关状态（需在 syncUltrasonicReceiving 之前声明）
bool button6_state = false;
bool button7_state = false;
bool button8_state = false;
bool ultrasonicHardwareEnabled = false;
bool chassisAutonomousAvoidanceEnabled = false;

void sendVoiceMoveCommand(const char *cmd);

// 同步超声波：ESP32接收 + 机械臂端四路超声波硬件开关
void syncUltrasonicReceiving() {
    bool needUltrasonic = button6_state || voiceControlEnabled || presetMotionSafetyEnabled;
    ultrasonicDataReceiving = needUltrasonic;

    if (needUltrasonic != ultrasonicHardwareEnabled) {
        ultrasonicHardwareEnabled = needUltrasonic;
        if (needUltrasonic) {
            Serial.println("6"); // 开启机械臂STM32四路超声波测量
        } else {
            Serial.println("7"); // 关闭机械臂超声波测量
        }
    }
}

// 同步底盘自主避障：仅 button6 开启且语音控制关闭时启用
void syncChassisAutonomousAvoidance() {
    bool wantAuto = button6_state && !voiceControlEnabled;
    if (wantAuto != chassisAutonomousAvoidanceEnabled) {
        chassisAutonomousAvoidanceEnabled = wantAuto;
        if (wantAuto) {
            Serial2.println("6"); // 底盘自动前进+完整避障
        } else {
            Serial2.println("7"); // 关闭底盘自主避障
        }
    }
}

// 语音控制超声波避障阈值（单位：cm）
const int VOICE_OBSTACLE_CM = 15;

// 判断距离是否小于语音避障阈值
bool isUltrasonicTooClose(int distanceCm) {
    return distanceCm > 0 && distanceCm < VOICE_OBSTACLE_CM;
}

// 检查预设运动方向是否被障碍物阻挡
bool isMotionDirectionBlocked(char cmd) {
    switch (cmd) {
        case 'a':
            // 前进：正前 + 左前 + 右前，任一 < 15cm 则停止
            return isUltrasonicTooClose(frontDistance) ||
                   isUltrasonicTooClose(frontLeftDistance) ||
                   isUltrasonicTooClose(frontRightDistance);
        case 'b':
            // 后退：正后 + 左后 + 右后
            return isUltrasonicTooClose(backDistance) ||
                   isUltrasonicTooClose(rearLeftDistance) ||
                   isUltrasonicTooClose(rearRightDistance);
        case 'c':
            // 左旋转：左前 + 左后
            return isUltrasonicTooClose(frontLeftDistance) ||
                   isUltrasonicTooClose(rearLeftDistance);
        case 'd':
            // 右旋转：右前 + 右后
            return isUltrasonicTooClose(frontRightDistance) ||
                   isUltrasonicTooClose(rearRightDistance);
        default:
            return false;
    }
}

unsigned long getPresetMotionDuration(char cmd) {
    return (cmd == 'c' || cmd == 'd')
               ? PRESET_TURN_90_DURATION_MS
               : PRESET_TRANSLATE_1M_DURATION_MS;
}

const char* getPresetMotionSerialCommand(char cmd) {
    switch (cmd) {
        case 'a': return "G5";
        case 'b': return "B5";
        case 'c': return "TL";
        case 'd': return "TR";
        default: return "S";
    }
}

void finishPresetMotion(bool obstacleStop) {
    Serial2.println("S");
    currentCommand = 0;
    commandStartTime = 0;
    currentCommandDuration = 0;
    presetMotionPending = 0;

    if (presetMotionOwnsVoiceSafety && !voiceControlEnabled) {
        Serial2.println("B");
    }
    presetMotionOwnsVoiceSafety = false;
    presetMotionSafetyEnabled = false;
    syncUltrasonicReceiving();

    if (obstacleStop) {
        shortBeep();
    }
}

void startPresetMotionNow(char cmd) {
    currentCommand = cmd;
    commandStartTime = millis();
    currentCommandDuration = getPresetMotionDuration(cmd);
    presetMotionPending = 0;
    sendVoiceMoveCommand(getPresetMotionSerialCommand(cmd));
}

void requestPresetMotion(char cmd) {
    if (cmd < 'a' || cmd > 'd') {
        return;
    }

    if (currentCommand != 0 || presetMotionPending != 0) {
        finishPresetMotion(false);
    }

    presetMotionSafetyEnabled = true;
    presetMotionOwnsVoiceSafety = !voiceControlEnabled;
    presetMotionPending = cmd;
    presetMotionRequestTime = millis();
    lastUltrasonicFrameMs = 0;
    syncUltrasonicReceiving();

    if (presetMotionOwnsVoiceSafety) {
        Serial2.println("A");
    }
}

void processPresetMotionState() {
    if (presetMotionPending == 0) {
        return;
    }

    unsigned long now = millis();
    bool freshFrame = lastUltrasonicFrameMs != 0 &&
                      (long)(lastUltrasonicFrameMs - presetMotionRequestTime) >= 0;
    if (!freshFrame) {
        if (now - presetMotionRequestTime >= PRESET_ULTRASONIC_WAIT_MS) {
            finishPresetMotion(true);
        }
        return;
    }

    if (isMotionDirectionBlocked(presetMotionPending)) {
        finishPresetMotion(true);
        return;
    }

    startPresetMotionNow(presetMotionPending);
}

bool isPresetTriggerPayload(const String& data) {
    String normalized = data;
    normalized.trim();
    normalized.toLowerCase();
    return normalized.length() > 0 &&
           normalized != "0" &&
           normalized != "false" &&
           normalized != "off";
}

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
    ACTION_UPPER_BODY_RESETTING,  // 新增：上身复位状态
    ACTION_DELAY_THEN_STANDUP,    // 非阻塞等待后起身
    ACTION_DELAY_THEN_UPPER,      // 非阻塞等待后上身启动
    ACTION_WAITING_ARM_THEN_BODY_RESET  // 先等机械臂复位，再身体复位
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

void attachBodyServos() {
    if (bodyServosAttached) {
        return;
    }
    servo_0.attach(32);
    servo_1.attach(33);
    servo_2.attach(25);
    servo_3.attach(26);
    servo_4.attach(27);
    servo_5.attach(19);
    servo_6.attach(18);
    servo_gpio5.attach(5);
    servo_gpio15.attach(15);
    bodyServosAttached = true;
}

void initBodyServoPositionsToReset() {
    current_servo0_angle = servo0_initial_angle;
    current_servo1_angle = servo1_initial_angle;
    current_servo2_angle = servo2_initial_angle;
    current_servo3_angle = servo3_initial_angle;
    current_servo4_angle = servo4_initial_angle;
    current_servo5_angle = servo5_initial_angle;
    current_servo6_angle = servo6_initial_angle;
    current_servo_gpio5_angle = servo_gpio5_initial_angle;
    current_servo_gpio15_angle = servo_gpio15_initial_angle;

    servo_0.write(servo0_initial_angle);
    servo_1.write(servo1_initial_angle);
    servo_2.write(servo2_initial_angle);
    servo_3.write(servo3_initial_angle);
    servo_4.write(servo4_initial_angle);
    servo_5.write(servo5_initial_angle);
    servo_6.write(servo6_initial_angle);
    servo_gpio5.write(servo_gpio5_initial_angle);
    servo_gpio15.write(servo_gpio15_initial_angle);

    initLastWrittenServoAngles();
    lastWrittenServoAngle[0] = servo0_initial_angle;
    lastWrittenServoAngle[1] = servo1_initial_angle;
    lastWrittenServoAngle[2] = servo2_initial_angle;
    lastWrittenServoAngle[3] = servo3_initial_angle;
    lastWrittenServoAngle[4] = servo4_initial_angle;
    lastWrittenServoAngle[5] = servo5_initial_angle;
    lastWrittenServoAngle[6] = servo6_initial_angle;
    lastWrittenServoAngle[7] = servo_gpio5_initial_angle;
    lastWrittenServoAngle[8] = servo_gpio15_initial_angle;

    resetServos();
}

#if WAIST_FOLD_SWITCH_CHECK_ENABLED
void updateWaistFoldSafety() {
    bool allPressed = areAllWaistFoldSwitchesPressed();
    if (allPressed) {
        if (waistFoldSafetyLocked) {
            waistFoldSafetyLocked = false;
            attachBodyServos();
            initBodyServoPositionsToReset();
            standupState = STANDUP_IDLE;
            actionQueueState = ACTION_IDLE;
            shortBeep();
            updateDisplayMessage("Waist OK", "Unlocked");
        }
    } else if (!waistFoldSafetyLocked) {
        waistFoldSafetyLocked = true;
        if (bodyServosAttached) {
            lockAllBodyServosAtTarget();
        }
        standupState = STANDUP_IDLE;
        actionQueueState = ACTION_IDLE;
        halfBodyState = HALFBODY_IDLE;
        Serial2.println("S");
        longBeep();
    } else {
        waistFoldSafetyLocked = true;
    }
}
#endif

const unsigned long COMMAND_DEDUP_MS = 3000;
const unsigned long ARM_COMMAND_DEDUP_MS = 3000;

String lastDedupSerialCommand = "";
unsigned long lastDedupSerialMs = 0;
String lastDedupMqttKey = "";
unsigned long lastDedupMqttMs = 0;
String lastArmCommandExecuted = "";
unsigned long lastArmCommandExecutedMs = 0;
bool mainMqttTopicsSubscribed = false;

void markSerialCommandDedup(const String& cmd) {
    lastDedupSerialCommand = cmd;
    lastDedupSerialMs = millis();
}

bool isDuplicateSerialCommand(const String& data) {
    return data.length() > 0 &&
           data == lastDedupSerialCommand &&
           (millis() - lastDedupSerialMs) < COMMAND_DEDUP_MS;
}

bool isButtonMqttTopic(const String& topicStr) {
    const String btnPrefix = String(mqtt_username) + "/" + project + "/button";
    const String topicPrefix = String(mqtt_username) + "/" + project + "/";
    return topicStr.startsWith(btnPrefix) ||
           topicStr == topicPrefix + left_90_topic ||
           topicStr == topicPrefix + right_90_topic ||
           topicStr == topicPrefix + forward_1m_topic ||
           topicStr == topicPrefix + retreat_1m_topic;
}

bool shouldIgnoreDuplicateMqtt(const String& topic, const String& data) {
    if (!isButtonMqttTopic(topic)) {
        return false;
    }
    String key = topic + "|" + data;
    if (key == lastDedupMqttKey && (millis() - lastDedupMqttMs) < COMMAND_DEDUP_MS) {
        return true;
    }
    lastDedupMqttKey = key;
    lastDedupMqttMs = millis();
    return false;
}

bool shouldIgnoreDuplicateArmCommand(const char* cmd) {
    String cmdStr = String(cmd);
    if (cmdStr.length() == 0) {
        return false;
    }
    if (cmdStr == lastArmCommandExecuted &&
        (millis() - lastArmCommandExecutedMs) < ARM_COMMAND_DEDUP_MS) {
        return true;
    }
    lastArmCommandExecuted = cmdStr;
    lastArmCommandExecutedMs = millis();
    return false;
}

// 机械臂动作权限：须先完成整体起身(4)或半身启动(12/18)；上身启动不解锁机械臂
bool isArmActionAllowed() {
    return fullBodyStandupCompleted || halfBodyStandupCompleted;
}

// 向机械臂(STM32/Serial)发送动作指令；未就绪时蜂鸣一声并拒绝
bool sendArmActionCommand(const char* cmd) {
    if (!isArmActionAllowed()) {
        shortBeep();
        return false;
    }
    if (shouldIgnoreDuplicateArmCommand(cmd)) {
        return false;
    }
    Serial.println(cmd);
    markSerialCommandDedup(String(cmd));
    return true;
}

// 上身启动：先机械臂张手，再驱动第三关节（内部流程，不受手势权限限制）
void beginUpperBodyStandup() {
    actionQueueState = ACTION_EXECUTING_UPPER;

    Serial.println("A");  // 机械臂张手
    delay(2000);          // 等待张手完成

    servo5_angle = servo5_up_angle;
    servo6_angle = servo6_up_angle;
    update_servo5 = true;
    update_servo6 = true;

    controlGpioServos(true);
    upperBodyActivated = true;
    shortBeep();
}

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

// 整体复位：先发机械臂"9"，等 ARM_RESET_WAIT_MS 后再动身体舵机
void startFullBodyResetArmFirst() {
    Serial.println("9");  // 先让机械臂复位
    markSerialCommandDedup("9");
    actionDelayUntilMs = millis() + ARM_RESET_WAIT_MS;
    actionQueueState = ACTION_WAITING_ARM_THEN_BODY_RESET;
    standupState = STANDUP_IDLE;
    safetyTriggered = false;
    emergencyReset = false;
}

// 机械臂等待结束后，开始身体舵机复位
void beginBodyServoResetAfterArm() {
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

    fullBodyStandupCompleted = false;
    upperBodyStandupCompleted = false;
    halfBodyStandupCompleted = false;
    halfBodyActivated = false;
    upperBodyActivated = false;
    standupCompleted = false;

    actionQueueState = ACTION_RESETTING;
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

// 超声波数据发送控制变量
unsigned long lastUltrasonicSendTime = 0;
const unsigned long ULTRASONIC_SEND_INTERVAL = 50; // 转发到底盘的超声波间隔(ms)

// 新增：控制move主题是否允许发送的标志
bool moveTopicAllowed = true; // 初始允许发送move主题

// 发送语音运动指令，flush 确保优先发出
void sendVoiceMoveCommand(const char *cmd) {
    Serial2.println(cmd);
    Serial2.flush();
}

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
        lastUltrasonicFrameMs = millis();
        
        unsigned long now = millis();
        if (now - lastUltrasonicSendTime < ULTRASONIC_SEND_INTERVAL) {
            return;
        }
        lastUltrasonicSendTime = now;

        // 组合六个超声波数据并发送（确保六个数据一组换行）
        String combinedData = String(frontLeftDistance) + "," + 
                              String(frontDistance) + "," + 
                              String(frontRightDistance) + "," + 
                              String(backDistance) + "," + 
                              String((int)distanceLeft) + "," + 
                              String((int)distanceRight);
        
        Serial2.println(combinedData);
    }
}

void publishGarbageStatus(const char* phase, const char* message);

// 由 Web/服务器远程设置垃圾捡取模式（不重复发布 mode 主题，避免回声）
void applyRemoteGarbagePickupMode(bool enabled, int targetDistanceCm) {
    if (targetDistanceCm > 0) {
        garbageTargetDistanceCm = targetDistanceCm;
    }
    if (enabled) {
        if (!button6_state) {
            button6_state = true;
            moveTopicAllowed = false;
            syncUltrasonicReceiving();
            syncChassisAutonomousAvoidance();
            lastUltrasonicSendTime = 0;
            shortBeep();
        }
        garbageTrackingEnabled = true;
        garbagePickupState = GARBAGE_TRACKING;
        garbagePickupActive = true;
    } else {
        Serial2.println("S");
        if (button6_state) {
            button6_state = false;
            moveTopicAllowed = true;
            syncUltrasonicReceiving();
            syncChassisAutonomousAvoidance();
            shortBeep();
            shortBeep();
        }
        garbageTrackingEnabled = false;
        garbagePickupState = GARBAGE_IDLE;
        garbagePickupActive = false;
    }
}

// 人体跟踪 / 垃圾跟踪 MQTT 统一回调
void humanTrackingCallback(char* topic, byte* payload, unsigned int length) {
    String topicStr = String(topic);
    String data = "";
    for (int i = 0; i < length; i++) {
        data += (char)payload[i];
    }

    if (isWaistFoldSafetyBlocking()) {
        if (topicStr == robotCmdHumanTracking ||
            topicStr == robotCmdGarbageTracking ||
            topicStr == robotCmdGarbagePickupSequence) {
            return;
        }
    }

    // Web/服务器远程垃圾模式开关（忽略 ESP32 自己发布的无 source 消息）
    if (topicStr == robotCmdGarbagePickupMode) {
        if (data.indexOf("\"source\":\"web\"") < 0 && data.indexOf("\"source\":\"server\"") < 0) {
            return;
        }
        int targetDistance = 0;
        if (data.indexOf("target_distance_cm") >= 0) {
            int idx = data.indexOf("target_distance_cm");
            int colon = data.indexOf(':', idx);
            if (colon >= 0) {
                targetDistance = data.substring(colon + 1).toInt();
            }
        }
        bool enabled = data.indexOf("\"enabled\":true") >= 0;
        applyRemoteGarbagePickupMode(enabled, targetDistance);
        return;
    }

    // 垃圾跟踪底盘指令（支持 PID 连续调速 V025L08 / B020N00 / S）
    if (topicStr == robotCmdGarbageTracking) {
        if (garbagePickupState != GARBAGE_IDLE && garbagePickupState != GARBAGE_TRACKING) {
            return;
        }
        data.trim();
        if (data.length() == 0) {
            return;
        }
        if (data == "S" || data == "stop") {
            Serial2.println("S");
            garbageTrackingCommand = 'S';
        } else if (data.startsWith("V") || data.startsWith("B")) {
            Serial2.println(data);
            garbageTrackingCommand = data.charAt(0);
        } else if (data == "forward") {
            Serial2.println("V020N00");
            garbageTrackingCommand = 'G';
        } else if (data == "backward") {
            Serial2.println("B015N00");
            garbageTrackingCommand = 'B';
        } else if (data == "left") {
            Serial2.println("V000L08");
            garbageTrackingCommand = 'L';
        } else if (data == "right") {
            Serial2.println("V000R08");
            garbageTrackingCommand = 'R';
        } else {
            Serial2.println(data);
        }
        lastGarbageCommandTime = millis();
        return;
    }

    // 垃圾捡取序列触发
    if (topicStr == robotCmdGarbagePickupSequence) {
        if (data.indexOf("target_distance_cm") >= 0) {
            int idx = data.indexOf("target_distance_cm");
            int colon = data.indexOf(':', idx);
            if (colon >= 0) {
                garbageTargetDistanceCm = data.substring(colon + 1).toInt();
            }
        }
        if (data.indexOf("\"phase\":\"aligned\"") >= 0 && garbagePickupState == GARBAGE_TRACKING) {
            Serial2.println("S");
            garbagePickupState = GARBAGE_APPROACH;
            garbagePhaseStartTime = millis();
            publishGarbageStatus("approach", "aligned start approach");
        } else if (data.indexOf("\"phase\":\"abort\"") >= 0) {
            Serial2.println("S");
            garbagePickupState = GARBAGE_IDLE;
            garbagePickupActive = false;
            publishGarbageStatus("aborted", "pickup aborted");
        }
        return;
    }

    // 人体跟踪指令（robots/{robot_id}/cmd/human_tracking/command）
    if (topicStr != robotCmdHumanTracking) {
        return;
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
        command = data;
    }
    Serial2.println(command);
    lastHumanTrackingTime = millis();
}

// 发布垃圾捡取状态到服务器
void publishGarbageStatus(const char* phase, const char* message) {
    if (!humanTrackingMqttClient.connected()) return;
    String payload = String("{\"phase\":\"") + phase + "\",\"message\":\"" + message +
                     "\",\"robot_id\":\"" + String(ROBOT_ID) +
                     "\",\"front_distance\":" + String(frontDistance) +
                     ",\"target_distance_cm\":" + String(garbageTargetDistanceCm) + "}";
    humanTrackingMqttClient.publish(robotStatusGarbagePickup.c_str(), payload.c_str());
}

// 启动腰部弯下（复用半身起身角度）
void startGarbageWaistBend() {
    servo3_angle = servo3_half_angle;
    servo4_angle = servo4_half_angle;
    servo5_angle = servo5_half_angle;
    servo6_angle = servo6_half_angle;
    update_servo3 = true;
    update_servo4 = true;
    update_servo5 = true;
    update_servo6 = true;
    halfBodyState = HALFBODY_MOVING;
    halfBodyStartTime = millis();
    halfBodyAction = true;
    controlGpioServos(true);
}

// 启动腰部起身复位
void startGarbageWaistStandup() {
    servo3_angle = servo3_initial_angle;
    servo4_angle = servo4_initial_angle;
    servo5_angle = servo5_initial_angle;
    servo6_angle = servo6_initial_angle;
    update_servo3 = true;
    update_servo4 = true;
    update_servo5 = true;
    update_servo6 = true;
    halfBodyState = HALFBODY_MOVING;
    halfBodyStartTime = millis();
    halfBodyAction = false;
    controlGpioServos(false);
}

// 垃圾捡取状态机（主循环调用）
void processGarbagePickupStateMachine() {
    if (garbagePickupState == GARBAGE_IDLE) return;
    if (isWaistFoldSafetyBlocking()) return;

    unsigned long now = millis();
    static unsigned long lastApproachMoveTime = 0;

    switch (garbagePickupState) {
        case GARBAGE_TRACKING:
            if (garbageTrackingCommand != 0 && now - lastGarbageCommandTime > GARBAGE_COMMAND_TIMEOUT) {
                Serial2.println("S");
                garbageTrackingCommand = 0;
            }
            break;

        case GARBAGE_APPROACH:
            if (frontDistance > 0 && frontDistance <= (unsigned int)garbageTargetDistanceCm) {
                Serial2.println("S");
                garbagePickupState = GARBAGE_BEND;
                garbagePhaseStartTime = now;
                startGarbageWaistBend();
                publishGarbageStatus("bend", "distance reached, bending waist");
            } else if (now - garbagePhaseStartTime > GARBAGE_APPROACH_TIMEOUT) {
                Serial2.println("S");
                garbagePickupState = GARBAGE_TRACKING;
                garbagePickupActive = true;
                publishGarbageStatus("failed", "approach timeout");
            } else if (now - lastApproachMoveTime > 300) {
                Serial2.println("G1");
                lastApproachMoveTime = now;
            }
            break;

        case GARBAGE_BEND:
            if (halfBodyState == HALFBODY_IDLE && now - garbagePhaseStartTime > 500) {
                garbagePickupState = GARBAGE_PICK;
                garbagePhaseStartTime = now;
                Serial.println("P");
                publishGarbageStatus("pick", "arm picking garbage");
            }
            break;

        case GARBAGE_PICK:
            if (now - garbagePhaseStartTime > GARBAGE_PICKUP_STEP_DELAY) {
                garbagePickupState = GARBAGE_PLACE;
                garbagePhaseStartTime = now;
                Serial.println("Q");
                publishGarbageStatus("place", "placing garbage inside");
            }
            break;

        case GARBAGE_PLACE:
            if (now - garbagePhaseStartTime > GARBAGE_PICKUP_STEP_DELAY) {
                garbagePickupState = GARBAGE_STANDUP;
                garbagePhaseStartTime = now;
                startGarbageWaistStandup();
                publishGarbageStatus("standup", "waist standing up");
            }
            break;

        case GARBAGE_STANDUP:
            if (halfBodyState == HALFBODY_IDLE && now - garbagePhaseStartTime > 500) {
                garbagePickupState = GARBAGE_TRACKING;
                garbagePickupActive = false;
                publishGarbageStatus("complete", "pickup complete");
            }
            break;

        default:
            break;
    }
}

void callback(char *topic, byte *payload, unsigned int length) {
    String data = "";
    for (int i = 0; i < length; i++) {
        data += (char)payload[i];
    }
    data.trim();

    String topicStr = String(topic);
    if (shouldIgnoreDuplicateMqtt(topicStr, data)) {
        return;
    }

    if (isWaistFoldSafetyBlocking()) {
        return;
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

    // 四个米思奇预设运动按键；忽略松开消息，避免一次点击重复执行。
    if (topicStr == String(mqtt_username) + "/" + project + "/" + left_90_topic) {
        if (isPresetTriggerPayload(data)) requestPresetMotion('c');
        return;
    }
    if (topicStr == String(mqtt_username) + "/" + project + "/" + right_90_topic) {
        if (isPresetTriggerPayload(data)) requestPresetMotion('d');
        return;
    }
    if (topicStr == String(mqtt_username) + "/" + project + "/" + forward_1m_topic) {
        if (isPresetTriggerPayload(data)) requestPresetMotion('a');
        return;
    }
    if (topicStr == String(mqtt_username) + "/" + project + "/" + retreat_1m_topic) {
        if (isPresetTriggerPayload(data)) requestPresetMotion('b');
        return;
    }

    // 处理button17开关（跳舞）
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button17_topic)) {
        sendArmActionCommand("G");
        return;
    }

    // 处理button6开关
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button6_topic)) {
        // 切换开关状态
        button6_state = !button6_state;
        moveTopicAllowed = !button6_state; // 当button6开启时，禁止move主题发送
        syncUltrasonicReceiving();
        syncChassisAutonomousAvoidance();
        
        if (button6_state) {
            // 清空上一次发送时间，确保立即发送
            lastUltrasonicSendTime = 0;
            shortBeep(); // 短蜂鸣提示开启
            // 开启避障时同步开启垃圾捡取模式（通知服务器与 OpenMV）
            garbageTrackingEnabled = true;
            garbagePickupState = GARBAGE_TRACKING;
            garbagePickupActive = true;
            if (humanTrackingMqttClient.connected()) {
                String modeMsg = String("{\"enabled\":true,\"target_distance_cm\":") +
                                 String(garbageTargetDistanceCm) + ",\"robot_id\":\"" + String(ROBOT_ID) + "\"}";
                humanTrackingMqttClient.publish(robotStatusGarbageMode.c_str(), modeMsg.c_str());
            }
        } else {
            Serial2.println("S"); // 发送停止
            shortBeep(); // 短蜂鸣提示关闭
            shortBeep();
            garbageTrackingEnabled = false;
            garbagePickupState = GARBAGE_IDLE;
            garbagePickupActive = false;
            if (humanTrackingMqttClient.connected()) {
                humanTrackingMqttClient.publish(robotStatusGarbageMode.c_str(), (String("{\"enabled\":false,\"robot_id\":\"") + ROBOT_ID + "\"}").c_str());
            }
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
            syncUltrasonicReceiving();
            syncChassisAutonomousAvoidance();
            lastUltrasonicSendTime = 0;
            Serial2.println("A");
            Serial.println("A"); // 开启语音控制，发送A
            shortBeep(); // 短蜂鸣提示开启
        } else {
            currentCommand = 0;
            commandStartTime = 0;
            currentCommandDuration = 0;
            presetMotionPending = 0;
            presetMotionSafetyEnabled = false;
            presetMotionOwnsVoiceSafety = false;
            Serial2.println("S");
            Serial2.println("B");
            syncUltrasonicReceiving();
            syncChassisAutonomousAvoidance();
            Serial.println("B"); // 关闭语音控制，发送B
            shortBeep(); // 短蜂鸣提示关闭
            shortBeep();
        }
        return;
    }

    // 处理button9开关（抬手）
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button9_topic)) {
        sendArmActionCommand("3");
        return;
    }

    // 处理button10开关（双手抬起）
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button10_topic)) {
        sendArmActionCommand("4");
        return;
    }

    // 处理button11开关（叉腰）
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button11_topic)) {
        sendArmActionCommand("8");
        return;
    }

    // 处理button12开关（放手）
    if (String(topic) == String(String(mqtt_username) + "/" + project + "/" + button12_topic)) {
        sendArmActionCommand("9");
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
            // 上身启动流程不控制机械臂，仅复位半身舵机
            
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
            
            // 上身启动流程不控制机械臂，仅复位身体舵机
            
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
        sendArmActionCommand("0"); // 握手
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button1_topic) {
        sendArmActionCommand("1"); // 挥手
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button2_topic) {
        sendArmActionCommand("2"); // 双手挥动
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
            // 整体复位：机械臂先复位，再身体复位
            startFullBodyResetArmFirst();
        }
        return;
    } else if (String(topic) == String(mqtt_username) + "/" + project + "/" + button5_topic) {
        if (!shouldIgnoreDuplicateArmCommand("5")) {
            Serial.println("5");
            markSerialCommandDedup("5");
        }
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

void configureMqttClients() {
    client.setServer(mqtt_broker, mqtt_port);
    client.setCallback(callback);
    client.setSocketTimeout(MQTT_SOCKET_TIMEOUT_SEC);
    client.setKeepAlive(60);

    humanTrackingMqttClient.setServer(human_tracking_mqtt_server, human_tracking_mqtt_port);
    humanTrackingMqttClient.setCallback(humanTrackingCallback);
    humanTrackingMqttClient.setSocketTimeout(MQTT_SOCKET_TIMEOUT_SEC);
    humanTrackingMqttClient.setKeepAlive(60);
    humanTrackingMqttClient.setBufferSize(512);
}

// 本地起身/复位/半身运动期间：网络必须让路，避免 WiFi/MQTT 阻塞导致舵机停顿
bool isLocalMotionBusy() {
    if (standupState != STANDUP_IDLE) {
        return true;
    }
    if (halfBodyState == HALFBODY_MOVING) {
        return true;
    }
    switch (actionQueueState) {
        case ACTION_IDLE:
            return false;
        default:
            return true;
    }
}

bool needsStandupSafetyUltrasonic() {
    return (standupState == STANDUP_START || standupState == STANDUP_PAUSED);
}

void serviceMqttLoopOnly() {
    // 运动中完全跳过，PubSubClient.loop 在弱网时也可能阻塞
    if (isLocalMotionBusy()) {
        return;
    }
    if (client.connected()) {
        client.loop();
    }
    if (humanTrackingMqttClient.connected()) {
        humanTrackingMqttClient.loop();
    }
}

void invokeLocalMqttCommand(const char* buttonName, const String& data) {
    char topic[128];
    sprintf(topic, "%s/%s/%s", mqtt_username, project.c_str(), buttonName);
    callback(topic, (byte*)data.c_str(), data.length());
}

bool tryConnectMainMqtt() {
    if (WiFi.status() != WL_CONNECTED) {
        return false;
    }

    String client_id = "esp-client-";
    client_id += String(WiFi.macAddress());
    if (client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
        subscribeMainMqttTopics();
        return true;
    }
    return false;
}

bool tryConnectHumanTrackingMqtt() {
    if (WiFi.status() != WL_CONNECTED) {
        return false;
    }

    String client_id = "esp32-human-";
    client_id += String(WiFi.macAddress());
    if (humanTrackingMqttClient.connect(client_id.c_str(), human_tracking_mqtt_user, human_tracking_mqtt_password)) {
        subscribeRobotMqttTopics();
        publishRobotOnlineStatus("connected");
        return true;
    }
    return false;
}

void maintainNetworkConnections() {
    // 起身/复位等本地动作优先：不触碰 WiFi/MQTT，彻底消除无网卡顿
    if (isLocalMotionBusy()) {
        return;
    }

    unsigned long now = millis();

    if (WiFi.status() != WL_CONNECTED) {
        wifiDisplayUpdated = false;
        lastMainMqttRetryMs = 0;
        lastHumanMqttRetryMs = 0;
        mainMqttTopicsSubscribed = false;
        lastRobotHeartbeatMs = 0;

        if (!wifiConnectStarted || now - lastWiFiRetryMs >= WIFI_RETRY_INTERVAL_MS) {
            lastWiFiRetryMs = now;
            if (!wifiConnectStarted) {
                WiFi.mode(WIFI_STA);
                WiFi.setSleep(false);
                wifiConnectStarted = true;
            }
            // 先 disconnect 再 begin，避免重复 begin 叠加阻塞
            WiFi.disconnect(false);
            delay(1);
            WiFi.begin("MTCPC", "mt12345mt");
        }
        return;
    }

    if (!wifiDisplayUpdated) {
        wifiDisplayUpdated = true;
        updateDisplayMessage("WiFi OK", WiFi.localIP().toString());
    }

    // 每次只尝试连接一个 MQTT 客户端，把单次最大阻塞限制在约 1 个 socket timeout
    bool needMain = !client.connected();
    bool needHuman = !humanTrackingMqttClient.connected();
    if (needMain || needHuman) {
        bool tryMain = needMain;
        if (needMain && needHuman) {
            tryMain = (mqttConnectTurn % 2 == 0);
            mqttConnectTurn++;
        }

        if (tryMain && needMain &&
            (lastMainMqttRetryMs == 0 || now - lastMainMqttRetryMs >= MQTT_RETRY_INTERVAL_MS)) {
            lastMainMqttRetryMs = now;
            mainMqttTopicsSubscribed = false;
            if (tryConnectMainMqtt()) {
                updateDisplayMessage("MQTT OK", "System Ready");
            }
        } else if (!tryMain && needHuman &&
                   (lastHumanMqttRetryMs == 0 || now - lastHumanMqttRetryMs >= MQTT_RETRY_INTERVAL_MS)) {
            lastHumanMqttRetryMs = now;
            tryConnectHumanTrackingMqtt();
        }
    }

    if (humanTrackingMqttClient.connected()) {
        if (lastRobotHeartbeatMs == 0 || now - lastRobotHeartbeatMs >= ROBOT_HEARTBEAT_INTERVAL_MS) {
            if (publishRobotOnlineStatusChecked("online")) {
                lastRobotHeartbeatMs = now;
            }
        }
    } else {
        lastRobotHeartbeatMs = 0;
    }
}

void subscribeMainMqttTopics() {
    if (mainMqttTopicsSubscribed) {
        return;
    }

    client.subscribe(String(String(mqtt_username) + "/" + project + "/controller").c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button1_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button2_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button3_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button4_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button5_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button6_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button7_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button8_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button9_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button10_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button11_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button12_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button13_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button14_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button15_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button16_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + button17_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + left_90_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + right_90_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + forward_1m_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + retreat_1m_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + body_topic).c_str());
    client.subscribe(String(String(mqtt_username) + "/" + project + "/" + controller_topic).c_str());
    client.subscribe(full_topic.c_str());
    mainMqttTopicsSubscribed = true;
}

void startMainWiFi() {
    updateDisplayMessage("WiFi...", "MTCPC");
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.setAutoReconnect(true);
    WiFi.begin("MTCPC", "mt12345mt");
    wifiConnectStarted = true;
    lastWiFiRetryMs = millis();
}

void setup() {
    pinMode(BUZZER_PIN, OUTPUT);
    buzzerIdle();
    Serial.begin(115200);
    Serial2.begin(115200, SERIAL_8N1, 16, 17);

    shortBeep();

    if (!initDisplay()) {
        longBeep();
    }

    distanceLeft = 0;
    distanceRight = 0;
    rearLeftDistance = 0;
    rearRightDistance = 0;

    pinMode(2, OUTPUT);
    pinMode(4, INPUT);
    pinMode(12, OUTPUT);
    pinMode(14, INPUT);

    initBatteryMonitor();

    initRobotMqttTopics();

#if WAIST_FOLD_SWITCH_CHECK_ENABLED
    initWaistFoldSwitchPins();
    waistFoldSafetyLocked = !areAllWaistFoldSwitchesPressed();
#else
    waistFoldSafetyLocked = false;
#endif

    if (!isWaistFoldSafetyBlocking()) {
        attachBodyServos();
        initBodyServoPositionsToReset();
    } else {
        updateDisplayMessage("Fold Waist", "3 SW Press");
        longBeep();
    }

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

    // 初始化垃圾捡取变量
    garbageTrackingEnabled = false;
    garbagePickupActive = false;
    garbagePickupState = GARBAGE_IDLE;
    garbageTargetDistanceCm = GARBAGE_TARGET_DISTANCE_CM;
    garbageTrackingCommand = 0;
    lastGarbageCommandTime = 0;

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

    configureMqttClients();
    startMainWiFi();
    updateDisplayMessage("Local Ready", "Network retry...");
    buzzer_on();
}

// processSerialData 等后续函数见下方

// 修改点：修复串口接收到"4"时的逻辑
void processSerialData(String data) {
    data.trim();
    if (data.length() == 0) {
        return;
    }

    if (isWaistFoldSafetyBlocking()) {
        return;
    }

    // 忽略机械臂串口回显（MixIO/MQTT 已执行动作后 Serial 可能收到相同指令）
    if (isDuplicateSerialCommand(data)) {
        return;
    }

    if (data == "0") {
        sendArmActionCommand("0");
    } else if (data == "1") {
        sendArmActionCommand("1");
    } else if (data == "2") {
        sendArmActionCommand("2");
    // 离线语音板使用具名命令，避免数字 3/4 被机械臂控制板误当成抬手动作。
    // 保留数字命令，兼容现有的网络和调试控制入口。
    } else if (data == "3" || data == "body_reset") {
        invokeLocalMqttCommand(button3_topic, "3");
    } else if (data == "4" || data == "body_stand") {
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
        invokeLocalMqttCommand(button5_topic, "5");
    } else if (data == "6") {
        button6_state = true;
        syncUltrasonicReceiving();
        syncChassisAutonomousAvoidance();
        moveTopicAllowed = false;
        lastUltrasonicSendTime = 0;
        shortBeep();
        garbageTrackingEnabled = true;
        garbagePickupState = GARBAGE_TRACKING;
        garbagePickupActive = true;
        if (humanTrackingMqttClient.connected()) {
            String modeMsg = String("{\"enabled\":true,\"target_distance_cm\":") +
                             String(garbageTargetDistanceCm) + ",\"robot_id\":\"" + String(ROBOT_ID) + "\"}";
            humanTrackingMqttClient.publish(robotStatusGarbageMode.c_str(), modeMsg.c_str());
        }
    } else if (data == "7") {
        Serial2.println("S");
        button6_state = false;
        syncUltrasonicReceiving();
        syncChassisAutonomousAvoidance();
        moveTopicAllowed = true;
        shortBeep();
        shortBeep();
        garbageTrackingEnabled = false;
        garbagePickupState = GARBAGE_IDLE;
        garbagePickupActive = false;
        if (humanTrackingMqttClient.connected()) {
            humanTrackingMqttClient.publish(robotStatusGarbageMode.c_str(), (String("{\"enabled\":false,\"robot_id\":\"") + ROBOT_ID + "\"}").c_str());
        }
    } else if (data == "8") {
        // 接收到8，发送8到串口2
        Serial2.println("8");
    } else if (data == "9") {
        // 接收到9，发送9到串口2
        Serial2.println("9");
    } else if (data == "A") {
        // 接收到A，开启语音控制功能并启动超声波检测
        voiceControlEnabled = true;
        button8_state = true;
        syncUltrasonicReceiving();
        syncChassisAutonomousAvoidance();
        lastUltrasonicSendTime = 0;
        Serial2.println("A");
        shortBeep(); // 短蜂鸣提示开启
    } else if (data == "B") {
        // 接收到B，关闭语音控制功能
        voiceControlEnabled = false;
        button8_state = false;
        currentCommand = 0;
        commandStartTime = 0;
        Serial2.println("S");
        Serial2.println("B");
        syncUltrasonicReceiving();
        syncChassisAutonomousAvoidance();
        shortBeep(); // 短蜂鸣提示关闭
        shortBeep();
    } else if (data == "C") {
        sendArmActionCommand("3"); // 抬手
    } else if (data == "D") {
        sendArmActionCommand("4"); // 双手抬起
    } else if (data == "E") {
        sendArmActionCommand("8"); // 叉腰
    } else if (data == "F") {
        sendArmActionCommand("9"); // 放手
    } else if (data == "G") {
        // 接收到G，开启人体跟踪功能
        humanTrackingEnabled = true;
        humanTrackingActive = true;
        humanTrackingButtonState = true;
        longBeep(); // 长蜂鸣提示开启
        
        // 发布人体跟踪状态
        if (humanTrackingMqttClient.connected()) {
            publishRobotOnlineStatus("tracking_active");
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
            publishRobotOnlineStatus("tracking_inactive");
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
            // 上身启动流程不控制机械臂，仅复位半身舵机
            
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
            invokeLocalMqttCommand(button13_topic, "13");
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
        invokeLocalMqttCommand(button15_topic, "15");
    } else if (data == "13") {
        // 接收到13，触发半身复位
        invokeLocalMqttCommand(button16_topic, "16");
    } else if (data == "15") {
        sendArmActionCommand("G"); // 跳舞
        return;
    } else if (data == "a" || data == "b" || data == "c" || data == "d" || data == "e") {
        // 只有在语音控制开启时才处理a,b,c,d,e指令
        if (voiceControlEnabled) {
            if (data == "e") {
                finishPresetMotion(false);
                longBeep();
                return;
            }

            requestPresetMotion(data.charAt(0));
        }
    }
}


void loop() {
    const bool motionBusy = isLocalMotionBusy();

    // 非运动时才做 MQTT 保活；运动中网络必须让路给舵机
    if (!motionBusy) {
        serviceMqttLoopOnly();
    }

    // 优先处理语音/串口指令，一次读完缓冲区避免丢字节
    while (Serial.available() > 0) {
        int serialChar = Serial.read();
        if (serialChar == '\n' || serialChar == '\r') {
            if (serialData.length() > 0) {
                processSerialData(serialData);
                serialData = "";
            }
        } else if (serialChar >= 0) {
            serialData += (char)serialChar;
        }
    }

    // 超声波：起身安全检测时用完整超时；其余场景降频+短超时，减少无回波阻塞
    unsigned long nowMs = millis();
    bool needSafetyUs = needsStandupSafetyUltrasonic();
    bool needVoiceUs = ((voiceControlEnabled || presetMotionSafetyEnabled) &&
                        (currentCommand != 0 || presetMotionPending != 0) &&
                        ultrasonicDataReceiving);
    unsigned long usInterval = needSafetyUs ? 40UL : ULTRASONIC_IDLE_INTERVAL_MS;
    if (needSafetyUs || needVoiceUs || (nowMs - lastUltrasonicSampleMs >= usInterval)) {
        lastUltrasonicSampleMs = nowMs;
        unsigned long usTimeout = needSafetyUs ? ULTRASONIC_PULSE_TIMEOUT_US : ULTRASONIC_PULSE_TIMEOUT_FAST_US;
        distanceLeft = checkDistance(2, 4, usTimeout);
        distanceRight = checkDistance(12, 14, usTimeout);
        rearLeftDistance = (int)distanceLeft;
        rearRightDistance = (int)distanceRight;
    }
    updateStatusLed();

    // 如果超声波数据接收开启，处理串口2的数据（每轮限制字节数，避免长时间占用）
    if (ultrasonicDataReceiving) {
        int serial2Budget = motionBusy ? 64 : 128;
        while (Serial2.available() > 0 && serial2Budget-- > 0) {
            char c = Serial2.read();
            if (c == '\n' || c == '\r') {
                if (serial2Data.length() > 0) {
                    parseUltrasonicData(serial2Data);
                    serial2Data = "";
                }
            } else {
                serial2Data += c;
            }
        }
    }

    processPresetMotionState();

    // 运动中持续检测超声波避障（先解析Serial2超声波，再判断）
    if ((voiceControlEnabled || presetMotionSafetyEnabled) &&
        currentCommand != 0 && ultrasonicDataReceiving) {
        if (isMotionDirectionBlocked(currentCommand)) {
            finishPresetMotion(true);
        }
    }

    if (!motionBusy) {
        updateBatteryMonitor();
    }

    // OLED 降频刷新，避免每圈 I2C 全屏刷新拖慢舵机
    if (nowMs - lastDisplayRefreshMs >= DISPLAY_REFRESH_INTERVAL_MS) {
        lastDisplayRefreshMs = nowMs;
        u8g2.firstPage();
        do {
#if WAIST_FOLD_SWITCH_CHECK_ENABLED
            if (isWaistFoldSafetyBlocking()) {
                displayWaistFoldLocked();
            } else {
                displayDistances();
                if (standupState != STANDUP_IDLE) {
                    if (distanceLeft < MIN_SAFE_DISTANCE || distanceRight < MIN_SAFE_DISTANCE) {
                        displayStop();
                    } else {
                        displayStart();
                    }
                }
            }
#else
            displayDistances();
            if (standupState != STANDUP_IDLE) {
                if (distanceLeft < MIN_SAFE_DISTANCE || distanceRight < MIN_SAFE_DISTANCE) {
                    displayStop();
                } else {
                    displayStart();
                }
            }
#endif
        } while (u8g2.nextPage());
    }

#if WAIST_FOLD_SWITCH_CHECK_ENABLED
    updateWaistFoldSafety();
#endif

    if (isWaistFoldSafetyBlocking()) {
        if (!motionBusy) {
            maintainNetworkConnections();
            serviceMqttLoopOnly();
        }
        return;
    }

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
    if (currentCommand != 0 && millis() - commandStartTime >= currentCommandDuration) {
        finishPresetMotion(false);
    }
    
    // 处理人体跟踪命令超时
    if (humanTrackingActive && humanTrackingCommand != 0 && millis() - lastHumanTrackingTime > HUMAN_TRACKING_TIMEOUT) {
        // 1秒内没有收到新的跟踪指令，发送停止指令
        Serial2.println("S");
        humanTrackingCommand = 0;
    }

    // 后台非阻塞重连 WiFi / MQTT（运动中内部会直接 return）
    maintainNetworkConnections();
    if (!motionBusy) {
        serviceMqttLoopOnly();
        processGarbagePickupStateMachine();
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
            lockAllBodyServosAtTarget(); // 锁定所有舵机，停止PID避免抖动
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
                actionDelayUntilMs = millis() + 1000;
                actionQueueState = ACTION_DELAY_THEN_UPPER;
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
            // 复位完成
            if (lastTriggeredButton == 13 || lastTriggeredButton == 15) {
                // 半身/上身流程：短暂等待后再执行后续动作
                actionDelayUntilMs = millis() + 500;
                actionQueueState = ACTION_WAITING;
            } else {
                // 整体复位完成
                actionQueueState = ACTION_IDLE;
                lastTriggeredButton = 0;
                shortBeep();
            }
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
            
            // 非阻塞等待整体复位稳定后再起身
            actionDelayUntilMs = millis() + 1000;
            actionQueueState = ACTION_DELAY_THEN_STANDUP;
        }
    }
    else if (actionQueueState == ACTION_RESETTING_FOR_UPPER) {
        // 检查半身复位是否完成（等待半身复位状态机完成）
        if (halfBodyState == HALFBODY_IDLE) {
            // 半身复位完成，现在执行整体复位（不控制机械臂）
            
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
            
            // 非阻塞等待整体复位稳定后再上身启动
            actionDelayUntilMs = millis() + 1000;
            actionQueueState = ACTION_DELAY_THEN_UPPER;
        }
    }
    else if (actionQueueState == ACTION_DELAY_THEN_STANDUP) {
        if (millis() >= actionDelayUntilMs) {
            actionQueueState = ACTION_IDLE;
            standupState = STANDUP_START_GPIO;
            controlGpioServos(true);
        }
    }
    else if (actionQueueState == ACTION_DELAY_THEN_UPPER) {
        if (millis() >= actionDelayUntilMs) {
            beginUpperBodyStandup();
        }
    }
    else if (actionQueueState == ACTION_WAITING_ARM_THEN_BODY_RESET) {
        // 机械臂复位等待中：身体先不动，时间到后再复位身体舵机
        if (millis() >= actionDelayUntilMs) {
            beginBodyServoResetAfterArm();
        }
    }
    else if (actionQueueState == ACTION_WAITING) {
        // 等待完成，现在根据触发的按钮执行相应的动作
        if (millis() < actionDelayUntilMs) {
            // 稳定等待中，继续后续舵机 PID
        } else if (lastTriggeredButton == 13) {  // 上身启动
            beginUpperBodyStandup();
            
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
            lockAllBodyServosAtTarget();
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
            lockAllBodyServosAtTarget();
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

    // 定义到位判定阈值（到位后停止PID，避免持续微调导致抖动）
    const float tolerance = servo_settle_threshold;

    if (currentMillis - previousMillis >= interval) {
        float deltaT = (currentMillis - previousMillis) / 1000.0; // 计算时间差（秒）
        if (deltaT < 0.008f) deltaT = interval / 1000.0f; // 防止微分项因时间过短而放大
        previousMillis = currentMillis;

        // 舵机0更新逻辑
        if (update_servo0) {
            error0 = servo0_angle - current_servo0_angle;
            
            if (fabs(error0) < tolerance) {
                current_servo0_angle = servo0_angle;
                integral0 = 0;
                prev_error0 = 0;
                update_servo0 = false;
            } else {
                integral0 += error0 * deltaT;
                integral0 = constrain(integral0, -integral_max, integral_max);
                float derivative0 = (error0 - prev_error0) / deltaT;
                prev_error0 = error0;

                float output0 = Kp * error0 + Ki * integral0 + Kd * derivative0;
                output0 = constrain(output0, -maxStep, maxStep);

                current_servo0_angle += output0;
                current_servo0_angle = constrain(current_servo0_angle, servo0_min_angle, servo0_max_angle);
            }
            writeServoIfChanged(servo_0, 0, current_servo0_angle);
        }

        // 舵机1更新逻辑
        if (update_servo1) {
            error1 = servo1_angle - current_servo1_angle;
            if (fabs(error1) < tolerance) {
                current_servo1_angle = servo1_angle;
                integral1 = 0;
                prev_error1 = 0;
                update_servo1 = false;
            } else {
                integral1 += error1 * deltaT;
                integral1 = constrain(integral1, -integral_max, integral_max);
                float derivative1 = (error1 - prev_error1) / deltaT;
                prev_error1 = error1;

                float output1 = Kp * error1 + Ki * integral1 + Kd * derivative1;
                output1 = constrain(output1, -maxStep, maxStep);

                current_servo1_angle += output1;
                current_servo1_angle = constrain(current_servo1_angle, servo1_min_angle, servo1_max_angle);
            }
            writeServoIfChanged(servo_1, 1, current_servo1_angle);
        }

        // 舵机2更新逻辑
        if (update_servo2) {
            error2 = servo2_angle - current_servo2_angle;
            if (fabs(error2) < tolerance) {
                current_servo2_angle = servo2_angle;
                integral2 = 0;
                prev_error2 = 0;
                update_servo2 = false;
            } else {
                integral2 += error2 * deltaT;
                integral2 = constrain(integral2, -integral_max, integral_max);
                float derivative2 = (error2 - prev_error2) / deltaT;
                prev_error2 = error2;

                float output2 = Kp * error2 + Ki * integral2 + Kd * derivative2;
                output2 = constrain(output2, -maxStep, maxStep);

                current_servo2_angle += output2;
                current_servo2_angle = constrain(current_servo2_angle, servo2_min_angle, servo2_max_angle);
            }
            writeServoIfChanged(servo_2, 2, current_servo2_angle);
        }

        // 舵机3更新逻辑
        if (update_servo3) {
            error3 = servo3_angle - current_servo3_angle;
            if (fabs(error3) < tolerance) {
                current_servo3_angle = servo3_angle;
                integral3 = 0;
                prev_error3 = 0;
                update_servo3 = false;
            } else {
                integral3 += error3 * deltaT;
                integral3 = constrain(integral3, -integral_max, integral_max);
                float derivative3 = (error3 - prev_error3) / deltaT;
                prev_error3 = error3;

                float output3 = Kp_34 * Kp * error3 + Ki * integral3 + Kd * derivative3;
                output3 = constrain(output3, -maxStep_3456, maxStep_3456);

                current_servo3_angle += output3;
                current_servo3_angle = constrain(current_servo3_angle, servo3_min_angle, servo3_max_angle);
            }
            writeServoIfChanged(servo_3, 3, current_servo3_angle);
        }

        // 舵机4更新逻辑
        if (update_servo4) {
            error4 = servo4_angle - current_servo4_angle;
            if (fabs(error4) < tolerance) {
                current_servo4_angle = servo4_angle;
                integral4 = 0;
                prev_error4 = 0;
                update_servo4 = false;
            } else {
                integral4 += error4 * deltaT;
                integral4 = constrain(integral4, -integral_max, integral_max);
                float derivative4 = (error4 - prev_error4) / deltaT;
                prev_error4 = error4;

                float output4 = Kp_34 * Kp * error4 + Ki * integral4 + Kd * derivative4;
                output4 = constrain(output4, -maxStep_3456, maxStep_3456);

                current_servo4_angle += output4;
                current_servo4_angle = constrain(current_servo4_angle, servo4_min_angle, servo4_max_angle);
            }
            writeServoIfChanged(servo_4, 4, current_servo4_angle);
        }

            // 舵机5更新逻辑
        if (update_servo5) {
            error5 = servo5_angle - current_servo5_angle;
            if (fabs(error5) < tolerance) {
                current_servo5_angle = servo5_angle;
                integral5 = 0;
                prev_error5 = 0;
                update_servo5 = false;
            } else {
                integral5 += error5 * deltaT;
                integral5 = constrain(integral5, -integral_max, integral_max);
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
            writeServoIfChanged(servo_5, 5, current_servo5_angle);
        }

        // 舵机6更新逻辑
        if (update_servo6) {
            error6 = servo6_angle - current_servo6_angle;
            if (fabs(error6) < tolerance) {
                current_servo6_angle = servo6_angle;
                integral6 = 0;
                prev_error6 = 0;
                update_servo6 = false;
            } else {
                integral6 += error6 * deltaT;
                integral6 = constrain(integral6, -integral_max, integral_max);
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
            writeServoIfChanged(servo_6, 6, current_servo6_angle);
        }

        // 新增：GPIO5舵机更新逻辑
        if (update_servo_gpio5) {
            error_gpio5 = servo_gpio5_angle - current_servo_gpio5_angle;
            if (fabs(error_gpio5) < tolerance) {
                current_servo_gpio5_angle = servo_gpio5_angle;
                integral_gpio5 = 0;
                prev_error_gpio5 = 0;
                update_servo_gpio5 = false;
            } else {
                integral_gpio5 += error_gpio5 * deltaT;
                integral_gpio5 = constrain(integral_gpio5, -integral_max, integral_max);
                float derivative_gpio5 = (error_gpio5 - prev_error_gpio5) / deltaT;
                prev_error_gpio5 = error_gpio5;

                // 使用专门为GPIO舵机设置的更快参数
                float output_gpio5 = Kp_gpio * error_gpio5 + Ki * integral_gpio5 + Kd * derivative_gpio5;
                output_gpio5 = constrain(output_gpio5, -maxStep_gpio, maxStep_gpio);

                current_servo_gpio5_angle += output_gpio5;
                current_servo_gpio5_angle = constrain(current_servo_gpio5_angle, servo_gpio5_min_angle, servo_gpio5_max_angle);
            }
            writeServoIfChanged(servo_gpio5, 7, current_servo_gpio5_angle);
        }

        // 新增：GPIO15舵机更新逻辑
        if (update_servo_gpio15) {
            error_gpio15 = servo_gpio15_angle - current_servo_gpio15_angle;
            if (fabs(error_gpio15) < tolerance) {
                current_servo_gpio15_angle = servo_gpio15_angle;
                integral_gpio15 = 0;
                prev_error_gpio15 = 0;
                update_servo_gpio15 = false;
            } else {
                integral_gpio15 += error_gpio15 * deltaT;
                integral_gpio15 = constrain(integral_gpio15, -integral_max, integral_max);
                float derivative_gpio15 = (error_gpio15 - prev_error_gpio15) / deltaT;
                prev_error_gpio15 = error_gpio15;

                // 使用专门为GPIO舵机设置的更快参数
                float output_gpio15 = Kp_gpio * error_gpio15 + Ki * integral_gpio15 + Kd * derivative_gpio15;
                output_gpio15 = constrain(output_gpio15, -maxStep_gpio, maxStep_gpio);

                current_servo_gpio15_angle += output_gpio15;
                current_servo_gpio15_angle = constrain(current_servo_gpio15_angle, servo_gpio15_min_angle, servo_gpio15_max_angle);
            }
            writeServoIfChanged(servo_gpio15, 8, current_servo_gpio15_angle);
        }
    }

    updateStatusLed();
}
