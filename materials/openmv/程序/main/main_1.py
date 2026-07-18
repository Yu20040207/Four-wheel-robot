import sensor
import time
import image
import network
import socket
import struct
import ujson
import gc
from pyb import LED, I2C
from math import pi, isnan

# 配置
SSID = "MTCPC"
KEY = "mt12345mt"
EMQX_BROKER = "192.168.13.225"
#EMQX_BROKER = "192.168.123.107"
EMQX_PORT = 1883
EMQX_USERNAME = "sy"
EMQX_PASSWORD = "123"

# MQTT主题
CAMERA_CONTROL_TOPIC = "camera_control"
VIDEO_TOPIC = "openmv/video/stream"
STATUS_TOPIC = "openmv/status"
RECOGNITION_RESULT_TOPIC = "openmv_recognition_result"
RECOGNITION_ACK_TOPIC = "openmv/recognition_ack"
FLASK_CONTROL_TOPIC = "flask/control"
FACE_COLLECTION_TOPIC = "face_collection"

# 系统状态
SYSTEM_STATE_OFF = 0
SYSTEM_STATE_READY = 1
SYSTEM_STATE_ON = 2
SYSTEM_STATE_FACE_TRACKING = 3
SYSTEM_STATE_start_recognition = 4

# 视频流配置
FRAME_SIZE = sensor.QVGA
FRAME_QUALITY = 80
TARGET_FPS = 30
MAX_FRAME_SIZE = 25000

# 舵机控制参数
SERVO_MIN = 150
SERVO_MAX = 450
SERVO_MID = 300

# 全局变量
mqtt_socket = None
frame_count = 0
system_state = SYSTEM_STATE_OFF
CLIENT_ID = "openmv_camera_001"
connect_state = 0
last_command_time = 0
# 性能优化变量
last_message_check = 0
message_check_interval = 5
video_frame_interval = int(1000 / TARGET_FPS)
last_frame_time = 0
pending_commands = []

# Flask控制命令相关
last_control_command_time = 0
control_command_interval = 1000

# 人体跟踪相关变量
human_tracking_enabled = False
last_human_command_time = 0
human_command_interval = 300  # 300ms间隔，防止指令过密

# 舵机相关变量
pca = None
pan_servo_channel = 0
tilt_servo_channel = 1
current_pan_angle = 0
current_tilt_angle = 0
pan_pid = None
tilt_pid = None
face_cascade = None

# LED
red_led = LED(1)
green_led = LED(2)
blue_led = LED(3)

# PCA9685类
class PCA9685:
    def __init__(self, i2c, address=0x40):
        self.i2c = i2c
        self.address = address
        self.reset()

    def _write(self, address, value):
        try:
            self.i2c.mem_write(value, self.address, address)
            return True
        except Exception as e:
            return False

    def _read(self, address):
        try:
            return self.i2c.mem_read(1, self.address, address)[0]
        except Exception as e:
            return 0

    def reset(self):
        self._write(0x00, 0x00)

    def freq(self, freq=None):
        if freq is None:
            return int(25000000.0 / 4096 / (self._read(0xFE) - 0.5))
        prescale = int(25000000.0 / 4096.0 / freq + 0.5)
        old_mode = self._read(0x00)
        self._write(0x00, (old_mode & 0x7F) | 0x10)
        self._write(0xFE, prescale)
        self._write(0x00, old_mode)
        time.sleep_us(5)
        self._write(0x00, old_mode | 0xA1)

    def pwm(self, index, on=None, off=None):
        if on is None or off is None:
            try:
                data = self.i2c.mem_read(4, self.address, 0x06 + 4 * index)
                return struct.unpack("<HH", data)
            except Exception as e:
                return (0, 0)
        data = struct.pack("<HH", on, off)
        try:
            self.i2c.mem_write(data, self.address, 0x06 + 4 * index)
            return True
        except Exception as e:
            return False

    def duty(self, index, value=None, invert=False):
        if value is None:
            pwm = self.pwm(index)
            if pwm == (0, 4096):
                value = 0
            elif pwm == (4096, 0):
                value = 4095
            value = pwm[1]
            if invert:
                value = 4095 - value
            return value
        if not 0 <= value <= 4095:
            raise ValueError("Out of range")
        if invert:
            value = 4095 - value
        if value == 0:
            return self.pwm(index, 0, 4096)
        elif value == 4095:
            return self.pwm(index, 4096, 0)
        else:
            return self.pwm(index, 0, value)

