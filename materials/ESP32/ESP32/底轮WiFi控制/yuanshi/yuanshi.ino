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

            // 转换回字符串
            String value1Neg = String(value1Int);
            String value2Neg = String(value2Int);

            // 调转两个值的位置
            String swappedData = value2Neg + "," + value1Neg;

            // 输出调转后的数据
            Serial.println(swappedData);
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
