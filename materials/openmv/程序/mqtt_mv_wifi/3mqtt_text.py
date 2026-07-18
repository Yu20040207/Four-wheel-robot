import sensor
import time
import network
import socket
import struct
import ujson
import gc
from pyb import LED

# 配置
SSID = "MTCPC"
KEY = "mt12345mt"
EMQX_BROKER = "192.168.13.225"
EMQX_PORT = 1883
EMQX_USERNAME = "sy"
EMQX_PASSWORD = "123"

# MQTT主题
CAMERA_CONTROL_TOPIC = "camera_control"      # 接收ESP32控制指令
VIDEO_TOPIC = "openmv/video/stream"          # 发送视频流到Flask
STATUS_TOPIC = "openmv/status"               # 发送状态信息

# 系统状态
SYSTEM_STATE_OFF = 0
SYSTEM_STATE_ON = 1

# 视频流配置
FRAME_SIZE = sensor.QVGA  # 320x240
FRAME_QUALITY = 80
TARGET_FPS =50
MAX_FRAME_SIZE = 20000

# 全局变量
mqtt_socket = None
frame_count = 0
system_state = SYSTEM_STATE_OFF
CLIENT_ID = "openmv_camera_001"
connect_state = 0  # 0=正常, 1=错误, 2=重连中

# LED
red_led = LED(1)
green_led = LED(2)
blue_led = LED(3)

def init_camera():
    """初始化摄像头"""
    try:
        sensor.reset()
        sensor.set_pixformat(sensor.GRAYSCALE)
        sensor.set_framesize(FRAME_SIZE)
        sensor.skip_frames(10)
        sensor.set_auto_whitebal(False)
        print("✅ 摄像头初始化完成: {}x{}".format(sensor.width(), sensor.height()))
        return True
    except Exception as e:
        print(f"❌ 摄像头初始化失败: {e}")
        return False

def init_led():
    """初始化LED"""
    red_led.off()
    green_led.off()
    blue_led.off()
    print("✅ LED初始化完成")

def set_led_state(state):
    """设置LED状态"""
    if state == SYSTEM_STATE_OFF:
        red_led.off()
        green_led.off()
        blue_led.off()
    elif state == SYSTEM_STATE_ON:
        red_led.off()
        green_led.on()
        blue_led.off()

def connect_wifi():
    """连接WiFi"""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        print(f"连接WiFi: {SSID}...")

        if wlan.isconnected():
            wlan.disconnect()
            time.sleep(1)

        wlan.connect(SSID, KEY)

        for i in range(30):
            if wlan.isconnected():
                break
            time.sleep_ms(500)
            print(".", end="")

        if wlan.isconnected():
            print("\n✅ WiFi连接成功!")
            print("IP地址:", wlan.ifconfig()[0])
            return True
        else:
            print("\n❌ WiFi连接失败!")
            return False
    except Exception as e:
        print(f"❌ WiFi连接异常: {e}")
        return False

