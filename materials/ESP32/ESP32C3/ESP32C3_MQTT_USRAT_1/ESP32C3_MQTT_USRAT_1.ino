#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>

// ========== 函数原型声明 ==========
void callback(char* topic, byte* payload, unsigned int length);
void send_command_with_ack(char command);
void check_command_timeout();
void process_command_queue();
bool enqueue_command(char command);
char dequeue_command();
void clear_mqtt_retained_messages();
void setup_wifi();
bool reconnect();

// ========== 配置存储 ==========
Preferences preferences;
const char* prefs_namespace = "robot_config";

// 默认配置（当 NVS 无配置时使用）
String wifi_ssid = "MTCPC";
String wifi_password = "mt12345mt";
String mqtt_server = "192.168.13.225";
int mqtt_port = 1883;
String mqtt_user = "sy";
String mqtt_password = "123";

// MQTT主题
const char* camera_control_topic = "camera_control";
const char* openmv_status_topic = "openmv/status";
const char* recognition_result_topic = "openmv_recognition_result";
const char* flask_control_topic = "flask/control";
const char* face_collection_status_topic = "face_collection_status";

WiFiClient espClient;
PubSubClient client(espClient);

// 状态变量
int camera_state = 0;
bool last_was_zero = false;

// 命令确认机制
struct Command {
  char value;
  unsigned long send_time;
  int retry_count;
  bool waiting_ack;
};

const int MAX_RETRIES = 3;
const unsigned long COMMAND_TIMEOUT = 1000;
Command current_command = {'\0', 0, 0, false};
unsigned long last_status_time = 0;
const unsigned long STATUS_TIMEOUT = 5000;

// 命令队列
const int QUEUE_SIZE = 10;
char command_queue[QUEUE_SIZE];
int queue_front = 0;
int queue_rear = 0;
int queue_count = 0;

// 防重复发送机制
unsigned long last_sent_command_time = 0;
const unsigned long COMMAND_MIN_INTERVAL = 1000;
char last_sent_command = '\0';

// 启动标记
bool system_initialized = false;
unsigned long system_start_time = 0;
const unsigned long INITIAL_DELAY = 5000;

// 防止循环的标记
bool processing_status_response = false;

// ========== 加载配置 ==========
void load_config() {
  preferences.begin(prefs_namespace, false);

  wifi_ssid = preferences.getString("ssid", wifi_ssid);
  wifi_password = preferences.getString("password", wifi_password);
  mqtt_server = preferences.getString("mqtt_server", mqtt_server);
  mqtt_port = preferences.getInt("mqtt_port", mqtt_port);
  mqtt_user = preferences.getString("mqtt_user", mqtt_user);
  mqtt_password = preferences.getString("mqtt_pass", mqtt_password);

  preferences.end();

  Serial.println("load already:");
  Serial.println("  SSID: " + wifi_ssid);
  Serial.println("  MQTT Server: " + mqtt_server + ":" + String(mqtt_port));
}

// ========== 保存配置 ==========
void save_config() {
  preferences.begin(prefs_namespace, false);
  preferences.putString("ssid", wifi_ssid);
  preferences.putString("password", wifi_password);
  preferences.putString("mqtt_server", mqtt_server);
  preferences.putInt("mqtt_port", mqtt_port);
  preferences.putString("mqtt_user", mqtt_user);
  preferences.putString("mqtt_pass", mqtt_password);
  preferences.end();
  Serial.println(" message save to NVS");
}