class PID:
    _kp = _ki = _kd = _integrator = _imax = 0
    _last_error = _last_derivative = _last_t = 0
    _RC = 1/(2 * pi * 20)

    def __init__(self, p=0, i=0, d=0, imax=0):
        self._kp = float(p)
        self._ki = float(i)
        self._kd = float(d)
        self._imax = abs(imax)
        self._last_derivative = float('nan')

    def get_pid(self, error, scaler):
        tnow = time.ticks_ms()
        dt = tnow - self._last_t
        output = 0
        if self._last_t == 0 or dt > 1000:
            dt = 0
            self.reset_I()
        self._last_t = tnow
        delta_time = float(dt) / float(1000)
        output += error * self._kp
        if abs(self._kd) > 0 and dt > 0:
            if isnan(self._last_derivative):
                derivative = 0
                self._last_derivative = 0
            else:
                derivative = (error - self._last_error) / delta_time
            derivative = self._last_derivative + \
                                     ((delta_time / (self._RC + delta_time)) * \
                                        (derivative - self._last_derivative))
            self._last_error = error
            self._last_derivative = derivative
            output += self._kd * derivative
        output *= scaler
        if abs(self._ki) > 0 and dt > 0:
            self._integrator += (error * self._ki) * scaler * delta_time
            if self._integrator < -self._imax:
                self._integrator = -self._imax
            elif self._integrator > self._imax:
                self._integrator = self._imax
            output += self._integrator
        return output

    def reset_I(self):
        self._integrator = 0
        self._last_derivative = float('nan')

def blink_red_and_reset():
    """红灯闪烁两次并重置程序"""
    print("🔴 连接失败，红灯闪烁并重置程序...")
    for i in range(2):
        red_led.on()
        time.sleep_ms(500)
        red_led.off()
        time.sleep_ms(500)
    print("🔄 正在重置程序...")
    time.sleep_ms(1000)
    import machine
    machine.reset()

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

def init_servos():
    """初始化舵机系统"""
    global pca, pan_pid, tilt_pid, face_cascade
    try:
        i2c = I2C(2, I2C.MASTER, baudrate=100000)
        devices = i2c.scan()
        if 0x40 in devices:
            pca = PCA9685(i2c)
            pca.freq(50)
            print("✅ PCA9685初始化成功")
        else:
            print("❌ PCA9685未找到")
            class DummyPCA:
                def duty(self, channel, value):
                    return True
            pca = DummyPCA()
        try:
            face_cascade = image.HaarCascade("/rom/haarcascade_frontalface.cascade", stages=25)
            print("✅ 人脸检测器加载成功")
        except:
            try:
                face_cascade = image.HaarCascade("frontalface", stages=25)
                print("✅ 人脸检测器加载成功 (备用)")
            except:
                print("❌ 人脸检测器加载失败")
                face_cascade = None
        pan_pid = PID(p=0.22, i=0, d=0.003, imax=90)
        tilt_pid = PID(p=0.24, i=0, d=0.006, imax=90)
        middle()
        return True
    except Exception as e:
        print(f"❌ 舵机系统初始化失败: {e}")
        return False

def set_servo_angle(channel, angle):
    """设置舵机角度"""
    global pca, current_pan_angle, current_tilt_angle
    if pca is None:
        return
    pulse_width = SERVO_MIN + ((angle + 90) / 180.0) * (SERVO_MAX - SERVO_MIN)
    pulse_width = int(pulse_width)
    pulse_width = max(SERVO_MIN, min(SERVO_MAX, pulse_width))
    for attempt in range(2):
        try:
            success = pca.duty(channel, pulse_width)
            if success is not False:
                if channel == pan_servo_channel:
                    current_pan_angle = angle
                elif channel == tilt_servo_channel:
                    current_tilt_angle = angle
                return
        except:
            pass
        time.sleep_ms(5)

def middle():
    """舵机复位到中间位置"""
    global current_pan_angle, current_tilt_angle
    current_pan_angle = 0
    current_tilt_angle = 0
    set_servo_angle(pan_servo_channel, current_pan_angle)
    set_servo_angle(tilt_servo_channel, current_tilt_angle)

def move_forward():
    """前进"""
    global current_tilt_angle
    if current_tilt_angle > -50:  # 确保不超过最小角度
        current_tilt_angle -= 5
        set_servo_angle(tilt_servo_channel, current_tilt_angle)
        print("⬆️ 前进 - 俯仰角度: {}°".format(current_tilt_angle))

def move_backward():
    """后退"""
    global current_tilt_angle
    if current_tilt_angle < 40:  # 确保不超过最大角度
        current_tilt_angle += 5
        set_servo_angle(tilt_servo_channel, current_tilt_angle)
        print("⬇️ 后退 - 俯仰角度: {}°".format(current_tilt_angle))

