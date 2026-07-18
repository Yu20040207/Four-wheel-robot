import sensor
import time
import image
from pyb import millis
from math import pi, isnan
from pyb import LED
import struct

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
        tnow = millis()
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

# 舵机控制参数（根据您的舵机调整这些值）
SERVO_MIN = 150   # 最小角度对应值
SERVO_MAX = 450   # 最大角度对应值
SERVO_MID = 300   # 中间位置对应值

# 舵机测试函数
def servo_test():
    global pca, pan_servo_channel, tilt_servo_channel, red_led, green_led, blue_led

    print("=== 开始舵机测试 ===")

    # 红灯亮表示测试开始
    red_led.on()
    green_led.off()
    blue_led.off()

    # 测试水平舵机
    print("测试水平舵机...")
    test_angles = [-60, -30, 0, 30, 60, 0]  # 测试角度序列

    for angle in test_angles:
        print(f"水平舵机角度: {angle}°")
        set_servo_angle(pan_servo_channel, angle)

        # 绿灯闪烁表示正在移动
        green_led.on()
        time.sleep_ms(500)
        green_led.off()
        time.sleep_ms(500)

    # 测试垂直舵机
    print("测试垂直舵机...")
    test_angles = [-40, -20, 0, 20, 40, 0]  # 测试角度序列

    for angle in test_angles:
        print(f"垂直舵机角度: {angle}°")
        set_servo_angle(tilt_servo_channel, angle)

        # 蓝灯闪烁表示正在移动
        blue_led.on()
        time.sleep_ms(500)
        blue_led.off()
        time.sleep_ms(500)

    # 测试完成，所有灯闪烁3次
    for i in range(3):
        red_led.on()
        green_led.on()
        blue_led.on()
        time.sleep_ms(200)
        red_led.off()
        green_led.off()
        blue_led.off()
        time.sleep_ms(200)

    print("=== 舵机测试完成 ===")

# 初始化设置
def init_setup():
    global pca, pan_servo_channel, tilt_servo_channel, pan_pid, tilt_pid, clock, face_cascade
    global red_led, green_led, blue_led
    global current_pan_angle, current_tilt_angle

    # 初始化PCA9685舵机扩展板
    # 使用I2C2总线，P4=SCL, P5=SDA
    try:
        from pyb import I2C
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
                print("PCA9685初始化成功")
            except Exception as e:
                print(f"PCA9685通信测试失败: {e}")
                raise
        else:
            print("在地址0x40未找到PCA9685")
            print("可用地址:", [hex(addr) for addr in devices])
            raise Exception("PCA9685未找到")

    except Exception as e:
        print("PCA9685初始化失败:", e)
        # 创建模拟PCA9685对象以便调试
        class DummyPCA:
            def duty(self, channel, value):
                print(f"DummyPCA: 设置通道 {channel} 为 {value}")
                return True
        pca = DummyPCA()

    # 定义舵机通道
    pan_servo_channel = 0   # S1通道，用于水平舵机
    tilt_servo_channel = 1  # S2通道，用于垂直舵机

    # 初始化当前舵机角度
    current_pan_angle = 0
    current_tilt_angle = 0

    # 初始化RGB LED
    red_led = LED(1)    # 红色LED
    green_led = LED(2)  # 绿色LED
    blue_led = LED(3)   # 蓝色LED

    # 初始状态关闭所有LED
    red_led.off()
    green_led.off()
    blue_led.off()

    # 加载人脸识别Haar Cascade
    try:
        # 尝试加载内置的人脸检测器
        face_cascade = image.HaarCascade("/rom/haarcascade_frontalface.cascade", stages=25)
        print("HaarCascade加载成功")
    except Exception as e:
        print("加载HaarCascade失败:", e)
        try:
            # 尝试备用的人脸检测器
            face_cascade = image.HaarCascade("face", stages=25)
            print("备用人脸检测器加载成功")
        except:
            print("所有人脸检测器加载失败")
            face_cascade = None

    # PID参数 - 调整参数减少舵机移动幅度
    pan_pid = PID(p=0.18, i=0, d=0.003, imax=90)    # 水平方向PID
    tilt_pid = PID(p=0.2, i=0, d=0.006, imax=90)   # 垂直方向PID

    # 初始化时钟
    clock = time.clock()

    # 初始化摄像头
    init_camera()

    # 开机时舵机复位到中间位置
    middle()

    # 执行舵机测试
    servo_test()

    # 绿灯闪烁3次表示系统启动完成
    for i in range(3):
        green_led.on()
        time.sleep_ms(200)
        green_led.off()
        time.sleep_ms(200)

    print("系统初始化完成。开始直接人脸跟踪。")