def connect_mqtt():
    """连接MQTT服务器"""
    global mqtt_socket, connect_state
    try:
        print(f"连接MQTT: {EMQX_BROKER}:{EMQX_PORT}")

        # 关闭现有连接
        if mqtt_socket:
            try:
                mqtt_socket.close()
            except:
                pass
            mqtt_socket = None

        addr = socket.getaddrinfo(EMQX_BROKER, EMQX_PORT)[0][-1]
        sock = socket.socket()
        sock.settimeout(5.0)
        sock.connect(addr)
        sock.settimeout(None)

        # MQTT连接报文
        protocol_name = "MQTT"
        protocol_level = 4
        connect_flags = 0xC2
        keepalive = 60

        variable_header = bytearray()
        variable_header.extend(struct.pack(">H", len(protocol_name)))
        variable_header.extend(protocol_name.encode())
        variable_header.append(protocol_level)
        variable_header.append(connect_flags)
        variable_header.extend(struct.pack(">H", keepalive))

        payload = bytearray()
        payload.extend(struct.pack(">H", len(CLIENT_ID)))
        payload.extend(CLIENT_ID.encode())
        payload.extend(struct.pack(">H", len(EMQX_USERNAME)))
        payload.extend(EMQX_USERNAME.encode())
        payload.extend(struct.pack(">H", len(EMQX_PASSWORD)))
        payload.extend(EMQX_PASSWORD.encode())

        remaining_length = len(variable_header) + len(payload)
        fixed_header = bytearray([0x10, remaining_length])
        connect_packet = fixed_header + variable_header + payload

        sock.send(connect_packet)

        # 等待CONNACK
        sock.settimeout(5.0)
        connack = sock.recv(4)
        sock.settimeout(None)

        if connack[0] == 0x20 and connack[3] == 0x00:
            print("✅ MQTT连接成功")

            # 订阅控制主题
            packet_id = 1
            subscribe_payload = bytearray()
            subscribe_payload.extend(struct.pack(">H", packet_id))
            subscribe_payload.extend(struct.pack(">H", len(CAMERA_CONTROL_TOPIC)))
            subscribe_payload.extend(CAMERA_CONTROL_TOPIC.encode())
            subscribe_payload.append(0)

            remaining_len = len(subscribe_payload)
            subscribe_packet = bytearray([0x82, remaining_len]) + subscribe_payload
            sock.send(subscribe_packet)

            sock.settimeout(3.0)
            suback = sock.recv(5)
            sock.settimeout(None)

            print("✅ 订阅主题成功:", CAMERA_CONTROL_TOPIC)

            mqtt_socket = sock
            connect_state = 0
            return True
        else:
            print("❌ MQTT连接失败")
            sock.close()
            connect_state = 1
            return False

    except Exception as e:
        print(f"❌ MQTT连接异常: {e}")
        connect_state = 1
        return False

def encode_remaining_length(length):
    """编码MQTT剩余长度字段"""
    encoded = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length > 0:
            digit |= 0x80
        encoded.append(digit)
        if length == 0:
            break
    return encoded

def publish_message(topic, message):
    """发布消息到MQTT主题"""
    global mqtt_socket, connect_state

    if not mqtt_socket or connect_state != 0:
        print("❌ MQTT未连接或连接异常")
        return False

    try:
        if isinstance(message, str):
            message_bytes = message.encode('utf-8')
        else:
            message_bytes = message

        fixed_header = bytearray([0x30])
        variable_header = bytearray()
        topic_bytes = topic.encode('utf-8')
        variable_header.extend(struct.pack(">H", len(topic_bytes)))
        variable_header.extend(topic_bytes)
        payload = message_bytes

        remaining_length = len(variable_header) + len(payload)
        encoded_remaining = encode_remaining_length(remaining_length)
        fixed_header.extend(encoded_remaining)
        publish_packet = fixed_header + variable_header + payload

        # 设置发送超时
        mqtt_socket.settimeout(3.0)
        try:
            mqtt_socket.send(publish_packet)
            mqtt_socket.settimeout(None)
            return True
        except Exception as e:
            mqtt_socket.settimeout(None)
            print(f"发送失败: {e}")
            connect_state = 1  # 标记连接错误
            return False

    except Exception as e:
        print(f"发布消息失败: {e}")
        connect_state = 1  # 标记连接错误
        return False

def compress_frame(img):
    """压缩图像帧"""
    quality = FRAME_QUALITY
    max_attempts = 3

    for attempt in range(max_attempts):
        jpeg_data = img.compress(quality=quality)
        if not isinstance(jpeg_data, bytes):
            jpeg_data = bytes(jpeg_data)

        frame_size = len(jpeg_data)

        if frame_size <= MAX_FRAME_SIZE:
            return jpeg_data, frame_size, quality

        quality = max(10, quality - 15)
        print(f"⚠️ 帧过大 ({frame_size}字节)，降低质量为{quality}%")

    return jpeg_data, frame_size, quality

