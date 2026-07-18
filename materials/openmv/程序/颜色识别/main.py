import sensor, time
from pyb import millis
from math import pi, isnan
from pyb import Servo


target_threshold  = (18, 74, 20, 127, -25, 127)   # 此处以红色为例


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

# ��ʼ����???
def init_setup():
    global pan_servo, tilt_servo, pan_pid, tilt_pid, sensor, clock
    pan_servo = Servo(1)                         # 实例化云台靠下的舵机
    tilt_servo = Servo(2)                        # 实例化云台靠上的舵机

    pan_servo.calibration(500,2500,1500)         # 设置舵机脉冲范围为500-2500，中心位置为1500
    tilt_servo.calibration(500,2500,1500)        # 设置舵机脉冲范围为500-2500，中心位置为1500

    #pan_pid = PID(p=0.07, i=0, imax=90)          # 脱机运行或者禁用图像传输，使用这个PID
    #tilt_pid = PID(p=0.05, i=0, imax=90)         # 脱机运行或者禁用图像传输，使用这个PID
    pan_pid = PID(p=0.10, i=0,d=0.003, imax=90)           # 在线调试使用这个PID
    tilt_pid = PID(p=0.10, i=0,d=0.006, imax=90)          # 在线调试使用这个PID

    sensor.reset()                               # 初始化感光元件
    sensor.set_pixformat(sensor.RGB565)          # 图像格式设置为彩色
    sensor.set_framesize(sensor.QQVGA)           # 图像大小设置为QQVGA，即160x120
    sensor.skip_frames(10)                       # 跳过10帧，使以上设置生效
    sensor.set_auto_whitebal(False)              # 关闭白平衡
    clock = time.clock()                         # 创建时钟对象

# 舵机回归中位
def middle():
    pan_servo.angle(0, 1000)                     # 舵机在1秒内转到0度位置
    tilt_servo.angle(0, 1000)                    # 舵机在1秒内转到0度位置
    time.sleep(1)                                # 延时1秒

# 查找识别到的目标颜色区域中最大区域的函数
def find_max(blobs):
    max_size = 0
    for blob in blobs:
        if blob[2] * blob[3] > max_size:
            max_blob = blob
            max_size = blob[2] * blob[3]
    return max_blob

# 主函数
def main():
    while 1:
        clock.tick()                             # 更新FPS帧率时钟
        img = sensor.snapshot()                  # 拍一张照片并返回图像

        blobs = img.find_blobs([target_threshold])  # 查找图像中的目标颜色
        if blobs:
            max_blob = find_max(blobs)           # 找到最大的目标颜色区域
            pan_error = max_blob.cx() - img.width() / 2
            tilt_error = max_blob.cy() - img.height() / 2

            #print("tilt_error: ", tilt_error)

            img.draw_rectangle(max_blob.rect())  # 将最大的目标颜色区域框出来
            img.draw_cross(max_blob.cx(), max_blob.cy())  # 在目标颜色区域的中心点处画十字

            pan_output = pan_pid.get_pid(pan_error, 1) / 2
            tilt_output = tilt_pid.get_pid(tilt_error, 1) / 2
            #print("tilt_output", tilt_output)
            pan_servo.angle(pan_servo.angle() - pan_output)
            tilt_servo.angle(tilt_servo.angle() + tilt_output)

            # 异常判断，定义舵机极限位置
            if pan_servo.angle() > 90:
                pan_servo.angle(90)

            if pan_servo.angle() < -90:
                pan_servo.angle(-90)
            if tilt_servo.angle() > 45:
                tilt_servo.angle(45)
            if tilt_servo.angle() < -60:
                tilt_servo.angle(-60)

# 程序入口
if __name__ == '__main__':
    init_setup()    # 执行初始化函数
    try:
        main()      # 执行主函数
    finally:
        middle()    # 程序结束时使云台舵机复位