def turn_left():
    """左转"""
    global current_pan_angle
    if current_pan_angle < 80:  # 确保不超过最大角度
        current_pan_angle += 5
        set_servo_angle(pan_servo_channel, current_pan_angle)
        print("⬅️ 左转 - 偏航角度: {}°".format(current_pan_angle))

def turn_right():
    """右转"""
    global current_pan_angle
    if current_pan_angle > -80:  # 确保不超过最小角度
        current_pan_angle -= 5
        set_servo_angle(pan_servo_channel, current_pan_angle)
        print("➡️ 右转 - 偏航角度: {}°".format(current_pan_angle))

def stop_moving():
    """停止移动"""
    print("⏹️ 停止移动")

def find_max(faces):
    """找到最大的人脸区域"""
    max_size = 0
    max_face = None
    for face in faces:
        if face[2] * face[3] > max_size:
            max_face = face
            max_size = face[2] * face[3]
    return max_face

def face_tracking():
    """执行人脸跟踪"""
    global current_pan_angle, current_tilt_angle
    if face_cascade is None or system_state < SYSTEM_STATE_FACE_TRACKING:
        return False
    img = sensor.snapshot()
    faces = img.find_features(face_cascade, threshold=0.4, scale_factor=1.25) if face_cascade else []
    if faces:
        max_face = find_max(faces)
        face_center_x = max_face[0] + max_face[2] // 2
        face_center_y = max_face[1] + max_face[3] // 2
        pan_error = face_center_x - img.width() // 2
        tilt_error = face_center_y - img.height() // 2
        if abs(pan_error) > 10:
            pan_output = pan_pid.get_pid(pan_error, 1) / 3
        else:
            pan_output = 0
        if abs(tilt_error) > 10:
            tilt_output = tilt_pid.get_pid(tilt_error, 1) / 3
        else:
            tilt_output = 0
        current_pan_angle = current_pan_angle - pan_output
        current_tilt_angle = current_tilt_angle + tilt_output
        current_pan_angle = max(-80, min(80, current_pan_angle))
        current_tilt_angle = max(-50, min(40, current_tilt_angle))
        set_servo_angle(pan_servo_channel, current_pan_angle)
        set_servo_angle(tilt_servo_channel, current_tilt_angle)
        return True
    else:
        pan_pid.reset_I()
        tilt_pid.reset_I()
        return False

def init_led():
    """初始化LED"""
    red_led.off()
    green_led.off()
    blue_led.off()

def set_led_state(state):
    """设置LED状态"""
    red_led.off()
    green_led.off()
    blue_led.off()
    if state == SYSTEM_STATE_OFF:
        pass
    elif state == SYSTEM_STATE_READY:
        green_led.on()
    elif state == SYSTEM_STATE_ON:
        green_led.on()
    elif state == SYSTEM_STATE_FACE_TRACKING:
        blue_led.on()
    elif state == SYSTEM_STATE_start_recognition:
        blue_led.on()

def connect_wifi():
    """连接WiFi"""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if wlan.isconnected():
            wlan.disconnect()
            time.sleep(1)
        wlan.connect(SSID, KEY)
        for i in range(30):
            if wlan.isconnected():
                break
            time.sleep_ms(500)
        if wlan.isconnected():
            print("✅ WiFi连接成功!")
            return True
        else:
            print("❌ WiFi连接失败!")
            return False
    except Exception as e:
        print(f"❌ WiFi连接异常: {e}")
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

def cleanup_retained_messages():
    """清理可能存在的保留消息"""
    try:
        # 向相同主题发布空消息来清除保留消息
        topics_to_clean = [CAMERA_CONTROL_TOPIC, VIDEO_TOPIC, STATUS_TOPIC]
        for topic in topics_to_clean:
            # 发布空消息，retain=True 来清除之前的保留消息
            publish_message_safe(topic, "", qos=0)
            print(f"🧹 清理主题保留消息: {topic}")
            time.sleep_ms(100)
    except Exception as e:
        print(f"⚠️ 清理保留消息失败: {e}")

