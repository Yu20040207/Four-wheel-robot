# openmv_emqx_tracking_system_integrated.py
import sensor
import image
import network
import time
import socket
import struct
import ujson
import gc
import machine
from pyb import LED
from math import pi, isnan

# PCA9685类 - 使用正确的OpenMV I2C方法
class PCA9685:
    def __init__(self, i2c, address=0x40):
        self.i2c = i2c
        self.address = address
        self.reset()

    def _write(self, address, value):
        # OpenMV使用mem_write而不是writeto_mem
        try:
            self.i2c.mem_write(value, self.address, address)
            return True
        except Exception as e:
            print(f"I2C写入错误: {e}")
            return False

    def _read(self, address):
        # OpenMV使用mem_read而不是readfrom_mem
        try:
            return self.i2c.mem_read(1, self.address, address)[0]
        except Exception as e:
            print(f"I2C读取错误: {e}")
            return 0

    def reset(self):
        self._write(0x00, 0x00)  # Mode1

    def freq(self, freq=None):
        if freq is None:
            return int(25000000.0 / 4096 / (self._read(0xFE) - 0.5))
        prescale = int(25000000.0 / 4096.0 / freq + 0.5)
        old_mode = self._read(0x00)  # Mode 1
        self._write(0x00, (old_mode & 0x7F) | 0x10)  # Mode 1, sleep
        self._write(0xFE, prescale)  # Prescale
        self._write(0x00, old_mode)  # Mode 1
        time.sleep_us(5)
        self._write(0x00, old_mode | 0xA1)  # Mode 1, autoincrement on

    def pwm(self, index, on=None, off=None):
        if on is None or off is None:
            # 读取4个字节的数据
            try:
                data = self.i2c.mem_read(4, self.address, 0x06 + 4 * index)
                return struct.unpack("<HH", data)
            except Exception as e:
                print(f"PWM读取错误: {e}")
                return (0, 0)
        data = struct.pack("<HH", on, off)
        # 写入4个字节的数据
        try:
            self.i2c.mem_write(data, self.address, 0x06 + 4 * index)
            return True
        except Exception as e:
            #print(f"PWM写入错误: {e}")
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

# PID控制器类
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
            if self._integrator < -self._imax: self._integrator = -self._imax
            elif self._integrator > self._imax: self._integrator = self._imax
            output += self._integrator
        return output
    def reset_I(self):
        self._integrator = 0
        self._last_derivative = float('nan')

# 配置区域
SSID = "MTCPC"
KEY = "mt12345mt"

# EMQX服务器配置
EMQX_BROKER = "192.168.13.225"
EMQX_PORT = 1883
EMQX_USERNAME = "sy"
EMQX_PASSWORD = "123"

# MQTT主题
VIDEO_TOPIC = "openmv/video/stream"
STATUS_TOPIC = "openmv/status"
RECOGNITION_RESULT_TOPIC = "openmv_recognition_result"
RECOGNITION_ACK_TOPIC = "openmv/recognition_ack"
FLASK_CONTROL_TOPIC = "flask/control"

# 视频流配置
FRAME_SIZE = sensor.QVGA  # 160x120
FRAME_QUALITY = 70         # 降低质量以减少数据量
TARGET_FPS = 20            # 降低帧率以给PWM更多时间
MAX_FRAME_SIZE = 15000     # 限制最大帧大小(8KB)
MAX_MESSAGE_SIZE = 27000   # 限制最大消息大小(10KB)

# 系统状态定义 - 直接启动到跟踪状态
SYSTEM_STATE_FACE_ON = 3       # 摄像头开启并开始追踪人脸

# 全局变量
mqtt_socket = None
frame_count = 0
last_recognition_time = 0
received_messages = []
message_buffer = bytearray()
CLIENT_ID = "openmv_camera_001"

# PCA9685舵机控制相关
pca = None
pan_servo_channel = 0   # S1通道，用于水平舵机
tilt_servo_channel = 1  # S2通道，用于垂直舵机

# 舵机控制参数（根据您的舵机调整这些值）
SERVO_MIN = 150   # 最小角度对应值
SERVO_MAX = 450   # 最大角度对应值
SERVO_MID = 300   # 中间位置对应值

# PID控制器
pan_pid = None
tilt_pid = None
face_cascade = None

# 当前舵机角度跟踪
current_pan_angle = 0
current_tilt_angle = 0