def send_video_frame():
    """发送视频帧"""
    global frame_count

    if system_state != SYSTEM_STATE_ON or connect_state != 0:
        return False

    try:
        img = sensor.snapshot()

        jpeg_data, frame_size, actual_quality = compress_frame(img)

        if frame_size > MAX_FRAME_SIZE:
            print(f"❌ 帧过大 ({frame_size}字节)，跳过此帧")
            return False

        message = {
            "frame_id": frame_count,
            "timestamp": time.ticks_ms(),
            "width": img.width(),
            "height": img.height(),
            "quality": actual_quality,
            "size": frame_size,
            "format": "grayscale",
            "data": jpeg_data.hex()
        }

        message_json = ujson.dumps(message)

        if publish_message(VIDEO_TOPIC, message_json):
            frame_count += 1
            if frame_count % 10 == 0:
                print("📹 已发送视频帧 #{}, 大小: {} 字节, 质量: {}%".format(
                    frame_count, frame_size, actual_quality))
            return True
        else:
            print("❌ 发送视频帧失败")
            return False

    except Exception as e:
        print("发送视频帧失败:", e)
        return False

def check_messages():
    """检查并处理接收到的MQTT消息"""
    global mqtt_socket, system_state, connect_state

    if not mqtt_socket or connect_state != 0:
        return

    try:
        mqtt_socket.setblocking(False)
        data = mqtt_socket.recv(1024)
        if data:
            print(f"📨 收到数据: {len(data)}字节")

            # 简化解析 - 查找ON或OFF消息
            if b"ON" in data:
                print("✅ 收到ON指令 - 开始发送视频流")
                system_state = SYSTEM_STATE_ON
                set_led_state(SYSTEM_STATE_ON)

                # 发送确认消息
                status_msg = {
                    "status": "camera_activated",
                    "system_state": system_state,
                    "client_id": CLIENT_ID,
                    "timestamp": time.ticks_ms(),
                    "message": "开始发送视频流到 {}".format(VIDEO_TOPIC)
                }
                publish_message(STATUS_TOPIC, ujson.dumps(status_msg))
                return True

            elif b"OFF" in data:
                print("🛑 收到OFF指令 - 停止发送视频流")
                system_state = SYSTEM_STATE_OFF
                set_led_state(SYSTEM_STATE_OFF)

                # 发送确认消息
                status_msg = {
                    "status": "camera_deactivated",
                    "system_state": system_state,
                    "client_id": CLIENT_ID,
                    "timestamp": time.ticks_ms(),
                    "message": "停止发送视频流"
                }
                publish_message(STATUS_TOPIC, ujson.dumps(status_msg))
                return True

    except Exception as e:
        # 没有数据是可接受的
        pass

    return False

def send_status():
    """发送状态信息"""
    global frame_count, system_state

    status_msg = {
        "frames_sent": frame_count,
        "status": "streaming" if system_state == SYSTEM_STATE_ON else "standby",
        "client_id": CLIENT_ID,
        "system_state": system_state,
        "camera_active": system_state == SYSTEM_STATE_ON,
        "resolution": "{}x{}".format(sensor.width(), sensor.height())
    }

    if publish_message(STATUS_TOPIC, ujson.dumps(status_msg)):
        state_str = "🟢 运行中" if system_state == SYSTEM_STATE_ON else "🟡 待机中"
        if frame_count % 20 == 0:
            print("📊 状态: {}, 视频帧数={}".format(state_str, frame_count))
        return True
    else:
        print("❌ 发送状态失败")
        return False

def attempt_reconnect():
    """尝试重新连接"""
    global connect_state
    print("🔄 尝试重新连接MQTT...")
    connect_state = 2  # 重连中

    if connect_mqtt():
        print("✅ MQTT重新连接成功")
        connect_state = 0
        return True
    else:
        print("❌ MQTT重新连接失败")
        connect_state = 1
        return False