# 设置舵机角度（使用PCA9685）
def set_servo_angle(channel, angle):
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

# 舵机回归中位
def middle():
    global current_pan_angle, current_tilt_angle, pan_servo_channel, tilt_servo_channel
    current_pan_angle = 0
    current_tilt_angle = 0
    set_servo_angle(pan_servo_channel, current_pan_angle)
    set_servo_angle(tilt_servo_channel, current_tilt_angle)
    time.sleep(1)  # 延时1秒

# 查找识别到的人脸区域中最大区域的函数
def find_max(faces):
    max_size = 0
    max_face = None
    for face in faces:
        # 人脸检测返回的是矩形 (x, y, w, h)
        if face[2] * face[3] > max_size:
            max_face = face
            max_size = face[2] * face[3]
    return max_face

# 初始化摄像头
def init_camera():
    sensor.reset()
    sensor.set_contrast(3)
    sensor.set_gainceiling(16)
    sensor.set_pixformat(sensor.GRAYSCALE)
    sensor.set_framesize(sensor.HQVGA)  # 320x240
    sensor.skip_frames(10)
    sensor.set_auto_whitebal(False)
    print("摄像头初始化: {}x{}".format(sensor.width(), sensor.height()))

# 在图像上显示状态信息 - 简化版
def draw_status(img, faces, fps):
    # 在左上角显示帧率
    status_text = "FPS: {:.1f}".format(fps)
    img.draw_string(5, 5, status_text, color=(255, 255, 255), scale=1)

    # 如果检测到人脸，显示人脸数量
    if faces:
        faces_text = "Face: {}".format(len(faces))
        img.draw_string(5, 20, faces_text, color=(0, 255, 0), scale=1)

# 主函数
def main():
    global current_pan_angle, current_tilt_angle, pan_servo_channel, tilt_servo_channel
    global pan_pid, tilt_pid, face_cascade, clock
    global red_led, green_led, blue_led, pca

    # 检查PCA9685是否初始化成功
    if pca is None:
        print("PCA9685未初始化, 无法继续")
        return

    # LED闪烁控制变量
    last_led_toggle = 0
    blue_led_state = False
    last_angle_print_time = 0  # 用于控制舵机角度打印频率
    last_debug_print = 0  # 用于控制调试信息打印频率

    # 启动后蓝灯常亮表示正在跟踪
    blue_led.on()

    while True:
        clock.tick()  # 更新FPS帧率时钟

        img = sensor.snapshot()  # 拍一张照片并返回图像

        # 检测人脸
        if face_cascade is not None:
            # 尝试不同的阈值和缩放因子
            faces = img.find_features(face_cascade, threshold=0.4, scale_factor=1.25)
        else:
            faces = []
            # 每5秒打印一次警告
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, last_debug_print) > 5000:
                print("警告: 人脸检测器未加载!")
                last_debug_print = current_time

        # 控制蓝色LED闪烁 - 检测到人脸时闪烁，未检测到时常亮
        if faces:
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, last_led_toggle) > 500:  # 500ms间隔闪烁
                blue_led_state = not blue_led_state
                if blue_led_state:
                    blue_led.on()
                else:
                    blue_led.off()
                last_led_toggle = current_time
            # 检测到人脸时，点亮绿灯作为确认
            green_led.on()
        else:
            # 未检测到人脸时蓝色LED常亮，绿灯关闭
            blue_led.on()
            blue_led_state = True
            green_led.off()

        # 在图像上显示状态信息 - 简化版
        draw_status(img, faces, clock.fps())

        # 如果检测到人脸，则进行跟踪
        if faces:
            max_face = find_max(faces)  # 找到最大的人脸区域

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
            if time.ticks_diff(current_time, last_debug_print) > 1000:  # 1秒间隔
                print("人脸: {}, 水平: {:.1f}°, 垂直: {:.1f}°, 误差: ({}, {})".format(
                    len(faces), current_pan_angle, current_tilt_angle, pan_error, tilt_error))
                last_debug_print = current_time

        else:
            # 如果没有检测到人脸，重置PID积分项以防止积分饱和
            pan_pid.reset_I()
            tilt_pid.reset_I()

# 程序入口
if __name__ == '__main__':
    try:
        init_setup()    # 执行初始化函数
        main()          # 执行主函数
    except Exception as e:
        print("错误:", e)
        # 确保程序出错时所有LED关闭
        try:
            red_led.off()
            green_led.off()
            blue_led.off()
        except:
            pass
    finally:
        try:
            middle()    # 程序结束时使云台舵机复位
        except:
            pass
        # 确保程序结束时所有LED关闭
        try:
            red_led.off()
            green_led.off()
            blue_led.off()
        except:
            pass
