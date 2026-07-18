#include <WiFi.h>
#include <WiFiClientSecure.h>   // 新增：支持 TLS 的客户端
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi配置
const char* ssid = "MTCPC";
const char* password = "mt12345mt";

// EMQX 云端服务器配置（修改点）
const char* mqtt_server = "n11f196b.ala.eu-central-1.emqxsl.com";  // 你的 EMQX 实例地址
const int mqtt_port = 8883;                                        // TLS 加密端口
const char* mqtt_user = "no_1";                                    // 你在 EMQX 创建的用户名
const char* mqtt_password = "123";                                 // 对应的密码

// MQTT主题（保持不变）
const char* camera_control_topic = "camera_control";
const char* openmv_status_topic = "openmv/status";
const char* recognition_result_topic = "openmv_recognition_result";
const char* flask_control_topic = "flask/control";
const char* face_collection_status_topic = "face_collection_status";

// 使用 WiFiClientSecure 替代 WiFiClient
WiFiClientSecure espClient;
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

void setup() {
  Serial.begin(115200);
  delay(2000);
  
  setup_wifi();
  
  // 设置 TLS 客户端：跳过证书验证（简化部署，与 OpenMV 一致）
  espClient.setInsecure();
  
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  
  system_start_time = millis();
}

void setup_wifi() {
  delay(10);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    attempts++;
  }
}

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
            // 检查是否包含识别的ID
            if (doc.containsKey("recognized_ids") && doc["recognized_ids"].is<JsonArray>()) {
                JsonArray ids = doc["recognized_ids"];
                if (ids.size() > 0) {
                    // 只输出第一个ID的三位数字
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
  
  if (client.connect(clientId.c_str(), mqtt_user, mqtt_password)) {
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