def connect_mqtt():
    """连接MQTT服务器 - 增强版本"""
    global mqtt_socket, connect_state
    try:
        print(f"连接MQTT: {EMQX_BROKER}:{EMQX_PORT}")
        if mqtt_socket:
            try:
                mqtt_socket.close()
            except:
                pass
            mqtt_socket = None

        addr = socket.getaddrinfo(EMQX_BROKER, EMQX_PORT)[0][-1]
        sock = socket.socket()
        sock.settimeout(5.0)  # 增加超时时间
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
        fixed_header = bytearray([0x10])  # CONNECT
        fixed_header.extend(encode_remaining_length(remaining_length))

        connect_packet = fixed_header + variable_header + payload
        sock.send(connect_packet)

        # 等待CONNACK
        sock.settimeout(5.0)
        connack = sock.recv(4)
        sock.settimeout(None)

        if len(connack) >= 4 and connack[0] == 0x20 and connack[3] == 0x00:
            print("✅ MQTT连接成功")

            # 清理可能的保留消息
            cleanup_retained_messages()

            # 订阅主题
            topics = [CAMERA_CONTROL_TOPIC, RECOGNITION_RESULT_TOPIC, FACE_COLLECTION_TOPIC]
            for topic in topics:
                packet_id = topics.index(topic) + 1
                subscribe_payload = bytearray()
                subscribe_payload.extend(struct.pack(">H", packet_id))
                subscribe_payload.extend(struct.pack(">H", len(topic)))
                subscribe_payload.extend(topic.encode())
                subscribe_payload.append(0)  # QoS 0

                remaining_len = len(subscribe_payload)
                subscribe_packet = bytearray([0x82, remaining_len]) + subscribe_payload
                sock.send(subscribe_packet)

                print(f"📝 已发送订阅请求: {topic}")
                time.sleep_ms(100)  # 给服务器处理时间

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

def publish_message_safe(topic, message, qos=0):
    """安全的发布消息到MQTT主题，带错误处理"""
    global mqtt_socket, connect_state
    if not mqtt_socket or connect_state != 0:
        return False
    try:
        # 确保消息是UTF-8编码的字符串
        if isinstance(message, dict):
            message = ujson.dumps(message)
        if isinstance(message, str):
            message_bytes = message.encode('utf-8')
        else:
            message_bytes = message
        fixed_header = bytearray([0x30 | (qos << 1)])
        variable_header = bytearray()
        topic_bytes = topic.encode('utf-8')
        variable_header.extend(struct.pack(">H", len(topic_bytes)))
        variable_header.extend(topic_bytes)
        if qos == 1:
            packet_id = 1
            variable_header.extend(struct.pack(">H", packet_id))
        payload = message_bytes
        remaining_length = len(variable_header) + len(payload)
        encoded_remaining = encode_remaining_length(remaining_length)
        fixed_header.extend(encoded_remaining)
        publish_packet = fixed_header + variable_header + payload
        mqtt_socket.settimeout(1.0)
        try:
            mqtt_socket.send(publish_packet)
            if qos == 1:
                puback = mqtt_socket.recv(4)
                if len(puback) < 4 or puback[0] != 0x40:
                    return False
            mqtt_socket.settimeout(None)
            return True
        except Exception as e:
            mqtt_socket.settimeout(None)
            connect_state = 1
            return False
    except Exception as e:
        connect_state = 1
        return False

def publish_message(topic, message, qos=0):
    """发布消息到MQTT主题（兼容旧代码）"""
    return publish_message_safe(topic, message, qos)

def send_control_command(command):
    """发送控制命令到Flask"""
    global last_control_command_time
    current_time = time.ticks_ms()
    # 防止频繁发送控制命令
    if time.ticks_diff(current_time, last_control_command_time) < control_command_interval:
        return False
    control_msg = {
        "command": command,
        "client_id": CLIENT_ID,
        "timestamp": current_time
    }
    success = publish_message_safe(FLASK_CONTROL_TOPIC, ujson.dumps(control_msg))
    if success:
        last_control_command_time = current_time
        print(f"✅ 已发送控制命令到Flask: {command}")
    else:
        print(f"❌ 发送控制命令到Flask失败: {command}")
    return success

def compress_frame(img):
    """压缩图像帧"""
    quality = FRAME_QUALITY
    max_attempts = 2
    for attempt in range(max_attempts):
        jpeg_data = img.compress(quality=quality)
        if not isinstance(jpeg_data, bytes):
            jpeg_data = bytes(jpeg_data)
        frame_size = len(jpeg_data)
        if frame_size <= MAX_FRAME_SIZE:
            return jpeg_data, frame_size, quality
        quality = max(20, quality - 20)
    return jpeg_data, frame_size, quality

def send_video_frame():
    """发送视频帧"""
    global frame_count
    if system_state < SYSTEM_STATE_ON or connect_state != 0:
        return False
    try:
        img = sensor.snapshot()
        jpeg_data, frame_size, actual_quality = compress_frame(img)
        if frame_size > MAX_FRAME_SIZE:
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
        if publish_message_safe(VIDEO_TOPIC, message_json, qos=0):
            frame_count += 1
            if frame_count % 20 == 0:
                print("📹 已发送视频帧 #{}, 大小: {} 字节".format(frame_count, frame_size))
            return True
        else:
            return False
    except Exception as e:
        return False