# 连接状态
CONNECT_STATE_NORMAL = 0
CONNECT_STATE_ERROR = 1
CONNECT_STATE_RECONNECTING = 2
CONNECT_STATE_RESETTING = 3
connect_state = CONNECT_STATE_NORMAL
reconnect_attempts = 0
max_reconnect_attempts = 3
last_reconnect_attempt = 0
reconnect_delay = 5000

# 系统重置相关
reset_attempts = 0
max_reset_attempts = 1
last_reset_attempt = 0
reset_delay = 10000

# LED状态
LED_OFF = 0
LED_READY = 1
LED_CAMERA_ON = 2
LED_TRACKING = 3
LED_RECOGNITION = 4
LED_ERROR = 5
LED_RECONNECTING = 6
LED_RESETTING = 7

current_led_state = LED_OFF
led_blink_state = False
last_led_change = 0
led_blink_interval = 500
recognition_led_start = 0

# 发送统计
send_errors = 0
max_send_errors = 5
last_successful_send = 0
consecutive_errors = 0
max_consecutive_errors = 10

# 系统状态 - 直接启动到跟踪状态
system_state = SYSTEM_STATE_FACE_ON

# 舵机角度打印控制
last_angle_print_time = 0
angle_print_interval = 1000  # 1秒打印一次

# 摄像头模式
CAMERA_MODE_GRAYSCALE = 1
current_camera_mode = CAMERA_MODE_GRAYSCALE  # 直接使用灰度模式

# 人脸检测状态
last_face_detected = False
face_detected_blink_start = 0
face_detected_blink_duration = 300  # 绿灯闪烁持续时间(ms)

# 舵机控制状态
servo_update_count = 0
last_servo_update_time = 0

def init_camera(mode=CAMERA_MODE_GRAYSCALE):
    """简化版摄像头初始化"""
    global current_camera_mode
    try:
        sensor.reset()

        # 使用与第一段程序相同的设置
        sensor.set_contrast(3)
        sensor.set_gainceiling(16)

        sensor.set_pixformat(sensor.GRAYSCALE)
        mode_str = "灰度"

        sensor.set_framesize(FRAME_SIZE)
        sensor.skip_frames(10)
        sensor.set_auto_whitebal(False)

        current_camera_mode = mode
        print("摄像头初始化完成 - {}模式, 分辨率: {}x{}".format(mode_str, sensor.width(), sensor.height()))
        return True
    except Exception as e:
        print(f"❌ 摄像头初始化失败: {e}")
        return False

def init_pca9685():
    """初始化PCA9685舵机扩展板"""
    global pca, pan_servo_channel, tilt_servo_channel, pan_pid, tilt_pid
    global current_pan_angle, current_tilt_angle

    try:
        from pyb import I2C
        print("🔄 初始化PCA9685舵机控制器...")

        # 使用I2C2总线，P4=SCL, P5=SDA
        i2c = I2C(2, I2C.MASTER, baudrate=100000)  # 使用I2C2，100kHz
        print("扫描I2C总线...")
        devices = i2c.scan()
        print("找到的I2C设备:", [hex(device) for device in devices])

        # 检查是否找到PCA9685 (地址0x40)
        if 0x40 in devices:
            pca = PCA9685(i2c)
            # 测试PCA9685通信
            print("测试PCA9685通信...")
            try:
                pca.freq(50)  # 设置PWM频率为50Hz，适用于舵机
                # 测试写入和读取
                pca.duty(0, SERVO_MID)
                time.sleep_ms(100)
                read_value = pca.duty(0)
                print(f"PCA9685通信测试: 写入{SERVO_MID}, 读取{read_value}")
                print("✅ PCA9685初始化成功")
            except Exception as e:
                print(f"❌ PCA9685通信测试失败: {e}")
                raise
        else:
            print("❌ 在地址0x40未找到PCA9685")
            print("可用地址:", [hex(addr) for addr in devices])
            raise Exception("PCA9685未找到")

        # 使用与第一段程序相同的PID参数
        pan_pid = PID(p=0.18, i=0, d=0.003, imax=90)    # 水平方向PID
        tilt_pid = PID(p=0.2, i=0, d=0.006, imax=90)   # 垂直方向PID

        # 舵机复位到中间位置
        middle()

        print("✅ PCA9685舵机控制器初始化完成")
        return True
    except Exception as e:
        print(f"❌ PCA9685初始化失败: {e}")
        # 创建模拟PCA9685对象以便调试
        class DummyPCA:
            def duty(self, channel, value):
                print(f"DummyPCA: 设置通道 {channel} 为 {value}")
                return True
        pca = DummyPCA()
        return False

