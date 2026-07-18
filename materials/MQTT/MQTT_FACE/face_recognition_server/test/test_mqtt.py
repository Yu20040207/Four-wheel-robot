# test_mqtt_server.py - 在电脑上测试MQTT服务器
import paho.mqtt.client as mqtt
import time
import sys


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ 电脑客户端连接MQTT服务器成功")
        client.subscribe("test/#")
    else:
        print(f"❌ 电脑客户端连接失败，错误代码: {rc}")
        sys.exit(1)


def on_message(client, userdata, msg):
    print(f"📨 收到消息: {msg.topic} -> {msg.payload.decode()}")


def test_mqtt_server(server_ip, username=None, password=None):
    print(f"测试MQTT服务器: {server_ip}:1883")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    if username and password:
        client.username_pw_set(username, password)
        print(f"使用认证: 用户名={username}")

    try:
        print("尝试连接...")
        client.connect(server_ip, 1883, 60)
        client.loop_start()

        # 发布测试消息
        client.publish("test/pc", "Hello from PC!")
        print("✅ 测试消息已发送")

        # 等待接收消息
        print("等待10秒接收消息...")
        time.sleep(10)

        client.loop_stop()
        client.disconnect()
        print("✅ 服务器测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        print("请检查:")
        print("1. 服务器IP地址是否正确")
        print("2. 服务器是否正在运行")
        print("3. 防火墙是否阻止连接")


if __name__ == "__main__":
    # 替换为你的EMQX服务器IP
    server_ip = "192.168.13.225"  # 例如 "192.168.1.100"

    # 再尝试认证连接
    print("\n=== 测试认证连接 ===")
    test_mqtt_server(server_ip, username="sy_1", password="123")
