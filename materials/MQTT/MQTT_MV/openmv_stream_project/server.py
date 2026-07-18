from flask import Flask, render_template, Response, jsonify
import paho.mqtt.client as mqtt
import json
import base64
import time
import threading
from io import BytesIO
from PIL import Image
import cv2
import numpy as np

app = Flask(__name__)

# EMQX配置
EMQX_BROKER = "192.168.13.225"
EMQX_PORT = 1883
EMQX_WS_PORT = 8083
EMQX_USERNAME = "sy"
EMQX_PASSWORD = "123"

# MQTT主题
VIDEO_TOPIC = "openmv/video/stream"
STATUS_TOPIC = "openmv/status"
CONTROL_TOPIC = "openmv/control"

# 全局变量
current_frame = None
frame_lock = threading.Lock()
connected_clients = 0
stats = {
    'fps': 0,
    'frames_received': 0,
    'latency': 0,
    'clients': 0
}


class MQTTManager:
    def __init__(self):
        self.client = None
        self.is_connected = False

    def connect(self):
        """连接EMQX服务器"""
        try:
            self.client = mqtt.Client()
            self.client.username_pw_set(EMQX_USERNAME, EMQX_PASSWORD)

            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect

            print(f"连接EMQX服务器 {EMQX_BROKER}:{EMQX_PORT}...")
            self.client.connect(EMQX_BROKER, EMQX_PORT, 60)
            self.client.loop_start()
            return True

        except Exception as e:
            print(f"连接失败: {e}")
            return False

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_connected = True
            print("EMQX连接成功!")
            client.subscribe(VIDEO_TOPIC)
            client.subscribe(STATUS_TOPIC)
        else:
            print(f"连接失败，错误代码: {rc}")

    def on_message(self, client, userdata, msg):
        global current_frame, stats

        try:
            if msg.topic == VIDEO_TOPIC:
                data = json.loads(msg.payload.decode())

                # 处理视频帧
                if 'data' in data:
                    hex_data = data['data']
                    jpeg_bytes = bytes.fromhex(hex_data)

                    with frame_lock:
                        current_frame = jpeg_bytes

                    # 更新统计信息
                    stats['frames_received'] += 1
                    if 'timestamp' in data:
                        stats['latency'] = int((time.time() * 1000) - data['timestamp'])

            elif msg.topic == STATUS_TOPIC:
                status_data = json.loads(msg.payload.decode())
                print(f"OpenMV状态: {status_data}")

        except Exception as e:
            print(f"处理MQTT消息错误: {e}")

    def on_disconnect(self, client, userdata, rc):
        self.is_connected = False
        print("MQTT连接断开")

    def send_control(self, command):
        """发送控制命令"""
        if self.is_connected:
            self.client.publish(CONTROL_TOPIC, json.dumps({"command": command}))
            print(f"发送控制命令: {command}")
            return True
        return False


# 初始化MQTT管理器
mqtt_manager = MQTTManager()


@app.route('/')
def index():
    """主页面"""
    return render_template('video_stream.html')


@app.route('/video_feed')
def video_feed():
    """视频流端点 - 返回MJPEG流"""

    def generate():
        while True:
            with frame_lock:
                if current_frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' +
                           current_frame + b'\r\n')
                else:
                    # 如果没有帧，发送黑色图像
                    black_frame = generate_black_frame()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' +
                           black_frame + b'\r\n')
            time.sleep(0.1)  # 控制帧率

    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/control/<command>')
def control_camera(command):
    """控制摄像头API"""
    if command in ['start', 'stop']:
        success = mqtt_manager.send_control(command)
        return jsonify({"status": "success" if success else "error"})
    return jsonify({"status": "error", "message": "无效命令"})


@app.route('/api/stats')
def get_stats():
    """获取统计信息"""
    stats['clients'] = connected_clients
    return jsonify(stats)


def generate_black_frame():
    """生成黑色帧"""
    img = Image.new('RGB', (640, 480), color='black')
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()


@app.before_request
def before_request():
    global connected_clients
    connected_clients += 1


@app.teardown_request
def teardown_request(exception=None):
    global connected_clients
    connected_clients -= 1


if __name__ == '__main__':
    # 连接MQTT
    if mqtt_manager.connect():
        print("启动Flask服务器...")
        # 在PyCharm中运行，host='0.0.0.0'允许外部访问
        app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
    else:
        print("MQTT连接失败，服务器无法启动")