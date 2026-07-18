# standalone_test_client.py - 独立版测试客户端
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime


class StandaloneTester:
    """独立版测试客户端"""

    def __init__(self):
        self.client = None
        self.message_count = 0

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("✅ MQTT连接成功")
            # 订阅所有相关主题
            topics = [
                "face_recognition/result",
                "face_recognition/error",
                "face_recognition/notification",
                "face_recognition/control_response",
                "face_recognition/admin_response"
            ]
            for topic in topics:
                client.subscribe(topic)
                print(f"📡 已订阅: {topic}")
        else:
            print(f"❌ 连接失败: {rc}")

    def on_message(self, client, userdata, msg):
        self.message_count += 1
        print(f"\n📥 消息 #{self.message_count} [主题: {msg.topic}]")
        print("-" * 50)

        try:
            data = json.loads(msg.payload.decode())

            if msg.topic == "face_recognition/result":
                self.handle_recognition_result(data)
            elif msg.topic == "face_recognition/notification":
                self.handle_notification(data)
            elif msg.topic == "face_recognition/control_response":
                self.handle_control_response(data)
            elif msg.topic == "face_recognition/admin_response":
                self.handle_admin_response(data)
            elif msg.topic == "face_recognition/error":
                self.handle_error(data)

        except Exception as e:
            print(f"❌ 消息解析错误: {e}")

    def handle_recognition_result(self, data):
        """处理识别结果"""
        print(f"🔍 识别结果:")
        print(f"   请求ID: {data['request_id']}")
        print(f"   设备: {data['device_id']}")
        print(f"   人脸数量: {data['face_count']}")

        if data['face_count'] > 0:
            print("   👥 识别到的人员:")
            for i, person in enumerate(data['recognition_results']):
                print(f"     {i + 1}. {person['name']} ({person['role']})")
                print(f"         置信度: {person['confidence']}")
                print(f"         权限: {person['access_level']}")
        else:
            print("   ⚠️ 未识别到人脸")

        print(f"   📊 图像分析: {data['image_analysis']['status']}")

    def handle_notification(self, data):
        """处理通知"""
        print(f"📢 实时通知:")
        print(f"   设备: {data['device_id']}")
        print(f"   识别人数: {data['recognized_count']}")
        print(f"   安全级别: {data['security_level']}")

    def handle_control_response(self, data):
        """处理控制响应"""
        print(f"⚙️  控制响应:")
        for key, value in data.items():
            print(f"   {key}: {value}")

    def handle_admin_response(self, data):
        """处理管理员响应"""
        action = data.get('action', 'unknown')
        print(f"👨‍💼 管理员操作: {action}")
        if action == "person_added":
            print(f"   ✅ 添加人员: {data['person_info']['name']}")
        elif action == "person_removed":
            print(f"   ✅ 移除人员: {data['removed_person']['name']}")

    def handle_error(self, data):
        """处理错误"""
        print(f"❌ 错误: {data['error_type']}")
        print(f"   信息: {data['error_message']}")

    def send_recognition_request(self, device_id):
        """发送识别请求"""
        request_data = {
            "device_id": device_id,
            "request_id": f"test_{int(time.time())}_{device_id}",
            "timestamp": datetime.now().isoformat(),
            "image_data": "dGVzdF9pbWFnZV9kYXRh"  # 简单的测试数据
        }

        self.client.publish("face_recognition/data", json.dumps(request_data))
        print(f"📤 发送识别请求: {device_id}")

    def send_control_command(self, command):
        """发送控制命令"""
        control_data = {
            "command": command,
            "timestamp": datetime.now().isoformat()
        }

        self.client.publish("face_recognition/control", json.dumps(control_data))
        print(f"⚙️  发送控制命令: {command}")

    def send_admin_command(self, action, data=None):
        """发送管理员命令"""
        if data is None:
            data = {}

        admin_data = {
            "action": action,
            "timestamp": datetime.now().isoformat(),
            **data
        }

        self.client.publish("face_recognition/admin", json.dumps(admin_data))
        print(f"👨‍💼 发送管理员命令: {action}")

    def run_comprehensive_test(self):
        """运行全面测试"""
        try:
            # 创建客户端
            self.client = mqtt.Client(transport='websockets')
            self.client.ws_set_options(path="/mqtt")
            self.client.username_pw_set("sy", "123")

            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message

            print("正在连接到MQTT服务器...")
            self.client.connect("192.168.56.1", 8083, 60)
            self.client.loop_start()

            time.sleep(2)  # 等待连接

            print("\n=== 开始全面测试 ===\n")

            # 1. 获取状态
            print("1. 获取服务状态...")
            self.send_control_command("status")
            time.sleep(2)

            # 2. 发送多个识别请求
            print("\n2. 发送识别请求...")
            devices = ["前台摄像头", "入口摄像头", "办公室摄像头", "出口摄像头"]
            for device in devices:
                self.send_recognition_request(device)
                time.sleep(3)

            # 3. 获取统计信息
            print("\n3. 获取统计信息...")
            self.send_control_command("statistics")
            time.sleep(2)

            # 4. 获取数据库信息
            print("\n4. 获取数据库信息...")
            self.send_control_command("database_info")
            time.sleep(2)

            # 5. 添加新人员
            print("\n5. 添加新人员...")
            new_person = {
                "person_id": "emp_999",
                "name": "测试人员",
                "department": "测试部",
                "role": "测试员",
                "access_level": "medium"
            }
            self.send_admin_command("add_person", new_person)
            time.sleep(2)

            # 6. 再次发送识别请求测试新人员
            print("\n6. 测试新人员识别...")
            self.send_recognition_request("测试摄像头")
            time.sleep(3)

            # 7. 获取历史记录
            print("\n7. 获取历史记录...")
            self.send_control_command("history")
            time.sleep(2)

            print(f"\n=== 测试完成 ===\n")
            print(f"共收到 {self.message_count} 条消息")
            print("等待剩余响应...")
            time.sleep(5)

        except Exception as e:
            print(f"❌ 测试错误: {e}")
        finally:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
            print("测试客户端已关闭")


if __name__ == "__main__":
    tester = StandaloneTester()
    tester.run_comprehensive_test()