# face_utils_simple.py - 简化版本，使用OpenCV的人脸检测
import cv2
import numpy as np
import os
from datetime import datetime


class SimpleFaceRecognizer:
    def __init__(self, face_database):
        self.face_database = face_database
        self.recognition_enabled = False

        # 加载OpenCV的人脸检测器
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # 存储已知人脸（简化版本，只存储图像不进行特征提取）
        self.known_faces = {}

    def load_known_faces(self):
        """加载已知人脸数据"""


        self.known_faces = {}
        faces = self.face_database.get_all_faces()

        for face in faces:
            person_name = face['name']
            image_paths = self.face_database.get_face_images(person_name)
            self.known_faces[person_name] = image_paths

        print(f"加载了 {len(self.known_faces)} 个人脸数据")

    def process_frame(self, frame_data):
        """处理视频帧进行人脸检测"""
        try:
            # 转换为numpy数组
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                return frame_data

            # 转换为灰度图进行人脸检测
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # 检测人脸
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )

            # 在检测到的人脸周围画框
            for (x, y, w, h) in faces:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, 'Face Detected', (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # 转换回JPEG
            _, jpeg_data = cv2.imencode('.jpg', frame)
            return jpeg_data.tobytes()

        except Exception as e:
            print(f"人脸检测处理失败: {e}")
            return frame_data
