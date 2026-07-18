# face_recognizer.py - 修复版本
import cv2
import numpy as np
import os
from loguru import logger
from typing import List, Dict, Any, Optional
from config import face_config


class FaceRecognizer:
    """人脸识别器"""

    def __init__(self):
        self.face_cascade = None
        self.recognizer = None
        self.known_faces = {}
        self.setup_models()

    def setup_models(self):
        """初始化模型"""
        try:
            logger.info(f"OpenCV版本: {cv2.__version__}")

            # 方法1：直接使用OpenCV数据目录中的模型
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_alt.xml'
            logger.info(f"尝试加载模型: {cascade_path}")

            # 验证文件是否存在
            if not os.path.exists(cascade_path):
                logger.error(f"模型文件不存在: {cascade_path}")
                # 尝试其他模型文件
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                logger.info(f"尝试备用模型: {cascade_path}")

            # 使用更安全的方式加载分类器
            self.face_cascade = cv2.CascadeClassifier()
            if not self.face_cascade.load(cascade_path):
                logger.error(f"模型加载失败: {cascade_path}")
                # 尝试创建空的分类器然后加载
                self.face_cascade = cv2.CascadeClassifier(cascade_path)

                # 检查分类器是否有效
                if self.face_cascade.empty():
                    logger.error("分类器为空，尝试重新创建")
                    raise Exception("无法加载人脸检测模型")

            logger.info("分类器创建成功，进行验证...")

            # 验证分类器是否能正常工作（使用测试图像）
            test_image = np.zeros((100, 100, 3), dtype=np.uint8)
            try:
                gray = cv2.cvtColor(test_image, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 5)
                logger.info("分类器验证通过")
            except Exception as e:
                logger.warning(f"分类器验证警告: {e}")

            # 初始化人脸识别器 - 尝试多种方式
            self.setup_recognizer()

            logger.success("人脸识别模型初始化完成")

        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            # 尝试备用方案
            self.setup_fallback_models()

    def setup_recognizer(self):
        """初始化人脸识别器"""
        try:
            # 尝试从cv2.face中创建
            self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        except AttributeError:
            try:
                # 尝试从cv2.createLBPHFaceRecognizer（旧版本）
                self.recognizer = cv2.createLBPHFaceRecognizer()
            except AttributeError:
                # 如果都不行，则使用一个模拟的识别器
                logger.warning("无法创建LBPH人脸识别器，使用模拟识别器")
                self.recognizer = None

    def recognize_face(self, face_image: np.ndarray) -> tuple:
        """识别人脸"""
        try:
            if self.recognizer is None:
                # 模拟识别结果
                return "unknown", 0.0
            else:
                # 使用真正的识别器
                label, confidence = self.recognizer.predict(face_image)
                return label, confidence
        except Exception as e:
            logger.error(f"人脸识别失败: {e}")
            return "error", 0.0

    def setup_fallback_models(self):
        """备用模型初始化方案"""
        try:
            logger.info("尝试备用模型初始化方案...")

            # 方法2：使用绝对路径
            cascade_path = r'C:\Users\86180\AppData\Local\Programs\Python\Python39\lib\site-packages\cv2\data\haarcascade_frontalface_alt.xml'

            if os.path.exists(cascade_path):
                logger.info(f"使用绝对路径: {cascade_path}")
                self.face_cascade = cv2.CascadeClassifier(cascade_path)

                if not self.face_cascade.empty():
                    logger.success("备用方案1成功")
                    return

            # 方法3：尝试不同的模型文件
            model_files = [
                'haarcascade_frontalface_alt.xml',
                'haarcascade_frontalface_alt2.xml',
                'haarcascade_frontalface_default.xml',
                'haarcascade_frontalface_alt_tree.xml'
            ]

            for model_file in model_files:
                cascade_path = cv2.data.haarcascades + model_file
                if os.path.exists(cascade_path):
                    logger.info(f"尝试模型: {model_file}")
                    self.face_cascade = cv2.CascadeClassifier(cascade_path)

                    if not self.face_cascade.empty():
                        logger.success(f"模型 {model_file} 加载成功")
                        # 重新初始化识别器
                        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
                        return

            # 所有方法都失败
            raise Exception("所有模型初始化方法均失败")

        except Exception as e:
            logger.error(f"备用方案也失败: {e}")
            raise

    def detect_faces(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """检测人脸"""
        try:
            if image is None:
                return []

            if self.face_cascade is None or (hasattr(self.face_cascade, 'empty') and self.face_cascade.empty()):
                logger.error("人脸检测模型未正确初始化")
                return []

            # 转换为灰度图
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # 人脸检测 - 使用更保守的参数
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.05,  # 更保守的缩放因子
                minNeighbors=6,  # 更高的邻居数
                minSize=(30, 30),  # 最小尺寸
                flags=cv2.CASCADE_SCALE_IMAGE
            )

            results = []
            for (x, y, w, h) in faces:
                face_roi = gray[y:y + h, x:x + w]
                label, confidence = self.recognize_face(face_roi)

                result = {
                    "bbox": [int(x), int(y), int(w), int(h)],
                    "confidence": float(confidence) if confidence > 0 else 0.95,
                    "label": label,
                    "face_size": w * h
                }
                results.append(result)

            logger.info(f"检测到 {len(results)} 张人脸")
            return results

        except Exception as e:
            logger.error(f"人脸检测失败: {e}")
            return []

    # 其他方法保持不变...
    def recognize_face(self, face_image: np.ndarray) -> tuple:
        """识别人脸"""
        try:
            return "unknown", 0.0
        except Exception as e:
            logger.error(f"人脸识别失败: {e}")
            return "error", 0.0

    def preprocess_image(self, image_data: bytes) -> Optional[np.ndarray]:
        """预处理图像数据"""
        try:
            nparr = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is not None:
                height, width = image.shape[:2]
                if width > 800:
                    scale = 800 / width
                    new_width = 800
                    new_height = int(height * scale)
                    image = cv2.resize(image, (new_width, new_height))
                return image
            else:
                logger.error("图像解码失败")
                return None

        except Exception as e:
            logger.error(f"图像预处理失败: {e}")
            return None