def set_servo_angle(channel, angle):
    """设置舵机角度（使用PCA9685）"""
    global pca, current_pan_angle, current_tilt_angle
    if pca is None:
        print("错误: PCA9685未初始化!")
        return

    # 将角度转换为PWM值
    # 角度范围从-90°到90°对应PWM值从SERVO_MIN到SERVO_MAX
    pulse_width = SERVO_MIN + ((angle + 90) / 180.0) * (SERVO_MAX - SERVO_MIN)
    pulse_width = int(pulse_width)

    # 限制PWM值范围
    pulse_width = max(SERVO_MIN, min(SERVO_MAX, pulse_width))

    # 设置PWM，添加重试机制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            success = pca.duty(channel, pulse_width)
            if success is not False:  # 如果成功或没有返回值(假设成功)
                # 更新当前角度
                if channel == pan_servo_channel:
                    current_pan_angle = angle
                elif channel == tilt_servo_channel:
                    current_tilt_angle = angle
                return  # 成功设置，退出函数
        except Exception as e:
            print(f"设置舵机角度错误 (尝试 {attempt+1}/{max_retries}): {e}")

        # 如果不是最后一次尝试，等待一段时间后重试
        if attempt < max_retries - 1:
            time.sleep_ms(10)

    print(f"设置舵机角度失败，已尝试 {max_retries} 次")

def middle():
    """舵机回归中位"""
    global current_pan_angle, current_tilt_angle

    current_pan_angle = 0
    current_tilt_angle = 0

    print("🔄 舵机复位到中间位置...")

    set_servo_angle(pan_servo_channel, current_pan_angle)
    set_servo_angle(tilt_servo_channel, current_tilt_angle)
    time.sleep(1)  # 延时1秒

    print("✅ 舵机复位完成")

def init_face_cascade():
    """初始化人脸检测"""
    global face_cascade
    try:
        face_cascade = image.HaarCascade("/rom/haarcascade_frontalface.cascade", stages=25)
        print("✅ 人脸检测模型加载完成")
        return True
    except Exception as e:
        print(f"❌ 人脸检测模型加载失败: {e}")
        try:
            # 尝试备用的人脸检测器
            face_cascade = image.HaarCascade("face", stages=25)
            print("✅ 备用人脸检测器加载成功")
            return True
        except:
            print("❌ 所有人脸检测器加载失败")
            face_cascade = None
            return False

def init_led():
    """初始化LED"""
    global red_led, green_led, blue_led
    try:
        red_led = LED(1)
        green_led = LED(2)
        blue_led = LED(3)
        red_led.off()
        green_led.off()
        blue_led.off()
        print("✅ LED初始化完成")
        return True
    except Exception as e:
        print(f"❌ LED初始化失败: {e}")
        return False

def update_led():
    """更新LED状态"""
    global current_led_state, led_blink_state, last_led_change, recognition_led_start
    global face_detected_blink_start, last_face_detected

    current_time = time.ticks_ms()

    # 处理人脸检测到的绿灯闪烁
    if face_detected_blink_start > 0:
        if time.ticks_diff(current_time, face_detected_blink_start) < face_detected_blink_duration:
            # 绿灯闪烁期间
            green_led.on()
            return
        else:
            # 闪烁结束，恢复正常状态
            face_detected_blink_start = 0
            # 恢复之前的LED状态
            if current_led_state == LED_TRACKING:
                blue_led.on()
                green_led.off()
                red_led.off()
            elif current_led_state == LED_RECOGNITION:
                blue_led.on()
                green_led.off()
                red_led.off()
            elif current_led_state == LED_CAMERA_ON:
                green_led.on()
                red_led.off()
                blue_led.off()
            elif current_led_state == LED_READY:
                green_led.on()
                red_led.off()
                blue_led.off()
            else:
                red_led.off()
                green_led.off()
                blue_led.off()
            last_led_change = current_time

    # 特殊状态处理
    if current_led_state == LED_RECONNECTING:
        if time.ticks_diff(current_time, last_led_change) > 300:
            led_blink_state = not led_blink_state
            last_led_change = current_time
            if led_blink_state:
                red_led.on()
                green_led.on()
                blue_led.off()
            else:
                red_led.off()
                green_led.off()
                blue_led.off()
        return

    if current_led_state == LED_RESETTING:
        if time.ticks_diff(current_time, last_led_change) > 200:
            led_blink_state = not led_blink_state
            last_led_change = current_time
            if led_blink_state:
                red_led.on()
                green_led.off()
                blue_led.off()
            else:
                red_led.off()
                green_led.off()
                blue_led.off()
        return

    # 常规状态处理
    if time.ticks_diff(current_time, last_led_change) > led_blink_interval:
        led_blink_state = not led_blink_state
        last_led_change = current_time

        if current_led_state == LED_OFF:
            red_led.off()
            green_led.off()
            blue_led.off()
        elif current_led_state == LED_READY:
            if led_blink_state:
                green_led.on()
                red_led.off()
                blue_led.off()
            else:
                green_led.off()
                red_led.off()
                blue_led.off()
        elif current_led_state == LED_CAMERA_ON:
            green_led.on()
            red_led.off()
            blue_led.off()
        elif current_led_state == LED_TRACKING:
            if led_blink_state:
                blue_led.on()
                green_led.off()
                red_led.off()
            else:
                blue_led.off()
                green_led.off()
                red_led.off()
        elif current_led_state == LED_RECOGNITION:
            if led_blink_state:
                blue_led.on()
                green_led.off()
                red_led.off()
            else:
                blue_led.off()
                green_led.off()
                red_led.off()
        elif current_led_state == LED_ERROR:
            if led_blink_state:
                red_led.on()
                green_led.off()
                blue_led.off()
            else:
                red_led.off()
                green_led.off()
                blue_led.off()