def extract_command_from_mqtt_packet(data):
    """从MQTT数据包中提取命令，支持字符串命令"""
    try:
        # 检查是否是有效的PUBLISH包 (0x30)
        if len(data) < 2 or data[0] != 0x30:
            return None

        # 剩余长度
        remaining_length = data[1]

        # 检查数据包是否完整
        expected_length = 2 + remaining_length
        if len(data) < expected_length:
            return None

        # 主题长度 (2字节)
        if len(data) < 4:
            return None
        topic_length = (data[2] << 8) | data[3]

        # 提取主题
        if 4 + topic_length > len(data):
            return None

        topic = data[4:4 + topic_length].decode('utf-8')

        # 只处理camera_control主题
        if topic != "camera_control":
            return None

        # 计算payload起始位置
        payload_start = 4 + topic_length

        # 检查是否有Packet ID (QoS > 0)
        qos = (data[0] & 0x06) >> 1
        if qos > 0:
            payload_start += 2

        # 计算payload长度
        payload_length = remaining_length - 2 - topic_length
        if qos > 0:
            payload_length -= 2

        # 检查payload位置是否有效
        if payload_start + payload_length > len(data):
            return None

        # 提取payload
        payload = data[payload_start:payload_start + payload_length]

        # 将payload解码为字符串
        try:
            command_str = payload.decode('utf-8')
        except:
            command_str = payload.decode('latin-1')

        return command_str

    except Exception as e:
        return None

def check_messages():
    """检查并处理接收到的MQTT消息"""
    global mqtt_socket, connect_state, pending_commands, last_command_time, last_human_command_time
    if not mqtt_socket or connect_state != 0:
        return False

    try:
        mqtt_socket.setblocking(False)
        data = mqtt_socket.recv(512)
        if data:
            # 检查是否是订阅确认包，如果是则忽略
            if len(data) >= 5 and data[0] == 0x90:
                return False

            # 检查是否是连接确认包，如果是则忽略
            if len(data) >= 4 and data[0] == 0x20:
                return False

            # 提取命令
            command = extract_command_from_mqtt_packet(data)

            if command:
                current_time = time.ticks_ms()

                # 处理系统控制命令（单字符）
                if len(command) == 1 and command in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A"]:
                    if last_command_time > 0:
                        time_diff = time.ticks_diff(current_time, last_command_time)
                        if time_diff < 1000:  # 1秒内重复命令可能是保留消息
                            return False

                    # 更新全局变量
                    last_command_time = current_time

                    # 将命令添加到待处理队列
                    pending_commands.append(command)
                    return True

                # 处理人体跟踪控制命令（字符串）
                elif len(command) > 1 and human_tracking_enabled:
                    # 检查命令间隔，防止过密
                    if time.ticks_diff(current_time, last_human_command_time) < human_command_interval:
                        return False

                    last_human_command_time = current_time

                    # 处理人体跟踪控制指令
                    if command == "forward":
                        move_forward()
                        print("🎯 收到人体跟踪指令: forward")
                    elif command == "backward":
                        move_backward()
                        print("🎯 收到人体跟踪指令: backward")
                    elif command == "left":
                        turn_left()
                        print("🎯 收到人体跟踪指令: left")
                    elif command == "right":
                        turn_right()
                        print("🎯 收到人体跟踪指令: right")
                    elif command == "stop":
                        stop_moving()
                        print("🎯 收到人体跟踪指令: stop")
                    else:
                        print(f"⚠️ 未知的人体跟踪指令: {command}")

                    return True
                elif len(command) > 1 and not human_tracking_enabled:
                    # 收到人体跟踪指令但人体跟踪未启用，打印警告
                    print(f"⚠️ 收到人体跟踪指令 '{command}' 但人体跟踪未启用，忽略")
                    return True

        return False
    except Exception as e:
        # 没有数据是可接受的异常
        if "EAGAIN" not in str(e) and "11" not in str(e):
            print(f"❌ 接收消息异常: {e}")
        return False

