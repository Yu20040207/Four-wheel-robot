# openmv_controller.py
import paho.mqtt.client as mqtt
import json
import time
import cv2
import numpy as np
from PIL import Image
import io
import threading

# MQTT服务器配置
MQTT_BROKER = "192.168.13.225"
MQTT_PORT = 1883
MQTT_USERNAME = "sy"
MQTT_PASSWORD = "123"

# 主题配置
VIDEO_TOPIC = "openmv/video"
STATUS_TOPIC = "openmv/status"
CONTROL_TOPIC = "openmv/control"


class OpenMVController:
    def __init__(self):
        self.client = None
        self.is_connected = False
        self.frame_count = 0
        self.current_frame = None
        self.is_streaming = False

    def connect(self):
        """连接MQTT服务器"""
        try:
            self.client = mqtt.Client()
            self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

            # 设置回调函数
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect

            print(f"连接MQTT服务器 {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)

            # 启动MQTT循环
            self.client.loop_start()
            return True

        except Exception as e:
            print(f"连接失败: {e}")
            return False

    def on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        if rc == 0:
            self.is_connected = True
            print("MQTT连接成功!")

            # 订阅视频和状态主题
            client.subscribe(VIDEO_TOPIC)
            client.subscribe(STATUS_TOPIC)
            print(f"已订阅主题: {VIDEO_TOPIC}, {STATUS_TOPIC}")
        else:
            print(f"连接失败，错误代码: {rc}")

    def on_message(self, client, userdata, msg):
        """消息接收回调"""
        try:
            topic = msg.topic
            payload = msg.payload

            if topic == VIDEO_TOPIC:
                self.process_video_frame(payload)
            elif topic == STATUS_TOPIC:
                self.process_status_message(payload)

        except Exception as e:
            print(f"处理消息错误: {e}")

    def on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        self.is_connected = False
        if rc != 0:
            print("意外断开连接，尝试重连...")
        else:
            print("连接已断开")

    def process_video_frame(self, payload):
        """处理视频帧"""
        try:
            # 解析帧数据 (格式: "帧ID|" + JPEG数据)
            if b'|' in payload:
                parts = payload.split(b'|', 1)
                if len(parts) == 2:
                    frame_id = parts[0].decode('utf-8', errors='ignore')
                    jpeg_data = parts[1]

                    # 将JPEG数据转换为图像
                    image = Image.open(io.BytesIO(jpeg_data))
                    self.current_frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

                    self.frame_count += 1
                    if self.frame_count % 10 == 0:
                        print(f"收到第 {self.frame_count} 帧")

        except Exception as e:
            print(f"处理视频帧错误: {e}")

    def process_status_message(self, payload):
        """处理状态消息"""
        try:
            status_str = payload.decode('utf-8', errors='ignore')
            print(f"状态更新: {status_str}")
        except Exception as e:
            print(f"处理状态消息错误: {e}")

    def send_control_command(self, command):
        """发送控制命令"""
        if self.is_connected:
            self.client.publish(CONTROL_TOPIC, command)
            print(f"发送命令: {command}")
            return True
        else:
            print("未连接，无法发送命令")
            return False

    def start_stream(self):
        """开始视频流"""
        return self.send_control_command("start")

    def stop_stream(self):
        """停止视频流"""
        return self.send_control_command("stop")

    def display_video(self):
        """显示视频帧（在单独的线程中运行）"""

        def display_loop():
            while True:
                if self.current_frame is not None:
                    # 调整窗口大小以适应QQVGA分辨率
                    display_frame = cv2.resize(self.current_frame, (320, 240))
                    cv2.imshow('OpenMV Camera', display_frame)

                # 按'q'退出
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            cv2.destroyAllWindows()

        # 在单独的线程中运行显示
        display_thread = threading.Thread(target=display_loop)
        display_thread.daemon = True
        display_thread.start()

    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("已断开连接")


def main():
    controller = OpenMVController()

    if controller.connect():
        print("\n=== OpenMV 控制器 ===")
        print("命令:")
        print("  1 - 开始视频流")
        print("  2 - 停止视频流")
        print("  3 - 显示视频窗口")
        print("  0 - 退出")

        # 启动视频显示
        controller.display_video()

        try:
            while True:
                command = input("\n请输入命令: ").strip()

                if command == '1':
                    controller.start_stream()
                    controller.is_streaming = True
                elif command == '2':
                    controller.stop_stream()
                    controller.is_streaming = False
                elif command == '3':
                    print("视频窗口已启动（按 'q' 关闭窗口）")
                elif command == '0':
                    break
                else:
                    print("未知命令")

        except KeyboardInterrupt:
            print("\n程序被用户中断")
        finally:
            controller.disconnect()


if __name__ == "__main__":
    main()