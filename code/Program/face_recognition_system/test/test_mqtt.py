# pycharm_mqtt_sender.py
import paho.mqtt.client as mqtt
import json
import time
import threading

# EMQX服务器配置
EMQX_BROKER = "192.168.13.225"
EMQX_PORT = 1883
EMQX_USERNAME = "sy"
EMQX_PASSWORD = "123"
TOPIC = "openmv_recognition_result"


class MQTTTestSender:
    def __init__(self):
        self.client = None
        self.connected = False

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("✅ 连接到EMQX服务器成功")
            self.connected = True
        else:
            print(f"❌ 连接失败，返回码: {rc}")

    def on_publish(self, client, userdata, mid):
        print(f"✅ 消息已发布 (消息ID: {mid})")

    def connect(self):
        """连接MQTT服务器"""
        print(f"连接EMQX: {EMQX_BROKER}:{EMQX_PORT}")
        self.client = mqtt.Client()
        self.client.username_pw_set(EMQX_USERNAME, EMQX_PASSWORD)
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish

        try:
            self.client.connect(EMQX_BROKER, EMQX_PORT, 60)
            self.client.loop_start()
            time.sleep(2)  # 等待连接建立
            return self.connected
        except Exception as e:
            print(f"连接异常: {e}")
            return False

    def send_test_message(self, message_data):
        """发送测试消息"""
        if not self.connected:
            print("未连接到MQTT服务器")
            return False

        try:
            # 转换为JSON并发布
            message_json = json.dumps(message_data)
            result = self.client.publish(TOPIC, message_json, qos=0)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"📤 发送消息: {message_json}")
                print(f"消息大小: {len(message_json)} 字节")
                return True
            else:
                print(f"发布失败，错误码: {result.rc}")
                return False

        except Exception as e:
            print(f"发送消息异常: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("已断开MQTT连接")


def interactive_test():
    """交互式测试"""
    sender = MQTTTestSender()

    if not sender.connect():
        print("无法连接到MQTT服务器，请检查网络和服务器状态")
        return

    print("\n" + "=" * 50)
    print("MQTT消息发送测试程序")
    print("=" * 50)

    # 预定义测试消息
    test_messages = [
        {
            "recognized_names": ["sy"],
            "count": 1,
            "timestamp": int(time.time() * 1000),
            "confidence_scores": [65.3]
        },
        {
            "recognized_names": ["user1", "user2"],
            "count": 2,
            "timestamp": int(time.time() * 1000),
            "confidence_scores": [78.5, 62.1]
        },
        {
            "recognized_names": [],
            "count": 0,
            "timestamp": int(time.time() * 1000),
            "confidence_scores": []
        },
        {
            "test": "simple",
            "message": "Hello OpenMV"
        }
    ]

    try:
        while True:
            print("\n选择要发送的消息:")
            print("1. 单人识别 (sy)")
            print("2. 双人识别 (user1, user2)")
            print("3. 无人识别")
            print("4. 简单测试消息")
            print("5. 自定义消息")
            print("0. 退出")

            choice = input("请输入选择 (0-5): ").strip()

            if choice == "0":
                break
            elif choice in ["1", "2", "3", "4"]:
                msg_index = int(choice) - 1
                sender.send_test_message(test_messages[msg_index])
            elif choice == "5":
                custom_msg = input("输入自定义消息 (JSON格式): ").strip()
                try:
                    if custom_msg:
                        data = json.loads(custom_msg)
                        sender.send_test_message(data)
                    else:
                        print("消息不能为空")
                except json.JSONDecodeError:
                    print("无效的JSON格式")
            else:
                print("无效选择")

            time.sleep(1)  # 短暂延迟

    except KeyboardInterrupt:
        print("\n用户中断程序")
    finally:
        sender.disconnect()


def auto_test():
    """自动测试 - 发送一系列消息"""
    sender = MQTTTestSender()

    if not sender.connect():
        return

    print("开始自动测试...")

    # 发送一系列测试消息
    test_cases = [
        {"test": "simple", "message": "Hello OpenMV", "number": 1},
        {"recognized_names": ["test_user"], "count": 1, "confidence_scores": [75.0]},
        {"recognized_names": ["Alice", "Bob"], "count": 2, "confidence_scores": [80.0, 65.5]},
    ]

    for i, message in enumerate(test_cases):
        print(f"\n发送测试消息 {i + 1}/{len(test_cases)}")
        message["timestamp"] = int(time.time() * 1000)
        sender.send_test_message(message)
        time.sleep(3)  # 等待3秒

    sender.disconnect()
    print("自动测试完成")


if __name__ == "__main__":
    print("MQTT消息发送器")
    print("1. 交互式测试")
    print("2. 自动测试")

    mode = input("选择模式 (1 或 2): ").strip()

    if mode == "1":
        interactive_test()
    elif mode == "2":
        auto_test()
    else:
        print("无效选择")
