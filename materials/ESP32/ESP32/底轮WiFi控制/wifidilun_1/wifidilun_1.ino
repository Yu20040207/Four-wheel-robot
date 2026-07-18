#include <WiFi.h>
#include <PubSubClient.h>

// MQTT 配置
const char *mqtt_broker = "mixio.mixly.cn";
const char *mqtt_username = "1593019617@qq.com";
const char *mqtt_password = "45ff8cd983fd9050dc8ad75f50d9a175";
const int mqtt_port = 1883;
const String project = "WiFi控制";

// WiFi 客户端和 MQTT 客户端
WiFiClient espClient;
PubSubClient client(espClient);

// 手柄主题
const char *move_topic = "move";

// 定义完整的订阅主题
const String full_topic = String(mqtt_username) + "/" + project + "/" + move_topic;

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
        if (absValue >= 0 && absValue < 20) return "go1";
        else if (absValue >= 20 && absValue < 40) return "go2";
        else if (absValue >= 40 && absValue < 60) return "go3";
        else if (absValue >= 60 && absValue < 80) return "go4";
        else return "go5";
    } else {
        if (absValue >= 0 && absValue < 20) return "back1";
        else if (absValue >= 20 && absValue < 40) return "back2";
        else if (absValue >= 40 && absValue < 60) return "back3";
        else if (absValue >= 60 && absValue < 80) return "back4";
        else return "back5";
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

void callback(char *topic, byte *payload, unsigned int length) {
    // 将接收到的字节数组转换为字符串
    String data = "";
    for (int i = 0; i < length; i++) {
        data += (char)payload[i];
    }

    // 检查是否是手柄控制主题
    if (String(topic) == full_topic) {
        // 找到逗号的位置
        int commaIndex = data.indexOf(',');
        if (commaIndex != -1) {
            // 提取两个值
            String value1 = data.substring(0, commaIndex);
            String value2 = data.substring(commaIndex + 1);

            // 将两个值取反
            int value1Int = -value1.toInt();
            int value2Int = value2.toInt(); // 第二个值不取反

            // 检查两个值是否都是0
            if (value1Int == 0 && value2Int == 0) {
                Serial.println("stop"); // 发送stop
                return;
            }

            // 转换回字符串
            String value1Neg = String(value1Int);
            String value2Neg = String(value2Int);

            // 调转两个值的位置
            String swappedData = value2Neg + "," + value1Neg;
            
            // 提取处理后的值
            int frontValue = value2Int; // 逗号前面的值（原始第二个值）
            int backValue = value1Int;   // 逗号后面的值（原始第一个值取反）
            
            // 首先检查特殊手势
            String specialGesture = checkSpecialGestures(frontValue, backValue);
            if (specialGesture != "") {
                Serial.println(specialGesture);
                return; // 特殊手势匹配，直接返回不再处理其他逻辑
            }
            
            // 如果没有特殊手势，执行原有逻辑
            if (abs(frontValue) > abs(backValue)) {
                // 逗号前面的数据绝对值更大
                Serial.println(getDirectionString(frontValue));
            } else {
                // 逗号后面的数据绝对值更大或相等
                Serial.println(getOutputString(backValue));
            }
        } else {
            // 如果没有找到逗号，直接输出原始数据
            Serial.println(data);
        }
    }
}

void setup() {
    // 连接到WiFi
    WiFi.begin("MTCPC", "mt12345mt");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
    }

    // 初始化串口通信
    Serial.begin(9600);

    // 设置MQTT服务器和回调函数
    client.setServer(mqtt_broker, mqtt_port);
    client.setCallback(callback);

    // 构建客户端ID
    String client_id = "esp-client-" + String(WiFi.macAddress());
    while (!client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
        Serial.print("MQTT connection failed with state ");
        Serial.print(client.state());
        delay(2000);
    }
    Serial.println("Connected to MQTT broker");

    // 订阅手柄控制主题
    client.subscribe(full_topic.c_str());
}

void loop() {
    // 检查MQTT连接是否断开
    if (!client.connected()) {
        // 重新连接
        String client_id = "esp-client-" + String(WiFi.macAddress());
        if (client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
            Serial.println("Reconnected to MQTT broker");
            client.subscribe(full_topic.c_str());
        }
    }

    // 处理MQTT消息
    client.loop();
}