def set_led_state(state):
    """设置LED状态"""
    global current_led_state, last_led_change, recognition_led_start
    if current_led_state == state and state != LED_RECOGNITION:
        return
    current_led_state = state
    last_led_change = time.ticks_ms()
    recognition_led_start = 0

    # 立即设置LED状态
    if state == LED_OFF:
        red_led.off()
        green_led.off()
        blue_led.off()
    elif state == LED_READY:
        green_led.on()
        red_led.off()
        blue_led.off()
    elif state == LED_CAMERA_ON:
        green_led.on()
        red_led.off()
        blue_led.off()
    elif state == LED_TRACKING:
        blue_led.on()
        green_led.off()
        red_led.off()
    elif state == LED_RECOGNITION:
        blue_led.on()
        green_led.off()
        red_led.off()
    elif state == LED_ERROR:
        red_led.on()
        green_led.off()
        blue_led.off()
    elif state == LED_RECONNECTING:
        red_led.on()
        green_led.on()
        blue_led.off()
    elif state == LED_RESETTING:
        red_led.on()
        green_led.off()
        blue_led.off()

def trigger_face_detected_blink():
    """触发检测到人脸时的绿灯闪烁"""
    global face_detected_blink_start
    face_detected_blink_start = time.ticks_ms()
    print("🟢 检测到人脸 - 绿灯闪烁")

def connect_wifi():
    """连接WiFi"""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        print("连接WiFi: {}...".format(SSID))

        if wlan.isconnected():
            wlan.disconnect()
            time.sleep(1)

        wlan.connect(SSID, KEY)
        timeout = 30
        while not wlan.isconnected() and timeout > 0:
            time.sleep_ms(500)
            timeout -= 1
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

def check_wifi_connection():
    """检查WiFi连接状态"""
    try:
        wlan = network.WLAN(network.STA_IF)
        return wlan.isconnected()
    except:
        return False

def subscribe_topic(sock, topic):
    """订阅主题"""
    try:
        packet_id = 1
        subscribe_payload = bytearray()
        subscribe_payload.extend(struct.pack(">H", packet_id))
        subscribe_payload.extend(struct.pack(">H", len(topic)))
        subscribe_payload.extend(topic.encode())
        subscribe_payload.append(0)
        remaining_len = len(subscribe_payload)
        subscribe_packet = bytearray([0x82, remaining_len]) + subscribe_payload
        sock.send(subscribe_packet)

        sock.settimeout(3.0)
        suback = sock.recv(5)
        sock.settimeout(None)

        print(f"SUBACK响应: {suback.hex()}")
        print(f"✅ 成功订阅主题: {topic}")
        return True
    except Exception as e:
        print(f"订阅主题失败: {e}")
        return False