// ========== 串口配置模式（支持回退和退出） ==========
void enter_config_mode() {
    // 清空串口缓冲区
    while (Serial.available()) Serial.read();

    Serial.println("\nEnter configuration mode:");
    Serial.println("Commands: Enter to keep, type new value and Enter to change, 'q' to go back, 'exit' to quit.");

    // 定义配置项
    struct ConfigItem {
        const char* prompt;
        void* valuePtr;
        bool isInt;
        String defaultValueStr;
    };

    ConfigItem items[] = {
        {"WiFi SSID", &wifi_ssid, false, wifi_ssid},
        {"WiFi Password", &wifi_password, false, wifi_password},
        {"MQTT Server", &mqtt_server, false, mqtt_server},
        {"MQTT Port", &mqtt_port, true, String(mqtt_port)},
        {"MQTT Username", &mqtt_user, false, mqtt_user},
        {"MQTT Password", &mqtt_password, false, mqtt_password}
    };
    const int itemCount = sizeof(items) / sizeof(items[0]);

    int currentIndex = 0;
    while (currentIndex < itemCount) {
        // 显示当前项的提示
        Serial.print(items[currentIndex].prompt);
        Serial.print(" [");
        Serial.print(items[currentIndex].defaultValueStr);
        Serial.print("]: ");

        // 等待输入一行
        while (!Serial.available()) {}
        String input = Serial.readStringUntil('\n');
        input.trim();

        if (input.equalsIgnoreCase("exit")) {
            Serial.println("Configuration exited. Returning to normal startup.");
            return; // 退出配置，不保存
        }
        else if (input.equalsIgnoreCase("q")) {
            if (currentIndex > 0) {
                currentIndex--; // 回退到上一项
                continue;
            } else {
                Serial.println("Already at first item, cannot go back.");
                continue; // 重新提示当前项
            }
        }
        else {
            // 处理输入值
            if (input.length() > 0) {
                // 有新值
                if (items[currentIndex].isInt) {
                    int* intPtr = (int*)items[currentIndex].valuePtr;
                    *intPtr = input.toInt();
                    items[currentIndex].defaultValueStr = String(*intPtr);
                } else {
                    String* strPtr = (String*)items[currentIndex].valuePtr;
                    *strPtr = input;
                    items[currentIndex].defaultValueStr = *strPtr;
                }
                Serial.print("Set to: ");
                Serial.println(input);
            } else {
                // 保留原值
                Serial.print("Keep: ");
                if (items[currentIndex].isInt) {
                    Serial.println(*(int*)items[currentIndex].valuePtr);
                } else {
                    Serial.println(*(String*)items[currentIndex].valuePtr);
                }
            }
            // 前进到下一项
            currentIndex++;
        }
    }

    // 所有项配置完成，打印最终配置
    Serial.println("\nFinal configuration:");
    Serial.println("  WiFi SSID: " + wifi_ssid);
    Serial.println("  WiFi Password: " + wifi_password);
    Serial.println("  MQTT Server: " + mqtt_server);
    Serial.println("  MQTT Port: " + String(mqtt_port));
    Serial.println("  MQTT Username: " + mqtt_user);
    Serial.println("  MQTT Password: " + mqtt_password);

    save_config();
    Serial.println("Configuration successful finished! Restarting...");
    delay(1000);
    ESP.restart();
}

// ========== 设置 WiFi ==========
void setup_wifi() {
  delay(10);
  WiFi.begin(wifi_ssid.c_str(), wifi_password.c_str());

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WIFI CONNECT SUCCESSFUL!");
  } else {
    Serial.println("❌ WiFi CONNECT FAILD!");
  }
}

void setup() {
  Serial.begin(115200);
  delay(2000);

  load_config();

  Serial.println("Press 'C' to enter configuration mode (5s window)...");
  unsigned long timeout = millis() + 5000;
  while (millis() < timeout) {
    if (Serial.available()) {
      char c = Serial.read();
      if (c == 'C' || c == 'c') {
        enter_config_mode();
        break;
      }
    }
    delay(100);
  }

  setup_wifi();

  client.setServer(mqtt_server.c_str(), mqtt_port);
  client.setCallback(callback);

  system_start_time = millis();
}

// ========== 以下函数保持不变 ==========

void clear_mqtt_retained_messages() {
  if (client.connected()) {
    client.publish(camera_control_topic, "", true);
    delay(100);
  }
}

bool enqueue_command(char command) {
  if (!system_initialized) {
    return false;
  }
  
  if (queue_count > 0) {
    for (int i = 1; i <= 3 && i <= queue_count; i++) {
      int index = (queue_rear - i + QUEUE_SIZE) % QUEUE_SIZE;
      if (command_queue[index] == command) {
        return false;
      }
    }
  }
  
  if (queue_count >= QUEUE_SIZE) {
    return false;
  }
  
  command_queue[queue_rear] = command;
  queue_rear = (queue_rear + 1) % QUEUE_SIZE;
  queue_count++;
  
  return true;
}

char dequeue_command() {
  if (queue_count <= 0) {
    return '\0';
  }
  
  char command = command_queue[queue_front];
  queue_front = (queue_front + 1) % QUEUE_SIZE;
  queue_count--;
  
  return command;
}

void process_command_queue() {
  unsigned long current_time = millis();
  
  if (!system_initialized) {
    if (current_time - system_start_time > INITIAL_DELAY) {
      system_initialized = true;
      clear_mqtt_retained_messages();
    } else {
      return;
    }
  }
  
  if (current_time - last_sent_command_time < COMMAND_MIN_INTERVAL) {
    return;
  }
  
  if (!current_command.waiting_ack && queue_count > 0) {
    char next_command = dequeue_command();
    
    if (next_command == last_sent_command) {
      return;
    }
    
    send_command_with_ack(next_command);
    last_sent_command = next_command;
    last_sent_command_time = current_time;
  }
}