def process_control_command(command):
    """处理控制命令 - 修改版：避免0命令重复唤醒"""
    global system_state, human_tracking_enabled

    print(f"🔧 处理命令: '{command}'，当前状态: {system_state}")
    original_state = system_state

    if command == "0":
        # 修改后的0命令逻辑：
        # - 如果系统是关闭状态，进入准备状态
        # - 如果系统是准备状态，进入追踪状态
        # - 如果系统已经是激活状态（ON、FACE_TRACKING、start_recognition），忽略命令
        if system_state == SYSTEM_STATE_OFF:
            system_state = SYSTEM_STATE_READY
            print("✅ 收到指令0 - 从OFF切换到READY（准备）")
            set_led_state(SYSTEM_STATE_READY)
            ack_state = system_state
        elif system_state == SYSTEM_STATE_READY:
            system_state = SYSTEM_STATE_FACE_TRACKING
            print("✅ 收到指令0 - 从READY切换到FACE_TRACKING（追踪）")
            set_led_state(SYSTEM_STATE_FACE_TRACKING)
            ack_state = system_state
        else:
            # 系统已经是激活状态，忽略0命令
            print("⚠️ 系统已经是激活状态，忽略0命令")
            # 保持当前状态不变，但仍发送确认
            ack_state = system_state

    elif command == "1":
        # 1命令仍然可以随时从任何状态切换到ON
        system_state = SYSTEM_STATE_ON
        print("✅ 收到指令1 - 摄像头开启但不追踪")
        set_led_state(SYSTEM_STATE_ON)
        ack_state = system_state
    elif command == "2":
        # 2命令可以从任何状态切换到识别状态
        system_state = SYSTEM_STATE_start_recognition
        print("✅ 收到指令2 - 开启人脸识别并保持追踪")
        set_led_state(SYSTEM_STATE_start_recognition)
        send_control_command("start_recognition")
        ack_state = system_state
    elif command == "3":
        # 3命令可以从识别状态切换回追踪
        if system_state == SYSTEM_STATE_start_recognition:
            system_state = SYSTEM_STATE_FACE_TRACKING
            print("✅ 收到指令3 - 关闭人脸识别但保持追踪")
            set_led_state(SYSTEM_STATE_FACE_TRACKING)
            send_control_command("stop_recognition")
        else:
            # 如果不是识别状态，切换到追踪
            system_state = SYSTEM_STATE_FACE_TRACKING
            print("✅ 收到指令3 - 切换到追踪状态")
            set_led_state(SYSTEM_STATE_FACE_TRACKING)
        ack_state = system_state
    elif command == "4":
        # 新命令：打开上下班打卡系统
        print("✅ 收到指令4 - 打开上下班打卡系统")
        send_control_command("attendance_on")
        # 不改变系统状态
        ack_state = 104
    elif command == "5":
        # 新命令：关闭上下班打卡系统
        print("✅ 收到指令5 - 关闭上下班打卡系统")
        send_control_command("attendance_off")
        # 不改变系统状态
        ack_state = 105
    elif command == "6":
        # 6命令可以完全关闭系统，允许再次唤醒
        system_state = SYSTEM_STATE_OFF
        print("✅ 收到指令6 - 摄像头关闭舵机复位")
        middle()
        set_led_state(SYSTEM_STATE_OFF)
        ack_state = system_state
    elif command == "7":
        # 新命令：舵机复位但不改变系统状态
        print("✅ 收到指令7 - 舵机复位")
        middle()
        # 不改变系统状态
        ack_state = 107
    elif command == "8":
        # 新命令：开始人脸采集
        print("✅ 收到指令8 - 开始人脸采集")
        send_face_collection_command()
        # 不改变系统状态
        ack_state = 108
    elif command == "9":
        # 命令9：开启人体跟踪
        print("✅ 收到指令9 - 开启人体跟踪")
        if send_control_command("9"):  # 发送到Flask
            human_tracking_enabled = True
            print("🎯 OpenMV人体跟踪已启用")
        else:
            print("❌ 发送控制命令失败")
        # 不改变系统状态
        ack_state = 109
    elif command == "A":
        # 命令A（代表10）：关闭人体跟踪
        print("✅ 收到指令A - 关闭人体跟踪")
        # 1. 先停止移动
        stop_moving()

        # 2. 关闭OpenMV的人体跟踪
        human_tracking_enabled = False
        print("⏹️ OpenMV人体跟踪已关闭")

        # 3. 发送命令到Flask
        if send_control_command("A"):  # 发送到Flask
            print("📤 已发送关闭指令到Flask")
        else:
            print("❌ 发送控制命令失败")

        # 4. 不改变系统状态
        ack_state = 110
    else:
        print(f"❌ 未知命令: '{command}'")
        return

    # 发送状态确认
    if command in ["4", "5", "7", "8", "9", "A"]:
        # 对于不改变系统状态的命令，发送特定确认码
        status_msg = {
            "status": ack_state,
            "client_id": CLIENT_ID,
            "timestamp": time.ticks_ms(),
            "message": f"Command {command} processed",
            "command_received": command,
            "system_state": ack_state,
            "is_command_response": True,
            "original_system_state": original_state,
            "human_tracking_enabled": human_tracking_enabled if command in ["9", "A"] else None
        }
    else:
        # 对于改变系统状态的命令
        status_msg = {
            "status": system_state,
            "client_id": CLIENT_ID,
            "timestamp": time.ticks_ms(),
            "message": get_state_message(system_state),
            "command_received": command,
            "system_state": system_state,
            "is_command_response": True,
            "human_tracking_enabled": human_tracking_enabled
        }

    print(f"📤 发送命令确认: 命令={command}, 系统状态={system_state}, 人体跟踪={'开启' if human_tracking_enabled else '关闭'}")

    # 发送确认消息
    success = False
    for attempt in range(2):
        success = publish_message_safe(STATUS_TOPIC, ujson.dumps(status_msg), qos=0)
        if success:
            break
        time.sleep_ms(50)

    if success:
        print("✅ 命令确认发送成功")
    else:
        print("❌ 命令确认发送失败")

    print(f"🎯 命令{command}处理完成，最终系统状态: {system_state}, 人体跟踪: {'开启' if human_tracking_enabled else '关闭'}")