def connect_mqtt_socket():
    """使用原始Socket连接MQTT服务器"""
    global mqtt_socket, connect_state, reconnect_attempts, send_errors, consecutive_errors
    try:
        print(f"🔗 连接MQTT Socket: {EMQX_BROKER}:{EMQX_PORT}")

        if mqtt_socket:
            try:
                mqtt_socket.close()
            except:
                pass
            mqtt_socket = None
            time.sleep_ms(500)

        addr = socket.getaddrinfo(EMQX_BROKER, EMQX_PORT)[0][-1]
        sock = socket.socket()
        sock.settimeout(8.0)
        sock.connect(addr)
        sock.settimeout(None)
        print("✅ Socket连接成功")

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
        print("已发送CONNECT报文")

        sock.settimeout(5.0)
        connack = sock.recv(4)
        sock.settimeout(None)
        print("CONNACK响应:", connack.hex())

        if connack[0] == 0x20 and connack[3] == 0x00:
            print("✅ MQTT连接成功")
            # 订阅所有需要的主题
            topics = [RECOGNITION_RESULT_TOPIC, FLASK_CONTROL_TOPIC]
            for topic in topics:
                if not subscribe_topic(sock, topic):
                    print(f"❌ 订阅主题 {topic} 失败")
                    sock.close()
                    connect_state = CONNECT_STATE_ERROR
                    set_led_state(LED_ERROR)
                    return False

            mqtt_socket = sock
            connect_state = CONNECT_STATE_NORMAL
            reconnect_attempts = 0
            send_errors = 0
            consecutive_errors = 0
            set_led_state(LED_TRACKING)  # 直接设置为跟踪状态
            return True
        else:
            print("❌ MQTT连接失败")
            sock.close()
            connect_state = CONNECT_STATE_ERROR
            set_led_state(LED_ERROR)
            return False
    except Exception as e:
        print(f"❌ MQTT Socket连接失败: {e}")
        try:
            sock.close()
        except:
            pass
        connect_state = CONNECT_STATE_ERROR
        set_led_state(LED_ERROR)
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

def publish_message_safe(topic, message):
    """安全地发布消息到MQTT主题"""
    global mqtt_socket, connect_state, send_errors, last_successful_send, consecutive_errors

    if not mqtt_socket or connect_state != CONNECT_STATE_NORMAL:
        print("❌ MQTT Socket未连接或连接异常")
        connect_state = CONNECT_STATE_ERROR
        return False

    try:
        if isinstance(message, str):
            message_bytes = message.encode('utf-8')
        else:
            message_bytes = message

        if len(message_bytes) > MAX_MESSAGE_SIZE:
            print(f"❌ 消息过长: {len(message_bytes)} > {MAX_MESSAGE_SIZE} 字节")
            return False

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

        total_packet_size = len(publish_packet)
        if total_packet_size > 65535:
            print(f"❌ 数据包过大: {total_packet_size} 字节")
            return False

        mqtt_socket.settimeout(3.0)
        try:
            bytes_sent = mqtt_socket.send(publish_packet)
            mqtt_socket.settimeout(None)

            if bytes_sent == len(publish_packet):
                send_errors = 0
                consecutive_errors = 0
                last_successful_send = time.ticks_ms()
                return True
            else:
                print(f"❌ 发送不完整: {bytes_sent}/{len(publish_packet)} 字节")
                send_errors += 1
                consecutive_errors += 1
                return False
        except OSError as e:
            mqtt_socket.settimeout(None)
            print(f"❌ 发送失败: {e}")
            send_errors += 1
            consecutive_errors += 1
            try:
                mqtt_socket.close()
            except:
                pass
            mqtt_socket = None
            connect_state = CONNECT_STATE_ERROR
            return False

    except Exception as e:
        print(f"发布消息失败: {e}")
        send_errors += 1
        consecutive_errors += 1
        return False

def attempt_reconnect():
    """尝试重新连接"""
    global reconnect_attempts, last_reconnect_attempt, connect_state, send_errors

    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_reconnect_attempt) < reconnect_delay:
        return False

    if reconnect_attempts >= max_reconnect_attempts:
        print(f"❌ 已达到最大重连次数 ({max_reconnect_attempts})，将尝试系统重置")
        connect_state = CONNECT_STATE_RESETTING
        return False

    reconnect_attempts += 1
    last_reconnect_attempt = current_time
    print(f"🔄 尝试重新连接 ({reconnect_attempts}/{max_reconnect_attempts})...")
    set_led_state(LED_RECONNECTING)

    if not check_wifi_connection():
        print("WiFi连接已断开，尝试重新连接WiFi...")
        if connect_wifi():
            print("WiFi重新连接成功")
        else:
            print("WiFi重新连接失败")
            return False

    if connect_mqtt_socket():
        print("✅ MQTT重新连接成功")
        return True
    else:
        print(f"❌ MQTT重新连接失败 ({reconnect_attempts}/{max_reconnect_attempts})")
        return False

