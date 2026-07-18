# simple_software_pwm_test.py
import time
from pyb import Pin

def software_pwm_test():
    """简单的软件PWM测试"""
    print("=" * 50)
    print("🎯 简单软件PWM测试 - P4/P5引脚")
    print("=" * 50)

    # 初始化P4和P5引脚
    pan_pin = Pin("P4", Pin.OUT_PP)
    tilt_pin = Pin("P5", Pin.OUT_PP)

    print("✅ 引脚初始化完成")
    print("Pan舵机: P4")
    print("Tilt舵机: P5")

    def set_servo_pulse(pin, pulse_width_us):
        """设置舵机脉冲宽度"""
        # 生成一个完整的PWM周期 (20ms = 20000us)
        pin.high()
        time.sleep_us(pulse_width_us)
        pin.low()
        time.sleep_us(20000 - pulse_width_us)

    def set_servo_angle(pin, angle):
        """设置舵机角度"""
        # 角度范围: -90° to +90° 对应 1000us to 2000us 脉冲
        pulse_width_us = int(1500 + (angle / 90.0) * 500)
        pulse_width_us = max(1000, min(2000, pulse_width_us))
        set_servo_pulse(pin, pulse_width_us)
        return pulse_width_us

    try:
        # 测试1: 基本角度测试
        print("\n" + "="*30)
        print("测试1: 基本角度测试")
        print("="*30)

        test_angles = [0, -45, 45, -90, 90, 0]

        for angle in test_angles:
            print(f"\n设置角度: {angle}°")

            # 为了稳定性，发送多个脉冲
            for i in range(50):  # 发送50个脉冲（约1秒）
                pulse1 = set_servo_angle(pan_pin, angle)
                pulse2 = set_servo_angle(tilt_pin, angle)

            print(f"Pan脉冲: {pulse1}us")
            print(f"Tilt脉冲: {pulse2}us")

        # 测试2: 扫描测试
        print("\n" + "="*30)
        print("测试2: 扫描测试")
        print("="*30)

        print("Pan舵机扫描...")
        for angle in range(-60, 61, 15):
            print(f"Pan: {angle}°")
            for i in range(30):  # 发送30个脉冲
                set_servo_angle(pan_pin, angle)
                set_servo_angle(tilt_pin, 0)  # Tilt保持中间
            time.sleep(0.5)

        print("Tilt舵机扫描...")
        for angle in range(-30, 31, 10):
            print(f"Tilt: {angle}°")
            for i in range(30):  # 发送30个脉冲
                set_servo_angle(pan_pin, 0)  # Pan保持中间
                set_servo_angle(tilt_pin, angle)
            time.sleep(0.5)

        # 回到中间位置
        print("\n回到中间位置...")
        for i in range(50):
            set_servo_angle(pan_pin, 0)
            set_servo_angle(tilt_pin, 0)

        print("\n✅ 软件PWM测试完成!")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import sys
        sys.print_exception(e)

def manual_pwm_test():
    """手动PWM测试 - 更简单的实现"""
    print("\n" + "="*50)
    print("🔧 手动PWM测试")
    print("="*50)

    pan = Pin("P4", Pin.OUT_PP)
    tilt = Pin("P5", Pin.OUT_PP)

    print("开始手动PWM测试...")
    print("这将测试几个固定位置")

    # 测试位置: 角度 -> 脉冲宽度
    positions = [
        (0, 1500),      # 中间
        (-90, 1000),    # 最左/最下
        (90, 2000),     # 最右/最上
        (-45, 1250),    # 中间左
        (45, 1750),     # 中间右
        (0, 1500)       # 回到中间
    ]

    try:
        for angle, pulse in positions:
            print(f"\n角度: {angle}°, 脉冲: {pulse}us")

            # 发送多个脉冲确保舵机稳定
            for i in range(100):  # 发送100个脉冲（约2秒）
                # Pan舵机
                pan.high()
                tilt.high()

                # 等待脉冲宽度
                start = time.ticks_us()
                while time.ticks_diff(time.ticks_us(), start) < pulse:
                    pass

                # 设置低电平
                pan.low()
                tilt.low()

                # 等待周期剩余时间
                while time.ticks_diff(time.ticks_us(), start) < 20000:
                    pass

            print(f"位置 {angle}° 设置完成")

        print("\n✅ 手动PWM测试完成!")

    except Exception as e:
        print(f"❌ 手动PWM测试失败: {e}")

# 直接运行测试
print("开始软件PWM舵机测试...")
print("请确保舵机连接到:")
print("  - Pan舵机 -> P4引脚")
print("  - Tilt舵机 -> P5引脚")
print("  - 舵机电源 -> 外部电源")
print()

# 运行第一个测试
software_pwm_test()

# 运行第二个测试
manual_pwm_test()

print("\n🎉 所有测试完成!")
print("如果舵机没有运动，请检查:")
print("  1. 舵机电源连接")
print("  2. 信号线连接")
print("  3. 舵机是否正常工作")
