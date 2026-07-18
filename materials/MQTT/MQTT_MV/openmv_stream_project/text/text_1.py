import cv2
import numpy as np
import requests
from threading import Thread, Lock
import time
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import socket
import re
import traceback


class OpenMVFaceDetector:
    def __init__(self):
        self.openmv_ip = "192.168.13.23"  # 直接设置目标IP
        self.port = 8080
        self.video_url = f"http://{self.openmv_ip}:{self.port}/video"
        self.running = False
        self.current_frame = None
        self.frame_lock = Lock()
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        self.cap = None
        self.connection_status = "未连接"
        self.frame_count = 0
        self.fps = 0
        self.auto_connect = True  # 自动连接标志

    def test_connection(self):
        """测试连接"""
        try:
            response = requests.get(f"http://{self.openmv_ip}:{self.port}/status", timeout=5)
            return response.status_code == 200, f"连接成功: {response.text}"
        except Exception as e:
            return False, f"连接失败: {str(e)}"

    def start_detection(self):
        """开始人脸检测"""
        self.running = True
        Thread(target=self._video_stream_worker, daemon=True).start()
        return True

    def stop_detection(self):
        """停止人脸检测"""
        self.running = False
        self.connection_status = "已断开"
        if self.cap:
            self.cap.release()
            self.cap = None

    def _video_stream_worker(self):
        """视频流工作线程"""
        reconnect_attempts = 0
        max_reconnect_attempts = 5

        while self.running and reconnect_attempts < max_reconnect_attempts:
            try:
                print(f"尝试连接到: {self.video_url}")
                self.connection_status = "连接中..."

                # 使用requests直接处理MJPEG流，避免OpenCV问题
                session = requests.Session()
                response = session.get(self.video_url, stream=True, timeout=10)

                if response.status_code != 200:
                    print(f"连接失败，状态码: {response.status_code}")
                    reconnect_attempts += 1
                    time.sleep(2)
                    continue

                print("MJPEG流连接成功")
                self.connection_status = "已连接"
                reconnect_attempts = 0

                # 解析MJPEG流
                buffer = b""
                frame_count = 0
                start_time = time.time()
                last_frame_time = time.time()

                for chunk in response.iter_content(chunk_size=8192):
                    if not self.running:
                        break

                    buffer += chunk

                    # 查找JPEG开始标记
                    start_marker = b'\xff\xd8'
                    end_marker = b'\xff\xd9'

                    while True:
                        start_pos = buffer.find(start_marker)
                        if start_pos == -1:
                            # 没有找到开始标记，保留部分数据
                            if len(buffer) > 4096:
                                buffer = buffer[-4096:]  # 保留最近的数据
                            break

                        # 查找结束标记
                        end_pos = buffer.find(end_marker, start_pos)
                        if end_pos == -1:
                            # 没有完整帧，等待更多数据
                            break

                        # 提取完整JPEG帧
                        jpeg_data = buffer[start_pos:end_pos + 2]
                        buffer = buffer[end_pos + 2:]

                        # 控制帧率，避免处理过快
                        current_time = time.time()
                        if current_time - last_frame_time < 0.1:  # 最大10fps
                            continue

                        last_frame_time = current_time

                        try:
                            # 解码JPEG
                            nparr = np.frombuffer(jpeg_data, np.uint8)
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                            if frame is not None and frame.size > 0:
                                # 进行人脸检测
                                processed_frame = self._safe_face_detection(frame)

                                with self.frame_lock:
                                    self.current_frame = processed_frame

                                frame_count += 1
                                self.frame_count = frame_count

                                # 计算FPS
                                if frame_count % 10 == 0:
                                    elapsed = time.time() - start_time
                                    self.fps = frame_count / elapsed
                                    print(f"视频流: {self.fps:.1f} FPS, 帧数: {frame_count}")

                        except Exception as e:
                            print(f"帧处理错误: {e}")
                            continue

                print("MJPEG流断开")
                self.connection_status = "连接断开"

            except Exception as e:
                print(f"视频流错误: {e}")
                self.connection_status = f"错误: {str(e)}"
                reconnect_attempts += 1
                traceback.print_exc()

            if self.running and reconnect_attempts < max_reconnect_attempts:
                print(f"等待重新连接... ({reconnect_attempts}/{max_reconnect_attempts})")
                time.sleep(2)

    def _safe_face_detection(self, frame):
        """安全的人脸检测，避免所有可能的异常"""
        try:
            # 确保图像有效
            if frame is None or frame.size == 0:
                return frame

            # 创建副本，避免修改原始数据
            result_frame = frame.copy()

            # 缩小图像以加快检测速度
            try:
                small_frame = cv2.resize(result_frame, (0, 0), fx=0.5, fy=0.5)
                gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

                # 人脸检测
                faces = self.face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(20, 20),
                    flags=cv2.CASCADE_SCALE_IMAGE
                )

                # 绘制检测结果
                for (x, y, w, h) in faces:
                    # 将坐标映射回原始尺寸
                    x, y, w, h = x * 2, y * 2, w * 2, h * 2
                    cv2.rectangle(result_frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
                    cv2.putText(result_frame, 'Face', (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

                # 添加统计信息
                cv2.putText(result_frame, f'Faces: {len(faces)}', (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(result_frame, f'FPS: {self.fps:.1f}', (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            except Exception as e:
                print(f"人脸检测内部错误: {e}")
                # 如果检测失败，至少添加FPS信息
                cv2.putText(result_frame, f'FPS: {self.fps:.1f}', (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            return result_frame

        except Exception as e:
            print(f"人脸检测整体错误: {e}")
            # 返回原始帧作为后备
            return frame

    def get_status_info(self):
        """获取状态信息"""
        with self.frame_lock:
            has_frame = self.current_frame is not None
        return f"{self.connection_status} | FPS: {self.fps:.1f} | 帧数: {self.frame_count} | 有画面: {has_frame}"


class FaceDetectionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenMV人脸检测系统")
        self.root.geometry("800x600")

        # 创建人脸检测器
        self.detector = OpenMVFaceDetector()

        # 创建GUI组件
        self.setup_gui()

        # 自动连接
        self.auto_connect()

        # 开始GUI更新循环
        self.update_gui()

    def setup_gui(self):
        """设置GUI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 标题
        title_label = ttk.Label(main_frame, text="OpenMV实时人脸检测 - 自动连接",
                                font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=10)

        # IP显示框架
        ip_frame = ttk.Frame(main_frame)
        ip_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))

        ttk.Label(ip_frame, text="目标IP:").grid(row=0, column=0, padx=5)
        ip_display = ttk.Label(ip_frame, text="192.168.13.23", font=("Arial", 10, "bold"))
        ip_display.grid(row=0, column=1, padx=5)

        # 连接控制按钮
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, columnspan=2, pady=5)

        self.connect_button = ttk.Button(control_frame, text="自动连接",
                                         command=self.auto_connect)
        self.connect_button.grid(row=0, column=0, padx=5)

        self.start_button = ttk.Button(control_frame, text="开始检测",
                                       command=self.start_detection)
        self.start_button.grid(row=0, column=1, padx=5)

        self.stop_button = ttk.Button(control_frame, text="停止检测",
                                      command=self.stop_detection, state="disabled")
        self.stop_button.grid(row=0, column=2, padx=5)

        self.snapshot_button = ttk.Button(control_frame, text="截图",
                                          command=self.take_snapshot)
        self.snapshot_button.grid(row=0, column=3, padx=5)

        # 视频显示区域
        self.video_label = ttk.Label(main_frame, text="正在自动连接 OpenMV...",
                                     background="black", foreground="white",
                                     font=("Arial", 12))
        self.video_label.grid(row=3, column=0, columnspan=2, pady=10,
                              ipadx=160, ipady=120)

        # 状态显示
        self.status_label = ttk.Label(main_frame, text="状态: 正在初始化...")
        self.status_label.grid(row=4, column=0, columnspan=2, pady=5)

        # 统计信息
        self.stats_label = ttk.Label(main_frame, text="检测到人脸: 0")
        self.stats_label.grid(row=5, column=0, columnspan=2, pady=5)

        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

    def auto_connect(self):
        """自动连接OpenMV设备"""
        self.status_label.config(text="状态: 正在自动连接到 192.168.13.23...")
        self.connect_button.config(state="disabled")

        def connect_thread():
            # 测试连接
            success, message = self.detector.test_connection()

            if success:
                self.status_label.config(text=f"状态: {message}")
                # 连接成功，自动开始检测
                self.root.after(100, self.start_detection)
            else:
                self.status_label.config(text=f"状态: {message}")
                self.connect_button.config(state="normal")
                messagebox.showerror("连接失败",
                                     f"无法连接到 OpenMV 设备 (192.168.13.23)\n\n"
                                     f"请确保:\n"
                                     f"1. OpenMV 设备已开机并运行视频流服务器\n"
                                     f"2. 设备已连接到同一网络\n"
                                     f"3. IP地址正确\n\n"
                                     f"错误详情: {message}")

        Thread(target=connect_thread, daemon=True).start()

    def start_detection(self):
        """开始人脸检测"""
        if self.detector.start_detection():
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
            self.connect_button.config(state="disabled")
            self.status_label.config(text="状态: 人脸检测运行中")
        else:
            messagebox.showerror("错误", "启动检测失败")

    def stop_detection(self):
        """停止人脸检测"""
        self.detector.stop_detection()
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.connect_button.config(state="normal")
        self.status_label.config(text="状态: 检测已停止")

    def take_snapshot(self):
        """截图功能"""
        with self.detector.frame_lock:
            if self.detector.current_frame is not None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"snapshot_{timestamp}.jpg"
                cv2.imwrite(filename, self.detector.current_frame)
                self.status_label.config(text=f"状态: 已保存截图 {filename}")
                print(f"截图已保存: {filename}")
            else:
                messagebox.showwarning("警告", "没有可用的帧进行截图")

    def update_gui(self):
        """更新GUI显示"""
        try:
            # 更新状态信息
            status_info = self.detector.get_status_info()
            self.status_label.config(text=f"状态: {status_info}")

            # 安全地更新视频帧
            with self.detector.frame_lock:
                current_frame = self.detector.current_frame

            if current_frame is not None:
                try:
                    # 转换颜色空间 BGR to RGB
                    frame_rgb = cv2.cvtColor(current_frame, cv2.COLOR_BGR2RGB)

                    # 调整图像大小以适应显示
                    h, w = frame_rgb.shape[:2]
                    # 保持原始比例，但调整到适合显示的大小
                    display_width = 400
                    display_height = 300
                    frame_resized = cv2.resize(frame_rgb, (display_width, display_height))

                    # 转换为PIL图像然后到Tkinter图像
                    pil_image = Image.fromarray(frame_resized)
                    tk_image = ImageTk.PhotoImage(pil_image)

                    # 更新标签
                    self.video_label.config(image=tk_image, text="")
                    self.video_label.image = tk_image  # 保持引用

                    # 更新统计信息 - 简化版本，避免复杂的人脸检测
                    gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
                    try:
                        faces = self.detector.face_cascade.detectMultiScale(gray, 1.1, 3, minSize=(30, 30))
                        self.stats_label.config(text=f"检测到人脸: {len(faces)}")
                    except:
                        self.stats_label.config(text="检测到人脸: 计算中...")

                except Exception as e:
                    print(f"GUI更新错误: {e}")
                    self.video_label.config(image='', text=f"画面处理错误: {str(e)}")
            else:
                # 显示等待信息
                self.video_label.config(image='', text="等待视频流...")

        except Exception as e:
            print(f"GUI更新整体错误: {e}")
            # 即使出错也继续运行

        # 每隔50ms再次调用自己
        self.root.after(50, self.update_gui)


def main():
    """主函数"""
    # 创建主窗口
    root = tk.Tk()

    # 创建GUI应用
    app = FaceDetectionGUI(root)

    # 处理窗口关闭事件
    def on_closing():
        app.detector.stop_detection()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # 启动GUI主循环
    try:
        root.mainloop()
    except Exception as e:
        print(f"GUI主循环错误: {e}")


if __name__ == "__main__":
    main()