def attempt_system_reset():
    """尝试系统重置"""
    global reset_attempts, last_reset_attempt, connect_state

    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_reset_attempt) < reset_delay:
        return False

    if reset_attempts >= max_reset_attempts:
        print(f"❌ 已达到最大重置次数 ({max_reset_attempts})，系统将保持错误状态")
        set_led_state(LED_ERROR)
        return False

    reset_attempts += 1
    last_reset_attempt = current_time
    print(f"🔄 尝试系统重置 ({reset_attempts}/{max_reset_attempts})...")
    set_led_state(LED_RESETTING)

    try:
        print("执行软重置...")
        machine.reset()
    except Exception as e:
        print(f"❌ 软重置失败: {e}")
        try:
            print("尝试硬重置...")
            machine.reset()
        except:
            print("❌ 硬重置失败")

    return False

def compress_frame(img):
    """压缩图像帧，确保大小在限制内"""
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

def send_frame():
    """发送一帧图像"""
    global frame_count, connect_state, send_errors

    if connect_state != CONNECT_STATE_NORMAL:
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

        if len(message_json) > MAX_MESSAGE_SIZE:
            print(f"❌ JSON消息过大: {len(message_json)} 字节，跳过此帧")
            return False

        if publish_message_safe(VIDEO_TOPIC, message_json):
            frame_count += 1
            if frame_count % 10 == 0:
                print("📹 已发送 {} 帧, 大小: {} 字节, 质量: {}%".format(
                    frame_count, frame_size, actual_quality))
            return True
        else:
            print("❌ 发送帧失败")
            return False

    except Exception as e:
        print("发送帧失败:", e)
        send_errors += 1
        return False

def check_connection_health():
    """检查连接健康状况"""
    global send_errors, connect_state, last_successful_send, consecutive_errors

    current_time = time.ticks_ms()

    if consecutive_errors >= max_consecutive_errors:
        print(f"⚠️ 连续错误过多 ({consecutive_errors})，立即触发重连")
        connect_state = CONNECT_STATE_ERROR
        return False

    if send_errors >= max_send_errors:
        print(f"⚠️ 发送错误过多 ({send_errors})，触发重连")
        connect_state = CONNECT_STATE_ERROR
        return False

    if last_successful_send > 0 and time.ticks_diff(current_time, last_successful_send) > 20000:
        print("⚠️ 20秒内无成功发送，触发重连")
        connect_state = CONNECT_STATE_ERROR
        return False

    return True

def check_and_process_messages():
    """检查并处理接收到的MQTT消息"""
    global mqtt_socket, message_buffer, received_messages, connect_state

    if not mqtt_socket or connect_state != CONNECT_STATE_NORMAL:
        return

    try:
        mqtt_socket.setblocking(False)
        try:
            chunk = mqtt_socket.recv(512)
            if chunk:
                message_buffer.extend(chunk)
        except OSError:
            pass

        while len(message_buffer) >= 2:
            packet_type = message_buffer[0] & 0xF0
            if packet_type == 0x30:
                topic, message = parse_mqtt_publish_safe(message_buffer)
                if topic and message is not None:
                    received_messages.append((topic, message))
                    print(f"📨 收到消息 - 主题: {topic}, 长度: {len(message)}字节")
                    if topic == RECOGNITION_RESULT_TOPIC:
                        set_led_state(LED_RECOGNITION)
                break
            else:
                message_buffer = message_buffer[1:]

        process_received_messages()

    except Exception as e:
        print(f"检查消息时出错: {e}")
        connect_state = CONNECT_STATE_ERROR

def parse_mqtt_publish_safe(data):
    """安全地解析MQTT PUBLISH报文"""
    try:
        if len(data) < 2:
            return None, None
        if (data[0] & 0xF0) != 0x30:
            return None, None

        multiplier = 1
        value = 0
        pos = 1

        while pos < len(data):
            encoded_byte = data[pos]
            value += (encoded_byte & 127) * multiplier
            multiplier *= 128
            pos += 1
            if (encoded_byte & 128) == 0:
                break
            if multiplier > 128 * 128 * 128:
                return None, None

        remaining_length = value
        total_length = pos + remaining_length

        if len(data) < total_length:
            return None, None

        if len(data) < pos + 2:
            return None, None
        topic_length = struct.unpack(">H", data[pos:pos+2])[0]

        if len(data) < pos + 2 + topic_length:
            return None, None

        topic = data[pos+2:pos+2+topic_length].decode('utf-8')
        message_start = pos + 2 + topic_length
        message = data[message_start:total_length]

        global message_buffer
        message_buffer = message_buffer[total_length:]

        return topic, message

    except Exception as e:
        print(f"解析MQTT报文错误: {e}")
        return None, None

