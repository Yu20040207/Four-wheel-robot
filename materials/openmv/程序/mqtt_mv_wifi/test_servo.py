# servo_test_p7p8.py
import time
from pyb import Servo

def init_servos():
    """初始化P7和P8引脚的舵机（使用Servo库）"""
    print("🔄 初始化舵机 - 使用P7和P8引脚...")

    try:
        # 创建舵机对象，1对应P7，2对应P8
        pan_servo = Servo(1)  # P7
        tilt_servo = Servo(2) # P8
        print("✅ Pan舵机: P7, Tilt舵机: P8")
    except Exception as e:
        print(f"❌ 舵机初始化失败: {e}")
        return None, None

    print("✅ 舵机初始化完成")
    return pan_servo, tilt_servo

def set_servo_angle(servo, angle):
    """设置舵机角度"""
    servo.angle(angle)
    print(f"舵机角度: {angle}°")

def test_servo_range(servo, servo_name):
    """测试单个舵机的完整范围"""
    if servo is None:
        print(f"❌ {servo_name}舵机不可用，跳过测试")
        return

    print(f"\n🔧 测试{servo_name}舵机范围...")

    # 测试序列：中间 -> 最小 -> 最大 -> 中间
    test_angles = [0, -90, 90, -45, 45, 0]

    for angle in test_angles:
        print(f"{servo_name}舵机转动到: {angle}°")
        set_servo_angle(servo, angle)
        time.sleep(2)  # 等待2秒让舵机到位

def main():
    """主测试函数"""
    print("=" * 50)
    print("🎯 P7/P8舵机测试程序（使用Servo库）")
    print("=" * 50)

    # 初始化舵机
    pan_servo, tilt_servo = init_servos()

    if pan_servo is None and tilt_servo is None:
        print("❌ 两个舵机都初始化失败，程序退出")
        return

    try:
        # 测试1: 单独测试每个舵机
        print("\n" + "="*30)
        print("测试1: 单独舵机范围测试")
        print("="*30)

        test_servo_range(pan_servo, "Pan")
        test_servo_range(tilt_servo, "Tilt")

        # 测试完成，回到中间位置
        print("\n✅ 所有测试完成，舵机回到中间位置")
        pan_servo.angle(0)
        tilt_servo.angle(0)

        print("\n🎉 舵机测试程序执行完毕！")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
    finally:
        print("\n🔚 测试程序结束")

if __name__ == "__main__":
    main()
