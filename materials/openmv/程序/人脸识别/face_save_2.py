# 修复版人脸采集程序 - 参数集中设置
import sensor, image, time, machine

class SimpleFaceCapture:
    def __init__(self, person_num=1, image_count=5):
        self.red_led = machine.LED("LED_RED")
        self.blue_led = machine.LED("LED_BLUE")
        self.green_led = machine.LED("LED_GREEN")

        # 采集参数 - 通过构造函数传入
        self.person_num = person_num      # 被拍摄者编号
        self.image_count = image_count    # 每人采集图片数量
        self.capture_interval = 3000      # 采集间隔3秒

        # 状态变量
        self.capturing = False
        self.current_count = 0
        self.last_capture_time = 0

        # 初始化相机（使用稳定设置）
        self.init_camera()

    def init_camera(self):
        """初始化相机使用稳定设置"""
        print("初始化相机...")
        sensor.reset()
        sensor.set_contrast(3)
        sensor.set_gainceiling(16)
        sensor.set_pixformat(sensor.GRAYSCALE)

        # 直接使用B128X128分辨率，避免需要调整大小
        sensor.set_framesize(sensor.B128X128)  # 128x128分辨率
        sensor.set_windowing((92, 112))  # 直接设置为92x112窗口

        sensor.set_auto_gain(False)
        sensor.set_auto_whitebal(False)
        sensor.set_auto_exposure(False, exposure_us=10000)
        sensor.skip_frames(30)

        print("相机初始化完成")

    def detect_face(self, img):
        """检测人脸，返回最大的人脸区域"""
        # 使用简单的人脸检测，降低阈值提高检测率
        faces = img.find_features(image.HaarCascade("/rom/haarcascade_frontalface.cascade", stages=20),
                                threshold=0.4, scale_factor=1.1, min_size=(30, 30))

        if not faces:
            return None

        # 返回最大的人脸
        max_face = max(faces, key=lambda f: f[2] * f[3])
        return max_face

    def capture_image(self, face_region, img, count):
        """采集并保存人脸图像"""
        x, y, w, h = face_region

        # 适当扩大裁剪区域
        expand = 15
        x_start = max(0, x - expand)
        y_start = max(0, y - expand)
        x_end = min(sensor.width(), x + w + expand)
        y_end = min(sensor.height(), y + h + expand)

        # 裁剪人脸区域
        face_img = img.copy(roi=(x_start, y_start, x_end-x_start, y_end-y_start))

        # 保存图像 - 不再调整大小，因为相机已经设置为正确尺寸
        filename = "singtown/s{}/{}.pgm".format(self.person_num, count)
        try:
            face_img.save(filename)
            return True
        except Exception as e:
            print("保存失败:", e)
            return False

    def start_capture(self):
        """开始人脸采集"""
        print("开始人脸采集...")
        print("人员编号: {}, 目标数量: {}".format(self.person_num, self.image_count))

        self.capturing = True
        self.current_count = 0
        self.last_capture_time = 0

        # 启动提示
        self.green_led.on()
        time.sleep_ms(1000)
        self.green_led.off()

        while self.capturing and self.current_count < self.image_count:
            current_time = time.ticks_ms()

            # 检查是否达到采集间隔
            if time.ticks_diff(current_time, self.last_capture_time) < self.capture_interval:
                # 显示倒计时
                remaining = self.capture_interval - time.ticks_diff(current_time, self.last_capture_time)
                if remaining % 1000 < 100:  # 每秒打印一次
                    print("下次采集倒计时: {}秒".format(remaining // 1000))

                # 蓝灯闪烁表示等待中
                if (current_time // 500) % 2 == 0:
                    self.blue_led.on()
                else:
                    self.blue_led.off()

                time.sleep_ms(100)
                continue

            # 拍摄图像
            img = sensor.snapshot()

            # 检测人脸
            face = self.detect_face(img)

            if face:
                # 检测到人脸，开始采集
                print("检测到人脸，开始采集第{}张".format(self.current_count + 1))

                # 红灯亮表示准备采集
                self.red_led.on()
                time.sleep_ms(500)

                # 绿灯亮表示正在采集
                self.red_led.off()
                self.green_led.on()

                # 采集图像
                success = self.capture_image(face, img, self.image_count - self.current_count)

                if success:
                    self.current_count += 1
                    self.last_capture_time = time.ticks_ms()
                    print("成功采集第{}张图片".format(self.current_count))

                    # 成功提示
                    for i in range(2):
                        self.green_led.on()
                        time.sleep_ms(200)
                        self.green_led.off()
                        time.sleep_ms(200)
                else:
                    # 失败提示
                    for i in range(3):
                        self.red_led.on()
                        time.sleep_ms(100)
                        self.red_led.off()
                        time.sleep_ms(100)

                # 采集完成，绿灯熄灭
                self.green_led.off()

                # 显示剩余数量
                remaining = self.image_count - self.current_count
                if remaining > 0:
                    print("还需采集{}张图片".format(remaining))
            else:
                # 未检测到人脸，蓝灯慢闪
                if (current_time // 1000) % 2 == 0:
                    self.blue_led.on()
                else:
                    self.blue_led.off()

                print("未检测到人脸，等待中...")
                time.sleep_ms(500)

        # 采集完成
        self.finish_capture()

    def finish_capture(self):
        """采集完成处理"""
        print("采集完成！共采集{}张图片".format(self.current_count))

        # 完成提示
        for i in range(5):
            self.red_led.on()
            self.green_led.on()
            self.blue_led.on()
            time.sleep_ms(200)
            self.red_led.off()
            self.green_led.off()
            self.blue_led.off()
            time.sleep_ms(200)

        # 绿灯常亮3秒表示完成
        self.green_led.on()
        time.sleep_ms(3000)
        self.green_led.off()

# 主程序 - 只需要在这里修改参数
def main():
    # ========== 只需修改这里的参数 ==========
    PERSON_NUM = 1      # 被拍摄者编号
    IMAGE_COUNT = 2     # 采集图片数量
    # =====================================

    # 创建采集器实例，传入参数
    capture_system = SimpleFaceCapture(person_num=PERSON_NUM, image_count=IMAGE_COUNT)

    # 开始采集
    capture_system.start_capture()

    print("程序执行完毕")

# 运行程序
if __name__ == '__main__':
    main()
