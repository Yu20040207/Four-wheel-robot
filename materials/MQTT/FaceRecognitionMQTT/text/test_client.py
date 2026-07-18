# test_client.py - 测试客户端
import paho.mqtt.client as mqtt
import json
import base64
import cv2
import time
from datetime import datetime


def on_connect(client, userdata, flags, rc):
    print("✅ 连接成功")
    client.subscribe("face_recognition/result")
    client.subscribe("face_recognition/error")


def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    if msg.topic == "face_recognition/result":
        print(f"🔍 识别结果: {payload['face_count']} 张人脸")
        print(f"   设备: {payload['device_id']}")
        print(f"   状态: {payload['status']}")
    elif msg.topic == "face_recognition/error":
        print(f"❌ 错误: {payload['error_type']} - {payload['error_message']}")


def send_test_image(client, image_path="test_images/test_face.jpg"):
    """发送测试图像"""
    try:
        # 读取图像
        img = cv2.imread(image_path)
        if img is None:
            print(f"❌ 无法读取图像: {image_path}")
            return

        # 编码为JPEG
        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        img_str = base64.b64encode(buffer).decode('utf-8')

        # 构建测试数据
        test_data = {
            "device_id": "test_device_001",
            "request_id": f"test_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "image_data": img_str
        }

        # 发布消息
        client.publish("face_recognition/data", json.dumps(test_data))
        print(f"📤 已发送测试图像: {image_path}")

    except Exception as e:
        print(f"❌ 发送测试图像失败: {e}")


def main():
    client = mqtt.Client("test_client")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect("localhost", 1883, 60)
        client.loop_start()

        print("🚀 测试客户端已启动，5秒后发送测试图像...")
        time.sleep(5)

        # 发送测试图像
        send_test_image(client)

        # 等待结果
        time.sleep(10)

    except Exception as e:
        print(f"❌ 测试客户端错误: {e}")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()