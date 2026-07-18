#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ======== 配置区域 ======== //
const char* ssid = "MTCPC";
const char* password = "mt12345mt";
const char* apiKey = "sk-fd879e401c3a49a38b857ee4509451ef";  // 从DeepSeek官网获取

// 串口设置
#define SERIAL_BAUDRATE 115200
#define USER_INPUT_TIMEOUT 30000  // 用户输入超时时间(毫秒)

// DeepSeek API设置
const char* apiEndpoint = "https://api.deepseek.com/v1/chat/completions";
const char* modelName = "deepseek-chat";  // 使用DeepSeek聊天模型
// ======================== //

// 全局变量
String inputBuffer = "";
bool newDataAvailable = false;

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  delay(1000);
  
  // 连接WiFi
  WiFi.begin(ssid, password);
  Serial.print("连接到WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n连接成功!");
  Serial.print("IP地址: ");
  Serial.println(WiFi.localIP());
  
  Serial.println("\n====== DeepSeek 对话系统 ======");
  Serial.println("输入你的问题后按回车发送");
  Serial.println("输入'clear'清除对话历史");
  Serial.println("=============================");
}

void loop() {
  // 1. 检查串口输入
  checkSerialInput();
  
  // 2. 如果有新数据，处理请求
  if (newDataAvailable) {
    if (inputBuffer.equalsIgnoreCase("clear")) {
      Serial.println("对话历史已清除");
    } else {
      Serial.println("\n思考中...");
      String response = getAIResponse(inputBuffer);
      Serial.println("助手: " + response);
    }
    
    // 重置标志
    newDataAvailable = false;
    inputBuffer = "";
    Serial.print("\n你: ");
  }
}

// 检查串口输入
void checkSerialInput() {
  static unsigned long inputStartTime = millis();
  
  while (Serial.available()) {
    char c = Serial.read();
    
    // 检查超时
    if (millis() - inputStartTime > USER_INPUT_TIMEOUT) {
      inputBuffer = "";
      break;
    }
    
    if (c == '\n') {
      newDataAvailable = true;
      inputStartTime = millis();
      return;
    } else if (c != '\r') {  // 忽略回车符
      inputBuffer += c;
    }
    
    delay(1);  // 稳定读取
  }
}

// 获取AI回复
String getAIResponse(String userInput) {
  HTTPClient http;
  http.begin(apiEndpoint);
  
  // 设置HTTP头
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + apiKey);
  
  // 构建JSON请求
  DynamicJsonDocument doc(1024);
  doc["model"] = modelName;
  
  JsonArray messages = doc.createNestedArray("messages");
  JsonObject systemMessage = messages.createNestedObject();
  systemMessage["role"] = "system";
  systemMessage["content"] = "你是一个有帮助的AI助手";
  
  JsonObject userMessage = messages.createNestedObject();
  userMessage["role"] = "user";
  userMessage["content"] = userInput;
  
  // 序列化JSON
  String requestBody;
  serializeJson(doc, requestBody);
  
  // 发送POST请求
  int httpCode = http.POST(requestBody);
  
  // 处理响应
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    
    // 解析JSON响应
    DynamicJsonDocument responseDoc(2048);
    deserializeJson(responseDoc, payload);
    
    String aiResponse = responseDoc["choices"][0]["message"]["content"].as<String>();
    aiResponse.trim();  // 移除首尾空白
    
    http.end();
    return aiResponse;
  } else {
    http.end();
    Serial.print("API错误: ");
    Serial.println(httpCode);
    return "抱歉，请求失败 (错误代码: " + String(httpCode) + ")";
  }
}
