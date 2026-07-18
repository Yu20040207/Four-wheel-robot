# face_detector.py
import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Optional
from config import config

logger = logging.getLogger(__name__)


class FaceDetector:
    """人脸检测器"""

    def __init__(self):
        self.face_cascade = None
        self.setup_detector()

    def setup_detector(self):
        """设置人脸检测器"""
        try:
            # 加载OpenCV的人脸检测器
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )

            if self.face_cascade.empty():
                raise Exception("无法加载人脸检测模型")

            logger.info("人脸检测器初始化完成")

        except Exception as e:
            logger.error(f"人脸检测器初始化失败: {e}")
            raise

    def detect_faces(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """检测图像中的人脸"""
        try:
            if image is None:
                return []

            # 转换为灰度图
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # 人脸检测
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=config.face_recognition.detection_scale,
                minNeighbors=config.face_recognition.min_neighbors,
                minSize=config.face_recognition.min_size
            )

            results = []
            for (x, y, w, h) in faces:
                face_info = {
                    "bbox": [int(x), int(y), int(w), int(h)],
                    "center": [int(x + w / 2), int(y + h / 2)],
                    "size": w * h,
                    "roi": gray[y:y + h, x:x + w]  # 人脸区域
                }
                results.append(face_info)

            logger.debug(f"检测到 {len(results)} 张人脸")
            return results

        except Exception as e:
            logger.error(f"人脸检测失败: {e}")
            return []

    def draw_faces(self, image: np.ndarray, faces: List[Dict[str, Any]]) -> np.ndarray:
        """在图像上绘制人脸框"""
        try:
            result_image = image.copy()

            for i, face in enumerate(faces):
                x, y, w, h = face["bbox"]

                # 绘制人脸框
                cv2.rectangle(result_image, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # 绘制中心点
                cx, cy = face["center"]
                cv2.circle(result_image, (cx, cy), 3, (0, 0, 255), -1)

                # 添加标签
                cv2.putText(result_image, f"Face {i + 1}", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            return result_image

        except Exception as e:
            logger.error(f"绘制人脸框失败: {e}")
            return image