def send_face_collection_command():
    """发送人脸采集命令到Flask"""
    collection_msg = {
        "action": "start_collection",
        "client_id": CLIENT_ID,
        "timestamp": time.ticks_ms(),
        "source": "openmv"
    }

    message_json = ujson.dumps(collection_msg)
    print(f"📤 发送人脸采集命令: {message_json}")

    success = publish_message_safe(FACE_COLLECTION_TOPIC, message_json)
    if success:
        print("✅ 人脸采集命令发送成功")
    else:
        print("❌ 人脸采集命令发送失败")
    return success

def process_pending_commands():
    """处理待处理命令队列"""
    global pending_commands
    if pending_commands:
        command = pending_commands.pop(0)
        print(f"🔄 从队列中取出命令: '{command}'，队列剩余: {len(pending_commands)}")
        process_control_command(command)
        return True
    return False

def get_state_message(state):
    """获取状态描述信息"""
    messages = {
        SYSTEM_STATE_OFF: "摄像头关闭",
        SYSTEM_STATE_READY: "摄像头准备就绪",
        SYSTEM_STATE_ON: "摄像头开启但不追踪",
        SYSTEM_STATE_FACE_TRACKING: "摄像头开启并追踪人脸",
        SYSTEM_STATE_start_recognition: "摄像头开启并识别人脸"
    }
    return messages.get(state, "未知状态")

def send_status():
    """发送状态信息"""
    global frame_count, system_state
    status_msg = {
        "frames_sent": frame_count,
        "status": system_state,
        "client_id": CLIENT_ID,
        "system_state": system_state,
        "camera_active": system_state >= SYSTEM_STATE_ON,
        "tracking_active": system_state >= SYSTEM_STATE_FACE_TRACKING,
        "recognition_active": system_state == SYSTEM_STATE_start_recognition,
        "pan_angle": current_pan_angle,
        "tilt_angle": current_tilt_angle,
        "human_tracking_enabled": human_tracking_enabled
    }
    return publish_message_safe(STATUS_TOPIC, ujson.dumps(status_msg), qos=0)