void send_command_with_ack(char command) {
  if (!client.connected()) {
    return;
  }

  current_command.value = command;
  current_command.send_time = millis();
  current_command.retry_count = 0;
  current_command.waiting_ack = true;
  
  client.publish(camera_control_topic, &command, 1);
}

void check_command_timeout() {
  if (!current_command.waiting_ack) {
    return;
  }
  
  unsigned long current_time = millis();
  if (current_time - current_command.send_time > COMMAND_TIMEOUT) {
    current_command.retry_count++;
    
    if (current_command.retry_count >= MAX_RETRIES) {
      current_command.waiting_ack = false;
    } else {
      current_command.send_time = current_time;
      client.publish(camera_control_topic, &current_command.value, 1);
    }
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
    String topic_str = String(topic);
    
    String message;
    for (unsigned int i = 0; i < length; i++) {
        message += (char)payload[i];
    }
    
    // 处理人脸采集状态消息
    if (topic_str == face_collection_status_topic) {
        DynamicJsonDocument doc(256);
        DeserializationError error = deserializeJson(doc, message);
        
        if (!error && doc.containsKey("status")) {
            int status = doc["status"];
            Serial.print(status);
        }
        return;
    }

    // 处理识别结果 - 只输出三位ID
    if (String(topic) == recognition_result_topic) {
        DynamicJsonDocument doc(1024);
        DeserializationError error = deserializeJson(doc, message);
        
        if (!error) {
            if (doc.containsKey("recognized_ids") && doc["recognized_ids"].is<JsonArray>()) {
                JsonArray ids = doc["recognized_ids"];
                if (ids.size() > 0) {
                    String faceId = ids[0].as<String>();
                    if (faceId.length() == 3) {
                        Serial.print(faceId);
                    }
                }
            }
        }
        return;
    }
    
    // 处理OpenMV状态消息
    if (topic_str == openmv_status_topic) {
        last_status_time = millis();
        
        DynamicJsonDocument doc(1024);
        DeserializationError error = deserializeJson(doc, message);
        
        if (!error) {
            bool is_command_response = doc.containsKey("is_command_response") && doc["is_command_response"] == true;
            
            if (is_command_response && doc.containsKey("command_received")) {
                String received_command = doc["command_received"];
                
                if (current_command.waiting_ack && 
                    received_command.length() == 1 && 
                    current_command.value == received_command[0]) {
                
                    current_command.waiting_ack = false;
                    current_command.value = '\0';
                }
            }
        }
        return;
    }
}

bool reconnect() {
  String clientId = "ESP32C3-";
  clientId += String(random(0xffff), HEX);
  
  if (client.connect(clientId.c_str(), mqtt_user.c_str(), mqtt_password.c_str())) {
    client.subscribe(openmv_status_topic);
    client.subscribe(recognition_result_topic);
    client.subscribe(flask_control_topic);
    client.subscribe(face_collection_status_topic);
    
    return true;
  }
  return false;
}

void check_serial_input() {
  if (Serial.available() > 0) {
    char input = Serial.read();
    
    if (!system_initialized) {
      while (Serial.available() > 0) Serial.read();
      return;
    }
    
    if (input == 's' || input == 'r') {
      while (Serial.available() > 0) Serial.read();
      return;
    }
    
    if ((input < '0' || input > '9') && input != 'A' && input != 'B') {
      while (Serial.available() > 0) Serial.read();
      return;
    }
    
    if (input == '0') {
      if (last_was_zero && camera_state == 1) {
        camera_state = 3;
        last_was_zero = false;
      } else {
        camera_state = 1;
        last_was_zero = true;
      }
    } else if (input == '1') {
      camera_state = 2;
      last_was_zero = false;
    } else if (input == '2') {
      camera_state = 4;
      last_was_zero = false;
    } else if (input == '3') {
      camera_state = 3;
      last_was_zero = false;
    } else if (input == '6') {
      camera_state = 0;
      last_was_zero = false;
    }
    
    if (enqueue_command(input)) {
      while (Serial.available() > 0) Serial.read();
    }
  }
}

void loop() {
  unsigned long current_time = millis();
  
  if (!client.connected()) {
    reconnect();
  } else {
    client.loop();
  }
  
  check_serial_input();
  check_command_timeout();
  process_command_queue();
  
  delay(50);
}