def main():
    """主函数"""
    global frame_count, system_state, connect_state

    print("=== OpenMV 视频流控制系统 ===")
    print(f"客户端ID: {CLIENT_ID}")
    print("🚀 系统启动中...")

    # 初始化硬件
    if not init_camera():
        print("❌ 摄像头初始化失败，程序退出")
        return

    init_led()

    # 绿灯闪烁3次表示系统启动完成
    for i in range(3):
        green_led.on()
        time.sleep_ms(200)
        green_led.off()
        time.sleep_ms(200)

    # 设置为等待状态
    set_led_state(SYSTEM_STATE_OFF)
    print("✅ 系统已启动，等待控制指令...")

    # 连接网络
    if not connect_wifi():
        print("❌ WiFi连接失败，程序退出")
        return

    if not connect_mqtt():
        print("❌ MQTT连接失败，程序退出")
        return

    print("\n🚀 系统就绪!")
    print("控制主题: " + CAMERA_CONTROL_TOPIC)
    print("视频流主题: " + VIDEO_TOPIC)
    print("等待ESP32发送控制指令...")

    # 发送就绪状态
    status_msg = {
        "status": "ready",
        "client_id": CLIENT_ID,
        "timestamp": time.ticks_ms(),
        "message": "系统就绪，等待控制指令"
    }
    publish_message(STATUS_TOPIC, ujson.dumps(status_msg))

    # 初始化时间变量
    last_status_time = time.ticks_ms()
    last_frame_time = time.ticks_ms()
    last_reconnect_attempt = time.ticks_ms()
    frame_interval = int(1000 / TARGET_FPS)
    reconnect_interval = 5000  # 5秒重连一次
    led_blink_time = time.ticks_ms()
    led_blink_state = False

    while True:
        current_time = time.ticks_ms()

        # 处理连接状态
        if connect_state == 1:  # 连接错误
            if time.ticks_diff(current_time, last_reconnect_attempt) > reconnect_interval:
                if attempt_reconnect():
                    # 重连成功后恢复状态
                    if system_state == SYSTEM_STATE_ON:
                        status_msg = {
                            "status": "reconnected",
                            "system_state": system_state,
                            "client_id": CLIENT_ID,
                            "timestamp": current_time,
                            "message": "重新连接成功，恢复视频流"
                        }
                        publish_message(STATUS_TOPIC, ujson.dumps(status_msg))
                last_reconnect_attempt = current_time
        elif connect_state == 0:  # 连接正常
            # 检查并处理消息
            check_messages()

            # 如果摄像头开启，发送视频流
            if system_state == SYSTEM_STATE_ON:
                if time.ticks_diff(current_time, last_frame_time) > frame_interval:
                    send_video_frame()
                    last_frame_time = current_time

            # 定期发送状态
            if time.ticks_diff(current_time, last_status_time) > 10000:
                send_status()
                gc.collect()
                last_status_time = current_time

        # 等待状态下LED闪烁
        if system_state == SYSTEM_STATE_OFF:
            if time.ticks_diff(current_time, led_blink_time) > 500:
                led_blink_state = not led_blink_state
                if connect_state == 0:  # 正常连接
                    green_led.on() if led_blink_state else green_led.off()
                else:  # 连接错误
                    red_led.on() if led_blink_state else red_led.off()
                led_blink_time = current_time

        time.sleep_ms(10)

# 启动程序
try:
    main()
except Exception as e:
    print(f"程序错误: {e}")
    import sys
    sys.print_exception(e)
    red_led.on()
    time.sleep(5000)
finally:
    # 清理资源
    try:
        if mqtt_socket:
            mqtt_socket.close()
            print("已关闭MQTT连接")
    except:
        pass
    red_led.off()
    green_led.off()
    blue_led.off()
    print("程序结束")