def process_received_messages():
    """处理已接收的消息"""
    global received_messages, last_recognition_time

    for topic, message in received_messages:
        try:
            if isinstance(message, bytes):
                msg_str = message.decode('utf-8')
            else:
                msg_str = message

            print(f"处理消息 - 主题: {topic}, 内容: {msg_str}")

            data = ujson.loads(msg_str)

            if topic == RECOGNITION_RESULT_TOPIC:
                recognized_names = data.get("recognized_names", [])
                recognized_ids = data.get("recognized_ids", [])
                count = data.get("count", 0)

                if count > 0:
                    print("\n" + "="*40)
                    print("🎯 人脸识别结果:")

                    print("  识别到 {} 个人:".format(count))
                    for i, (name, id_val) in enumerate(zip(recognized_names, recognized_ids)):
                        print("  👤 {}: {} (ID: {})".format(i+1, name, id_val))
                    print("="*40)

                    ack_message = {
                        "status": "received",
                        "recognized_names": recognized_names,
                        "recognized_ids": recognized_ids,
                        "count": count,
                        "client_timestamp": time.ticks_ms()
                    }
                    publish_message_safe(RECOGNITION_ACK_TOPIC, ujson.dumps(ack_message))
                    print("📨 已发送确认消息")

                    last_recognition_time = time.ticks_ms()
                else:
                    print("\n❌ 未识别到任何人脸")

        except Exception as e:
            print("处理消息失败:", e)

    received_messages = []

def send_status():
    """发送状态信息"""
    global frame_count, last_recognition_time, connect_state, send_errors

    if connect_state != CONNECT_STATE_NORMAL:
        return False

    status_msg = {
        "frames_sent": frame_count,
        "memory_free": gc.mem_free(),
        "status": "streaming",
        "send_errors": send_errors,
        "client_id": CLIENT_ID,
        "resolution": "{}x{}".format(sensor.width(), sensor.height()),
        "system_state": system_state,
        "format": "grayscale"
    }

    if publish_message_safe(STATUS_TOPIC, ujson.dumps(status_msg)):
        print("📊 状态: 帧数={}, 错误={}, 内存={}字节, 系统状态={}".format(
            frame_count, send_errors, gc.mem_free(), system_state))
        return True
    else:
        print("❌ 发送状态失败")
        return False

def find_max_face(faces):
    """查找识别到的人脸区域中最大区域的函数"""
    max_size = 0
    max_face = None
    for face in faces:
        if face[2] * face[3] > max_size:
            max_face = face
            max_size = face[2] * face[3]
    return max_face

def face_tracking():
    """人脸追踪函数 - 使用PCA9685控制舵机"""
    global pan_pid, tilt_pid, face_cascade
    global last_angle_print_time, angle_print_interval, last_face_detected
    global current_pan_angle, current_tilt_angle, servo_update_count, last_servo_update_time

    if system_state != SYSTEM_STATE_FACE_ON:
        return

    try:
        img = sensor.snapshot()

        # 使用与第一段程序相同的检测参数
        faces = img.find_features(face_cascade, threshold=0.4, scale_factor=1.25)

        # 检查人脸检测状态变化
        current_face_detected = len(faces) > 0

        # 如果从无人脸状态切换到检测到人脸状态，触发绿灯闪烁
        if current_face_detected and not last_face_detected:
            trigger_face_detected_blink()

        last_face_detected = current_face_detected

        # 控制蓝色LED闪烁 - 检测到人脸时闪烁，未检测到时常亮
        if faces:
            current_time = time.ticks_ms()
            blue_led_state = (time.ticks_diff(current_time, last_led_change) // 500) % 2 == 0
            if blue_led_state:
                blue_led.on()
            else:
                blue_led.off()
            # 检测到人脸时，点亮绿灯作为确认
            green_led.on()
        else:
            # 未检测到人脸时蓝色LED常亮，绿灯关闭
            blue_led.on()
            green_led.off()

        if faces:
            max_face = find_max_face(faces)

            # 计算人脸中心点与图像中心的误差
            face_center_x = max_face[0] + max_face[2] // 2
            face_center_y = max_face[1] + max_face[3] // 2

            pan_error = face_center_x - img.width() // 2
            tilt_error = face_center_y - img.height() // 2

            # 只绘制人脸矩形
            img.draw_rectangle(max_face, color=(255, 255, 255), thickness=2)

            # 计算PID输出 - 添加死区避免微小移动
            if abs(pan_error) > 10:  # 水平死区
                pan_output = pan_pid.get_pid(pan_error, 1) / 3  # 进一步降低输出
            else:
                pan_output = 0

            if abs(tilt_error) > 10:  # 垂直死区
                tilt_output = tilt_pid.get_pid(tilt_error, 1) / 3  # 进一步降低输出
            else:
                tilt_output = 0

            # 更新舵机角度并设置
            current_pan_angle = current_pan_angle - pan_output
            current_tilt_angle = current_tilt_angle + tilt_output

            # 限制舵机角度范围 - 扩大范围
            current_pan_angle = max(-80, min(80, current_pan_angle))
            current_tilt_angle = max(-50, min(40, current_tilt_angle))  # 调整垂直范围

            # 控制舵机转动
            set_servo_angle(pan_servo_channel, current_pan_angle)
            set_servo_angle(tilt_servo_channel, current_tilt_angle)

            # 打印调试信息（每秒打印一次，避免过于频繁）
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, last_angle_print_time) > angle_print_interval:
                print("🎯 人脸追踪中 - 检测到{}个人脸, Pan: {:.1f}°, Tilt: {:.1f}°".format(
                    len(faces), current_pan_angle, current_tilt_angle))
                last_angle_print_time = current_time
                servo_update_count = 0

        else:
            # 如果没有检测到人脸，重置PID积分项以防止积分饱和
            pan_pid.reset_I()
            tilt_pid.reset_I()

    except Exception as e:
        print(f"人脸追踪错误: {e}")
        import sys
        sys.print_exception(e)