def attempt_reconnect():
    """尝试重新连接"""
    global connect_state
    print("🔄 尝试重新连接MQTT...")
    connect_state = 2
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
    global last_message_check, last_frame_time

    print("=== OpenMV 视频流与跟踪系统 ===")
    print(f"客户端ID: {CLIENT_ID}")

    # 初始化硬件
    if not init_camera():
        blink_red_and_reset()
    if not init_servos():
        blink_red_and_reset()
    init_led()

    # LED闪烁指示启动
    for i in range(3):
        green_led.on()
        time.sleep_ms(200)
        green_led.off()
        time.sleep_ms(200)

    set_led_state(SYSTEM_STATE_OFF)
    print("✅ 系统已启动，等待控制指令...")

    # 连接网络和MQTT
    if not connect_wifi():
        blink_red_and_reset()
    if not connect_mqtt():
        blink_red_and_reset()

    print("\n🚀 系统就绪!")

    # 发送就绪状态
    status_msg = {
        "status": "ready",
        "client_id": CLIENT_ID,
        "timestamp": time.ticks_ms(),
        "message": "系统就绪，等待控制指令"
    }
    publish_message_safe(STATUS_TOPIC, ujson.dumps(status_msg), qos=0)

    # 初始化时间变量
    current_time = time.ticks_ms()
    last_status_time = current_time
    last_frame_time = current_time
    last_reconnect_attempt = current_time
    last_led_blink = current_time
    last_message_check = current_time

    # 设置初始标志，忽略启动时的保留消息
    ignore_initial_messages = True
    initial_message_ignore_time = current_time + 5000  # 增加到5秒

    reconnect_interval = 5000
    led_blink_interval = 500
    led_blink_state = False
    frame_counter = 0
    message_check_counter = 0

    print("🎯 进入事件循环...")
    print("📋 可用命令: 0(准备/追踪), 1(开启不追踪), 2(识别), 3(追踪), 4(打卡开), 5(打卡关), 6(关闭), 7(舵机复位), 8(人脸采集), 9(开启人体跟踪), A(关闭人体跟踪)")

    # 新增：清空初始队列
    pending_commands.clear()

    # 新增：启动延迟，避免处理保留消息
    print("⏳ 启动延迟5秒，避免处理保留消息...")
    startup_delay_end = current_time + 5000

    while True:
        current_time = time.ticks_ms()

        # 检查是否过了初始忽略期
        if ignore_initial_messages and time.ticks_diff(current_time, initial_message_ignore_time) > 0:
            ignore_initial_messages = False
            print("✅ 初始消息忽略期结束，开始正常处理消息")

        # 检查启动延迟
        if time.ticks_diff(current_time, startup_delay_end) < 0:
            # 启动延迟期间，清空所有收到的消息
            try:
                mqtt_socket.setblocking(False)
                while True:
                    try:
                        data = mqtt_socket.recv(512)
                        if not data:
                            break
                    except:
                        break
                mqtt_socket.setblocking(True)
            except:
                pass
            continue

        # 消息检查 - 这是您缺少的关键部分！
        message_check_counter += 1
        if time.ticks_diff(current_time, last_message_check) > 2:
            messages_found = False
            for i in range(5):
                if check_messages():
                    messages_found = True
            # 处理所有待处理命令
            if not ignore_initial_messages:
                if process_pending_commands():
                    print("⚡ 命令处理完成")
            last_message_check = current_time

        # 处理连接状态
        if connect_state == 1:
            if time.ticks_diff(current_time, last_reconnect_attempt) > reconnect_interval:
                if attempt_reconnect():
                    if system_state >= SYSTEM_STATE_ON:
                        status_msg = {
                            "status": "reconnected",
                            "system_state": system_state,
                            "client_id": CLIENT_ID,
                            "timestamp": current_time,
                            "message": "重新连接成功，恢复视频流"
                        }
                        publish_message_safe(STATUS_TOPIC, ujson.dumps(status_msg), qos=0)
                else:
                    blink_red_and_reset()
                last_reconnect_attempt = current_time

        # 视频流处理
        elif connect_state == 0:
            if system_state >= SYSTEM_STATE_ON:
                if time.ticks_diff(current_time, last_frame_time) > 50:
                    if send_video_frame():
                        frame_counter += 1
                    last_frame_time = current_time

            # 人脸跟踪
            if system_state >= SYSTEM_STATE_FACE_TRACKING:
                face_tracking()

            # 定期发送状态
            if time.ticks_diff(current_time, last_status_time) > 10000:
                send_status()
                gc.collect()
                last_status_time = current_time
                # 打印性能统计
                fps = frame_counter / 10
                frame_counter = 0
                message_check_counter = 0
                print(f"📊 性能统计: {fps:.1f} FPS, 队列命令: {len(pending_commands)}, 系统状态: {system_state}, 人体跟踪: {'开启' if human_tracking_enabled else '关闭'}")

        # 识别状态下的LED闪烁
        if system_state == SYSTEM_STATE_start_recognition:
            if time.ticks_diff(current_time, last_led_blink) > led_blink_interval:
                led_blink_state = not led_blink_state
                blue_led.on() if led_blink_state else blue_led.off()
                last_led_blink = current_time
        # 人体跟踪状态下的LED指示
        elif human_tracking_enabled:
            if time.ticks_diff(current_time, last_led_blink) > 300:  # 更快的闪烁频率
                led_blink_state = not led_blink_state
                if led_blink_state:
                    blue_led.on()
                    red_led.off()
                else:
                    blue_led.off()
                    red_led.on()
                last_led_blink = current_time
        else:
            # 非人体跟踪状态，恢复LED状态
            set_led_state(system_state)

        # 极短延迟
        time.sleep_ms(1)


# 启动程序
try:
    main()
except Exception as e:
    print(f"程序错误: {e}")
    blink_red_and_reset()
finally:
    try:
        if mqtt_socket:
            mqtt_socket.close()
    except:
        pass
    red_led.off()
    green_led.off()
    blue_led.off()
    print("程序结束")
