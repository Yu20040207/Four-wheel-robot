import sensor
import time
import image
import network
import socket
import struct
import ujson
import gc
import os  # 新增，用于读取 SD 卡配置文件
from pyb import LED, I2C
from math import pi, isnan

# ========== 从 SD 卡加载配置 ==========
def load_config():
    """尝试从 SD 卡读取配置，若失败则使用默认值"""
    config = {
        'SSID': 'MTCPC',
        'KEY': 'mt12345mt',
        'EMQX_BROKER': '192.168.13.225',
        'EMQX_PORT': 1883,
        'EMQX_USERNAME': 'sy',
        'EMQX_PASSWORD': '123'
    }

    # 常见的 SD 卡挂载点（优先使用 /sdcard，因为你的输出显示如此）
    for mount in ['/sdcard', '/sd']:
        try:
            with open(mount + '/config.ini', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        if key in config:
                            if key == 'EMQX_PORT':
                                config[key] = int(value)
                            else:
                                config[key] = value
                print(f"✅ 从 {mount}/config.ini 加载配置成功")
                return config  # 成功读取后立即返回
        except:
            continue  # 尝试下一个挂载点

    print("⚠️ 未找到有效的配置文件，使用默认配置")
    return config





# 加载配置
cfg = load_config()
SSID = cfg['SSID']
KEY = cfg['KEY']
EMQX_BROKER = cfg['EMQX_BROKER']
EMQX_PORT = cfg['EMQX_PORT']
EMQX_USERNAME = cfg['EMQX_USERNAME']
EMQX_PASSWORD = cfg['EMQX_PASSWORD']

# MQTT主题
CAMERA_CONTROL_TOPIC = "camera_control"
# 每台 OpenMV 唯一 ID，需与 ESP32 ROBOT_ID、管理后台 robot_id 一致
ROBOT_ID = "R001"
CLIENT_ID = "openmv_" + ROBOT_ID
VIDEO_TOPIC = "robots/" + ROBOT_ID + "/video/stream"
ROBOT_STATUS_TOPIC = "robots/" + ROBOT_ID + "/status/device"
STATUS_TOPIC = "openmv/status"
RECOGNITION_RESULT_TOPIC = "openmv_recognition_result"
RECOGNITION_ACK_TOPIC = "openmv/recognition_ack"
FLASK_CONTROL_TOPIC = "flask/control"
FACE_COLLECTION_TOPIC = "face_collection"
GARBAGE_TRACKING_COMMAND_TOPIC = "garbage_tracking/command"
GARBAGE_TRACKING_HEAD_TOPIC = "garbage_tracking/head"
FACE_TRACKING_HEAD_TOPIC = "face_tracking/head"
ROBOT_FACE_TRACKING_HEAD_TOPIC = "robots/" + ROBOT_ID + "/cmd/face_tracking/head"

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
SERVO_ANGLE_DEADBAND = 1.5       # 角度变化小于该值时不更新（加大防抖）
SERVO_PULSE_DEADBAND = 5         # PWM 脉宽变化小于该值时不写 I2C
SERVO_PULSE_HYSTERESIS = 2       # 额外滞回，避免脉宽在边界来回跳
SERVO_MIN_UPDATE_INTERVAL_MS = 50  # 两次舵机写入最小间隔
SERVO_MAX_STEP = 3.0             # 单次最大角度步进，限制突变
SERVO_FACE_ERROR_DEADBAND = 22   # 人脸跟踪像素死区
SERVO_FACE_STREAK_REQUIRED = 3   # 连续检测到人脸才跟踪
SERVO_ERROR_EMA_ALPHA = 0.35     # 人脸误差低通滤波系数（越小越稳）
SERVO_OUTPUT_DEADBAND = 0.35     # PID 输出死区
FACE_HEAD_COMMAND_INTERVAL_MS = 300
# Haar 检测：threshold 越高越敏感（官方示例 0.75）；scale_factor 越小越精细
FACE_DETECT_THRESHOLD = 0.72
FACE_DETECT_THRESHOLD_BOOST = 0.78
FACE_DETECT_SCALE = 1.12
FACE_HAAR_STAGES = 25
last_detected_face_count = 0
last_no_face_log_time = 0
last_face_head_command_time = 0
filtered_pan_error = 0.0
filtered_tilt_error = 0.0
servo_settled = False
last_servo_move_time = 0
SERVO_SETTLE_HOLD_MS = 400       # 到位后短时冻结，避免微抖

# 全局变量
mqtt_socket = None
frame_count = 0
system_state = SYSTEM_STATE_OFF
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
garbage_tracking_enabled = False
last_human_command_time = 0
last_garbage_command_time = 0
human_command_interval = 300  # 300ms间隔，防止指令过密
garbage_command_interval = 300
# MQTT 重连后短暂忽略 camera_control，防止 broker 残留指令误关摄像头
ignore_camera_control_until = 0
CAMERA_CONTROL_IGNORE_MS = 2500

# 舵机相关变量
pca = None
pan_servo_channel = 0
tilt_servo_channel = 1
current_pan_angle = 0
current_tilt_angle = 0
target_pan_angle = 0
target_tilt_angle = 0
last_applied_pan_pulse = None
last_applied_tilt_pulse = None
last_servo_write_time = 0
last_tracking_status_time = 0
face_detect_streak = 0
servo_outputs_enabled = True
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
        # MODE1: 退出休眠，恢复正常模式
        self._write(0x00, 0x00)
        time.sleep_ms(10)

    def freq(self, freq=None):
        if freq is None:
            return int(25000000.0 / 4096 / (self._read(0xFE) - 0.5))
        prescale = int(25000000.0 / 4096.0 / freq + 0.5)
        old_mode = self._read(0x00)
        self._write(0x00, (old_mode & 0x7F) | 0x10)  # sleep
        self._write(0xFE, prescale)
        self._write(0x00, old_mode)
        time.sleep_us(5)
        # restart + auto-increment，确保 PWM 输出使能
        self._write(0x00, old_mode | 0xA1)
        time.sleep_ms(5)

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
    """初始化摄像头（针对室内/逆光场景优化对比度与增益）"""
    try:
        sensor.reset()
        sensor.set_pixformat(sensor.GRAYSCALE)
        sensor.set_framesize(FRAME_SIZE)
        try:
            sensor.skip_frames(time=1500)
        except TypeError:
            sensor.skip_frames(30)
        sensor.set_auto_whitebal(False)
        sensor.set_auto_gain(True)
        try:
            sensor.set_gainceiling(sensor.GAINCEILING_16X)
        except Exception:
            pass
        sensor.set_auto_exposure(True)
        try:
            sensor.set_contrast(3)
        except Exception:
            pass
        try:
            sensor.set_brightness(0)
        except Exception:
            pass
        print("✅ 摄像头初始化完成: {}x{}".format(sensor.width(), sensor.height()))
        return True
    except Exception as e:
        print("❌ 摄像头初始化失败: {}".format(e))
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
            time.sleep_ms(10)
            print("✅ PCA9685初始化成功")
        else:
            print("❌ PCA9685未找到")
            class DummyPCA:
                def duty(self, channel, value):
                    return True
            pca = DummyPCA()
        try:
            face_cascade = image.HaarCascade("frontalface", stages=FACE_HAAR_STAGES)
            print("✅ 人脸检测器加载成功 (frontalface)")
        except Exception:
            try:
                face_cascade = image.HaarCascade("/rom/haarcascade_frontalface.cascade", stages=FACE_HAAR_STAGES)
                print("✅ 人脸检测器加载成功 (rom)")
            except Exception:
                print("❌ 人脸检测器加载失败")
                face_cascade = None
        pan_pid = PID(p=0.10, i=0, d=0.001, imax=40)
        tilt_pid = PID(p=0.12, i=0, d=0.0015, imax=40)
        # 上电：使能 PWM 并复位到中间位，保持持力（勿立刻卸力）
        servo_hold_outputs()
        middle(force=True)
        time.sleep_ms(500)  # 给舵机到位时间
        # 再写一次，确保上电后 PWM 稳定输出
        set_servo_angles(0, 0, force=True)
        print("✅ 舵机已使能并复位到中间位置")
        return True
    except Exception as e:
        print(f"❌ 舵机系统初始化失败: {e}")
        return False

def _angle_to_pulse(angle):
    """角度转 PCA9685 脉宽（四舍五入，减少截断抖动）"""
    pulse_width = SERVO_MIN + ((angle + 90) / 180.0) * (SERVO_MAX - SERVO_MIN)
    return int(max(SERVO_MIN, min(SERVO_MAX, round(pulse_width))))

def _should_write_pulse(channel, pulse, force=False):
    """判断是否需要写入 PWM；带滞回，避免边界来回跳"""
    if force:
        return True
    if channel == pan_servo_channel:
        last_pulse = last_applied_pan_pulse
    else:
        last_pulse = last_applied_tilt_pulse
    if last_pulse is None:
        return True
    # 离开当前脉宽需要超过 deadband+hysteresis
    return abs(pulse - last_pulse) >= (SERVO_PULSE_DEADBAND + SERVO_PULSE_HYSTERESIS)

def _clamp_step(current, target, max_step):
    """限制单次角度变化，避免突变抖动"""
    delta = target - current
    if delta > max_step:
        return current + max_step
    if delta < -max_step:
        return current - max_step
    return target

def apply_servo_pulses(pan_pulse=None, tilt_pulse=None, force=False):
    """批量写入舵机 PWM，减少 I2C 事务"""
    global last_applied_pan_pulse, last_applied_tilt_pulse, last_servo_write_time
    global servo_outputs_enabled, last_servo_move_time, servo_settled
    if pca is None or not servo_outputs_enabled:
        return False

    current_time = time.ticks_ms()
    if not force and time.ticks_diff(current_time, last_servo_write_time) < SERVO_MIN_UPDATE_INTERVAL_MS:
        return False

    updates = []
    if pan_pulse is not None and _should_write_pulse(pan_servo_channel, pan_pulse, force):
        updates.append((pan_servo_channel, pan_pulse))
    if tilt_pulse is not None and _should_write_pulse(tilt_servo_channel, tilt_pulse, force):
        updates.append((tilt_servo_channel, tilt_pulse))

    if not updates:
        return False

    wrote = False
    for channel, pulse in updates:
        for attempt in range(2):
            try:
                if pca.duty(channel, pulse) is not False:
                    if channel == pan_servo_channel:
                        last_applied_pan_pulse = pulse
                    else:
                        last_applied_tilt_pulse = pulse
                    wrote = True
                    break
            except:
                pass
            time.sleep_us(200)

    if wrote:
        last_servo_write_time = current_time
        last_servo_move_time = current_time
        servo_settled = False
    return wrote

def set_servo_angles(pan_angle=None, tilt_angle=None, force=False):
    """设置一个或两个舵机角度，带死区、限速和限频"""
    global current_pan_angle, current_tilt_angle, target_pan_angle, target_tilt_angle
    if pca is None:
        return False

    pan_pulse = None
    tilt_pulse = None
    next_pan = None
    next_tilt = None

    if pan_angle is not None:
        desired = max(-80, min(80, pan_angle))
        if not force:
            desired = _clamp_step(current_pan_angle, desired, SERVO_MAX_STEP)
        if force or abs(desired - target_pan_angle) >= SERVO_ANGLE_DEADBAND:
            next_pan = desired
            pan_pulse = _angle_to_pulse(desired)

    if tilt_angle is not None:
        desired = max(-50, min(40, tilt_angle))
        if not force:
            desired = _clamp_step(current_tilt_angle, desired, SERVO_MAX_STEP)
        if force or abs(desired - target_tilt_angle) >= SERVO_ANGLE_DEADBAND:
            next_tilt = desired
            tilt_pulse = _angle_to_pulse(desired)

    if pan_pulse is None and tilt_pulse is None:
        return False

    wrote = apply_servo_pulses(pan_pulse=pan_pulse, tilt_pulse=tilt_pulse, force=force)
    # 只有真正写出 PWM 后才更新角度，避免“软件角度漂移”导致边界抖动
    if wrote:
        if next_pan is not None:
            current_pan_angle = next_pan
            target_pan_angle = next_pan
        if next_tilt is not None:
            current_tilt_angle = next_tilt
            target_tilt_angle = next_tilt
    return wrote

def set_servo_angle(channel, angle, force=False):
    """设置单个舵机角度"""
    if channel == pan_servo_channel:
        return set_servo_angles(pan_angle=angle, force=force)
    if channel == tilt_servo_channel:
        return set_servo_angles(tilt_angle=angle, force=force)
    return False

def servo_hold_outputs():
    """重新使能舵机 PWM 输出，并恢复到当前目标角度"""
    global servo_outputs_enabled
    was_disabled = not servo_outputs_enabled
    servo_outputs_enabled = True
    if was_disabled and pca is not None:
        # 从卸力状态恢复时强制重写一次 PWM
        set_servo_angles(target_pan_angle, target_tilt_angle, force=True)

def servo_release_outputs():
    """关闭 PWM 输出，空闲时卸力，减少手碰时的抖动"""
    global servo_outputs_enabled, last_applied_pan_pulse, last_applied_tilt_pulse
    if pca is None:
        return
    try:
        pca.duty(pan_servo_channel, 0)
        pca.duty(tilt_servo_channel, 0)
    except:
        pass
    servo_outputs_enabled = False
    last_applied_pan_pulse = None
    last_applied_tilt_pulse = None

def middle(force=True):
    """舵机复位到中间位置"""
    global target_pan_angle, target_tilt_angle, face_detect_streak
    global filtered_pan_error, filtered_tilt_error, servo_settled
    target_pan_angle = 0
    target_tilt_angle = 0
    face_detect_streak = 0
    filtered_pan_error = 0.0
    filtered_tilt_error = 0.0
    servo_settled = False
    if pan_pid:
        pan_pid.reset_I()
    if tilt_pid:
        tilt_pid.reset_I()
    servo_hold_outputs()
    set_servo_angles(0, 0, force=force)

def move_forward():
    """前进"""
    new_tilt = current_tilt_angle - 5
    if new_tilt >= -50:
        servo_hold_outputs()
        set_servo_angles(tilt_angle=new_tilt, force=True)
        print("⬆️ 前进 - 俯仰角度: {}°".format(current_tilt_angle))

def move_backward():
    """后退"""
    new_tilt = current_tilt_angle + 5
    if new_tilt <= 40:
        servo_hold_outputs()
        set_servo_angles(tilt_angle=new_tilt, force=True)
        print("⬇️ 后退 - 俯仰角度: {}°".format(current_tilt_angle))

def turn_left():
    """左转"""
    new_pan = current_pan_angle + 5
    if new_pan <= 80:
        servo_hold_outputs()
        set_servo_angles(pan_angle=new_pan, force=True)
        print("⬅️ 左转 - 偏航角度: {}°".format(current_pan_angle))

def turn_right():
    """右转"""
    new_pan = current_pan_angle - 5
    if new_pan >= -80:
        servo_hold_outputs()
        set_servo_angles(pan_angle=new_pan, force=True)
        print("➡️ 右转 - 偏航角度: {}°".format(current_pan_angle))

def stop_moving():
    """停止移动"""
    print("⏹️ 停止移动")

def detect_faces_robust(img):
    """多策略人脸检测：原图 → 直方图均衡 → 伽马提亮，适配逆光/低对比度"""
    global face_cascade, last_detected_face_count, last_no_face_log_time
    if face_cascade is None:
        last_detected_face_count = 0
        return []

    faces = img.find_features(
        face_cascade,
        threshold=FACE_DETECT_THRESHOLD,
        scale_factor=FACE_DETECT_SCALE,
    )
    if faces:
        last_detected_face_count = len(faces)
        return faces

    try:
        eq = img.copy()
        eq.histeq(adaptive=True, clip_limit=3)
        faces = eq.find_features(
            face_cascade,
            threshold=FACE_DETECT_THRESHOLD_BOOST,
            scale_factor=FACE_DETECT_SCALE,
        )
        del eq
        if faces:
            last_detected_face_count = len(faces)
            return faces
    except Exception:
        pass

    try:
        boosted = img.copy()
        boosted.gamma_corr(gamma=0.65, contrast=1.5, brightness=0)
        faces = boosted.find_features(
            face_cascade,
            threshold=FACE_DETECT_THRESHOLD_BOOST,
            scale_factor=FACE_DETECT_SCALE,
        )
        del boosted
        if faces:
            last_detected_face_count = len(faces)
            return faces
    except Exception:
        pass

    last_detected_face_count = 0
    now = time.ticks_ms()
    if system_state >= SYSTEM_STATE_FACE_TRACKING:
        if last_no_face_log_time == 0 or time.ticks_diff(now, last_no_face_log_time) > 3000:
            print("⚠️ 跟踪模式未检测到人脸（可调整光线或正对摄像头）")
            last_no_face_log_time = now
    return []

def find_max(faces):
    """找到最大的人脸区域（按宽×高面积）"""
    max_size = 0
    max_face = None
    for face in faces:
        if face[2] * face[3] > max_size:
            max_face = face
            max_size = face[2] * face[3]
    return max_face

def same_face(a, b):
    return a[0] == b[0] and a[1] == b[1] and a[2] == b[2] and a[3] == b[3]

def draw_face_boxes(img, faces, track_face=None, tracking_locked=False):
    """绘制人脸框：跟踪目标高亮，其余灰色细框"""
    if not faces:
        return
    for face in faces:
        x, y, w, h = face[0], face[1], face[2], face[3]
        if track_face is not None and same_face(face, track_face):
            if tracking_locked:
                img.draw_rectangle((x, y, w, h), color=255, thickness=2)
                img.draw_cross(x + w // 2, y + h // 2, color=255, size=5)
            else:
                img.draw_rectangle((x, y, w, h), color=200, thickness=1)
        else:
            img.draw_rectangle((x, y, w, h), color=128, thickness=1)

def apply_face_servo_from_error(pan_error, tilt_error):
    """根据人脸相对画面中心的偏差驱动头部舵机（滤波 + 死区 + 限速）"""
    global last_detected_face_count, filtered_pan_error, filtered_tilt_error
    global servo_settled, last_servo_move_time

    # 误差低通，抑制检测框抖动
    a = SERVO_ERROR_EMA_ALPHA
    filtered_pan_error = (1.0 - a) * filtered_pan_error + a * float(pan_error)
    filtered_tilt_error = (1.0 - a) * filtered_tilt_error + a * float(tilt_error)

    pan_output = 0
    tilt_output = 0
    if abs(filtered_pan_error) > SERVO_FACE_ERROR_DEADBAND:
        pan_output = pan_pid.get_pid(filtered_pan_error, 1) / 2.5
        servo_settled = False
    else:
        pan_pid.reset_I()
    if abs(filtered_tilt_error) > SERVO_FACE_ERROR_DEADBAND:
        tilt_output = tilt_pid.get_pid(filtered_tilt_error, 1) / 2.5
        servo_settled = False
    else:
        tilt_pid.reset_I()

    if abs(pan_output) < SERVO_OUTPUT_DEADBAND:
        pan_output = 0
    if abs(tilt_output) < SERVO_OUTPUT_DEADBAND:
        tilt_output = 0

    last_detected_face_count = 1
    if pan_output == 0 and tilt_output == 0:
        # 进入死区后短时冻结，避免边界微抖
        now = time.ticks_ms()
        if (not servo_settled) and time.ticks_diff(now, last_servo_move_time) >= SERVO_SETTLE_HOLD_MS:
            servo_settled = True
        maybe_send_tracking_status()
        return True

    if servo_settled:
        # 已稳定时，需要更大误差才重新启动，形成滞回
        if abs(filtered_pan_error) < SERVO_FACE_ERROR_DEADBAND * 1.4 and \
           abs(filtered_tilt_error) < SERVO_FACE_ERROR_DEADBAND * 1.4:
            maybe_send_tracking_status()
            return True
        servo_settled = False

    new_pan_angle = max(-80, min(80, current_pan_angle - pan_output))
    new_tilt_angle = max(-50, min(40, current_tilt_angle + tilt_output))
    set_servo_angles(new_pan_angle, new_tilt_angle)
    maybe_send_tracking_status(force=True)
    return True

def process_face_tracking(img):
    """检测、绘制并跟踪面积最大的人脸"""
    global current_pan_angle, current_tilt_angle, face_detect_streak
    global filtered_pan_error, filtered_tilt_error
    if face_cascade is None or system_state < SYSTEM_STATE_FACE_TRACKING:
        return False
    if not servo_outputs_enabled:
        servo_hold_outputs()

    faces = detect_faces_robust(img)
    if not faces:
        face_detect_streak = 0
        filtered_pan_error = 0.0
        filtered_tilt_error = 0.0
        pan_pid.reset_I()
        tilt_pid.reset_I()
        return False

    face_detect_streak += 1
    max_face = find_max(faces)
    tracking_locked = face_detect_streak >= SERVO_FACE_STREAK_REQUIRED
    draw_face_boxes(img, faces, max_face, tracking_locked)

    if not tracking_locked:
        return False

    face_center_x = max_face[0] + max_face[2] // 2
    face_center_y = max_face[1] + max_face[3] // 2
    pan_error = face_center_x - img.width() // 2
    tilt_error = face_center_y - img.height() // 2
    return apply_face_servo_from_error(pan_error, tilt_error)

def maybe_send_tracking_status(force=False):
    """跟踪模式下定期上报舵机角度"""
    global last_tracking_status_time
    now = time.ticks_ms()
    if force or time.ticks_diff(now, last_tracking_status_time) >= 500:
        send_status()
        last_tracking_status_time = now

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
    global mqtt_socket, connect_state, ignore_camera_control_until
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
            topics = [CAMERA_CONTROL_TOPIC, RECOGNITION_RESULT_TOPIC, FACE_COLLECTION_TOPIC,
                      GARBAGE_TRACKING_COMMAND_TOPIC, GARBAGE_TRACKING_HEAD_TOPIC,
                      FACE_TRACKING_HEAD_TOPIC, ROBOT_FACE_TRACKING_HEAD_TOPIC]
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
            ignore_camera_control_until = time.ticks_add(time.ticks_ms(), CAMERA_CONTROL_IGNORE_MS)
            print("⏳ 重连后 {:.1f}s 内忽略 camera_control 残留指令".format(
                CAMERA_CONTROL_IGNORE_MS / 1000))
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
        if system_state >= SYSTEM_STATE_FACE_TRACKING:
            process_face_tracking(img)
        jpeg_data, frame_size, actual_quality = compress_frame(img)
        if frame_size > MAX_FRAME_SIZE:
            return False
        message = {
            "frame_id": frame_count,
            "robot_id": ROBOT_ID,
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

def extract_mqtt_publish(data):
    """从 MQTT PUBLISH 包提取主题与 payload"""
    try:
        if len(data) < 2 or data[0] != 0x30:
            return None, None

        remaining_length = data[1]
        expected_length = 2 + remaining_length
        if len(data) < expected_length or len(data) < 4:
            return None, None

        topic_length = (data[2] << 8) | data[3]
        if 4 + topic_length > len(data):
            return None, None

        topic = data[4:4 + topic_length].decode('utf-8')
        payload_start = 4 + topic_length
        qos = (data[0] & 0x06) >> 1
        if qos > 0:
            payload_start += 2

        payload_length = remaining_length - 2 - topic_length
        if qos > 0:
            payload_length -= 2

        if payload_start + payload_length > len(data):
            return None, None

        payload = data[payload_start:payload_start + payload_length]
        try:
            payload_str = payload.decode('utf-8')
        except:
            payload_str = payload.decode('latin-1')
        return topic, payload_str
    except Exception:
        return None, None


def extract_command_from_mqtt_packet(data):
    """从MQTT数据包中提取命令，支持字符串命令"""
    topic, command_str = extract_mqtt_publish(data)
    if topic == "camera_control":
        return command_str
    return None


def handle_garbage_head_command(payload_str):
    """处理垃圾跟踪头部俯仰指令"""
    global garbage_tracking_enabled
    if not garbage_tracking_enabled:
        return
    if "tilt_down" in payload_str:
        move_backward()
    elif "tilt_up" in payload_str:
        move_forward()
    elif "pan_left" in payload_str:
        turn_left()
    elif "pan_right" in payload_str:
        turn_right()

def handle_face_tracking_head_command(payload_str):
    """处理 Flask 转发的人脸中心坐标，驱动头部舵机（OpenMV 本地未检出时使用）"""
    global last_face_head_command_time, face_detect_streak
    if system_state < SYSTEM_STATE_FACE_TRACKING:
        return
    now = time.ticks_ms()
    if last_face_head_command_time and time.ticks_diff(now, last_face_head_command_time) < FACE_HEAD_COMMAND_INTERVAL_MS:
        return
    last_face_head_command_time = now

    try:
        data = ujson.loads(payload_str)
        cx = data.get('cx')
        cy = data.get('cy')
        fw = data.get('fw', 320)
        fh = data.get('fh', 240)
        if cx is None or cy is None:
            return
    except Exception:
        return

    if not servo_outputs_enabled:
        servo_hold_outputs()

    face_detect_streak = SERVO_FACE_STREAK_REQUIRED
    pan_error = int(cx) - int(fw) // 2
    tilt_error = int(cy) - int(fh) // 2
    apply_face_servo_from_error(pan_error, tilt_error)

def check_messages():
    """检查并处理接收到的MQTT消息"""
    global mqtt_socket, connect_state, pending_commands, last_command_time
    global last_human_command_time, last_garbage_command_time, garbage_tracking_enabled
    global ignore_camera_control_until
    if not mqtt_socket or connect_state != 0:
        return False

    try:
        mqtt_socket.setblocking(False)
        data = mqtt_socket.recv(512)
        if data:
            if len(data) >= 5 and data[0] == 0x90:
                return False
            if len(data) >= 4 and data[0] == 0x20:
                return False

            topic, payload_str = extract_mqtt_publish(data)
            if not topic:
                return False

            current_time = time.ticks_ms()

            # 垃圾跟踪底盘指令（OpenMV 本地也可转发，主要经 ESP32）
            if topic == GARBAGE_TRACKING_COMMAND_TOPIC and garbage_tracking_enabled:
                if time.ticks_diff(current_time, last_garbage_command_time) < garbage_command_interval:
                    return False
                last_garbage_command_time = current_time
                if payload_str == "forward":
                    move_forward()
                elif payload_str == "backward":
                    move_backward()
                elif payload_str == "left":
                    turn_left()
                elif payload_str == "right":
                    turn_right()
                elif payload_str == "stop":
                    stop_moving()
                return True

            if topic == GARBAGE_TRACKING_HEAD_TOPIC:
                handle_garbage_head_command(payload_str)
                return True

            if topic in (FACE_TRACKING_HEAD_TOPIC, ROBOT_FACE_TRACKING_HEAD_TOPIC):
                handle_face_tracking_head_command(payload_str)
                return True

            if topic != "camera_control":
                return False

            if time.ticks_diff(time.ticks_ms(), ignore_camera_control_until) < 0:
                print("⚠️ 忽略重连后的 camera_control 指令: {}".format(payload_str))
                return True

            command = payload_str
            if not command:
                return False

            # 处理系统控制命令（单字符）
            if len(command) == 1 and command in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "C"]:
                if last_command_time > 0:
                    time_diff = time.ticks_diff(current_time, last_command_time)
                    if time_diff < 1000:
                        return False
                last_command_time = current_time
                pending_commands.append(command)
                return True

            elif len(command) > 1 and human_tracking_enabled:
                if time.ticks_diff(current_time, last_human_command_time) < human_command_interval:
                    return False
                last_human_command_time = current_time
                if command == "forward":
                    move_forward()
                elif command == "backward":
                    move_backward()
                elif command == "left":
                    turn_left()
                elif command == "right":
                    turn_right()
                elif command == "stop":
                    stop_moving()
                return True

        return False
    except Exception as e:
        # 没有数据是可接受的异常
        if "EAGAIN" not in str(e) and "11" not in str(e):
            print(f"❌ 接收消息异常: {e}")
        return False

def process_control_command(command):
    """处理控制命令 - 修改版：避免0命令重复唤醒"""
    global system_state, human_tracking_enabled, garbage_tracking_enabled

    print(f"🔧 处理命令: '{command}'，当前状态: {system_state}")
    original_state = system_state

    if command == "0":
        # 0：OFF→开摄像头；ON→人脸跟踪（与语音唤醒/二次 0 一致）
        if system_state == SYSTEM_STATE_OFF:
            system_state = SYSTEM_STATE_ON
            print("✅ 收到指令0 - 从OFF切换到ON（开启摄像头）")
            set_led_state(SYSTEM_STATE_ON)
            ack_state = system_state
        elif system_state == SYSTEM_STATE_READY:
            system_state = SYSTEM_STATE_FACE_TRACKING
            print("✅ 收到指令0 - 从READY切换到FACE_TRACKING（追踪）")
            servo_hold_outputs()
            set_led_state(SYSTEM_STATE_FACE_TRACKING)
            ack_state = system_state
        elif system_state == SYSTEM_STATE_ON:
            system_state = SYSTEM_STATE_FACE_TRACKING
            print("✅ 收到指令0 - 从ON切换到FACE_TRACKING（追踪）")
            servo_hold_outputs()
            set_led_state(SYSTEM_STATE_FACE_TRACKING)
            ack_state = system_state
        else:
            print("⚠️ 系统已经是激活状态，忽略0命令")
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
            servo_hold_outputs()
        else:
            # 如果不是识别状态，切换到追踪
            system_state = SYSTEM_STATE_FACE_TRACKING
            print("✅ 收到指令3 - 切换到追踪状态")
            set_led_state(SYSTEM_STATE_FACE_TRACKING)
            servo_hold_outputs()
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
        middle(force=True)
        servo_release_outputs()
        set_led_state(SYSTEM_STATE_OFF)
        ack_state = system_state
    elif command == "7":
        # 新命令：舵机复位但不改变系统状态
        print("✅ 收到指令7 - 舵机复位")
        middle(force=True)
        if system_state < SYSTEM_STATE_FACE_TRACKING and not human_tracking_enabled and not garbage_tracking_enabled:
            servo_release_outputs()
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
        if system_state < SYSTEM_STATE_FACE_TRACKING and not garbage_tracking_enabled:
            servo_release_outputs()
    elif command == "B":
        print("✅ 收到指令B - 开启垃圾捡取跟踪")
        if send_control_command("B"):
            garbage_tracking_enabled = True
            servo_hold_outputs()
            if system_state == SYSTEM_STATE_OFF:
                system_state = SYSTEM_STATE_ON
                set_led_state(SYSTEM_STATE_ON)
        ack_state = 111
    elif command == "C":
        print("✅ 收到指令C - 关闭垃圾捡取跟踪（保持摄像头状态不变）")
        stop_moving()
        garbage_tracking_enabled = False
        if system_state < SYSTEM_STATE_FACE_TRACKING and not human_tracking_enabled:
            servo_release_outputs()
        if send_control_command("C"):
            pass
        ack_state = 112
        # 明确：C 仅关闭垃圾跟踪标志，绝不将 system_state 置为 OFF
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
            "robot_id": ROBOT_ID,
            "timestamp": time.ticks_ms(),
            "message": get_state_message(system_state),
            "command_received": command,
            "system_state": system_state,
            "camera_active": system_state >= SYSTEM_STATE_ON,
            "tracking_active": system_state >= SYSTEM_STATE_FACE_TRACKING,
            "recognition_active": system_state == SYSTEM_STATE_start_recognition,
            "pan_angle": current_pan_angle,
            "tilt_angle": current_tilt_angle,
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

    # 状态变化后立即上报舵机角度，便于 Web 端实时显示
    if command in ["0", "1", "2", "3", "6"]:
        send_status()

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
        "robot_id": ROBOT_ID,
        "system_state": system_state,
        "camera_active": system_state >= SYSTEM_STATE_ON,
        "tracking_active": system_state >= SYSTEM_STATE_FACE_TRACKING,
        "recognition_active": system_state == SYSTEM_STATE_start_recognition,
        "pan_angle": current_pan_angle,
        "tilt_angle": current_tilt_angle,
        "faces_detected": last_detected_face_count if system_state >= SYSTEM_STATE_FACE_TRACKING else 0,
        "human_tracking_enabled": human_tracking_enabled
    }
    publish_message_safe(STATUS_TOPIC, ujson.dumps(status_msg), qos=0)
    robot_status = {
        "robot_id": ROBOT_ID,
        "client_id": CLIENT_ID,
        "status": "online",
        "system_state": system_state,
        "camera_active": system_state >= SYSTEM_STATE_ON,
        "timestamp": time.ticks_ms(),
    }
    return publish_message_safe(ROBOT_STATUS_TOPIC, ujson.dumps(robot_status), qos=0)

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
        "robot_id": ROBOT_ID,
        "timestamp": time.ticks_ms(),
        "message": "系统就绪，等待控制指令"
    }
    publish_message_safe(STATUS_TOPIC, ujson.dumps(status_msg), qos=0)
    publish_message_safe(ROBOT_STATUS_TOPIC, ujson.dumps({
        "robot_id": ROBOT_ID,
        "client_id": CLIENT_ID,
        "status": "online",
        "timestamp": time.ticks_ms(),
    }), qos=0)

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
                    print("❌ MQTT重连失败，稍后重试（不重启设备）")
                last_reconnect_attempt = current_time

        # 视频流处理
        elif connect_state == 0:
            if system_state >= SYSTEM_STATE_ON:
                if time.ticks_diff(current_time, last_frame_time) > 50:
                    if send_video_frame():
                        frame_counter += 1
                    last_frame_time = current_time

            if system_state == SYSTEM_STATE_ON and not human_tracking_enabled and not garbage_tracking_enabled:
                # 仅开摄像头、不跟踪时空闲卸力，避免手碰舵机抖动
                if servo_outputs_enabled:
                    servo_release_outputs()

            # 定期发送状态（跟踪模式 1s，其它 10s）
            status_interval = 1000 if system_state >= SYSTEM_STATE_FACE_TRACKING else 10000
            if time.ticks_diff(current_time, last_status_time) > status_interval:
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