def main():
    """主函数"""
    global system_state

    print("=== OpenMV EMQX追踪系统 (集成PCA9685版本) ===")
    print(f"客户端ID: {CLIENT_ID}")
    print("🚀 系统启动 - 直接进入人脸跟踪模式")

    # 初始化硬件
    if not init_camera(CAMERA_MODE_GRAYSCALE):
        print("❌ 摄像头初始化失败，程序退出")
        return

    if not init_pca9685():
        print("⚠️ PCA9685初始化失败，继续运行")

    if not init_face_cascade():
        print("⚠️ 人脸检测初始化失败，继续运行")

    if not init_led():
        print("⚠️ LED初始化失败，继续运行")

    # 绿灯闪烁3次表示系统启动完成
    for i in range(3):
        green_led.on()
        time.sleep_ms(200)
        green_led.off()
        time.sleep_ms(200)

    # 直接设置为人脸跟踪状态
    set_led_state(LED_TRACKING)
    print("✅ 系统已启动并进入人脸跟踪模式")

    if not connect_wifi():
        print("❌ WiFi连接失败，程序退出")
        return

    if not connect_mqtt_socket():
        print("❌ MQTT连接失败，程序退出")
        return

    print("\n🚀 系统就绪! 已自动开启人脸跟踪和视频流传输")

    last_status_time = time.ticks_ms()
    last_health_check = time.ticks_ms()

    while True:
        current_time = time.ticks_ms()
        update_led()

        # 根据连接状态处理不同情况
        if connect_state == CONNECT_STATE_ERROR:
            if attempt_reconnect():
                print("✅ 重连成功，恢复运行")
            else:
                time.sleep_ms(2000)
        elif connect_state == CONNECT_STATE_RESETTING:
            if attempt_system_reset():
                print("✅ 系统重置成功")
            else:
                time.sleep_ms(2000)
        else:
            # 正常状态下的操作
            check_and_process_messages()

            # 发送视频流
            send_frame()

            # 进行人脸追踪
            face_tracking()

            # 定期发送状态和健康检查
            if time.ticks_diff(current_time, last_status_time) > 15000:
                send_status()
                gc.collect()
                last_status_time = current_time

            if time.ticks_diff(current_time, last_health_check) > 5000:
                if not check_connection_health():
                    print("⚠️ 连接健康状况不佳")
                last_health_check = current_time

        time.sleep_ms(int(1000 / TARGET_FPS))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("程序错误:", e)
        import sys
        sys.print_exception(e)
        set_led_state(LED_ERROR)
        time.sleep(5000)
        machine.reset()
    finally:
        if mqtt_socket:
            try:
                mqtt_socket.close()
                print("已关闭MQTT Socket连接")
            except:
                pass
        if 'red_led' in globals():
            red_led.off()
        if 'green_led' in globals():
            green_led.off()
        if 'blue_led' in globals():
            blue_led.off()
        print("程序结束")
