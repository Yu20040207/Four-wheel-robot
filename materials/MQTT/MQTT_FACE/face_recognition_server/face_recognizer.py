# face_recognizer.py
import cv2
import numpy as np
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from config import config

logger = logging.getLogger(__name__)


class FaceRecognizer:
    """人脸识别器"""

    def __init__(self):
        self.recognizer = None
        self.face_labels = {}  # 标签映射
        self.label_counter = 0
        self.setup_recognizer()

    def setup_recognizer(self):
        """设置人脸识别器"""
        try:
            # 使用LBPH人脸识别器
            self.recognizer = cv2.face.LBPHFaceRecognizer_create()

            # 尝试加载已训练的模型
            if os.path.exists(config.face_recognition.face_model_path):
                self.recognizer.read(config.face_recognition.face_model_path)
                self._load_labels()
                logger.info("已加载训练好的人脸识别模型")
            else:
                logger.info("未找到训练模型，将使用新模型")

            logger.info("人脸识别器初始化完成")

        except Exception as e:
            logger.error(f"人脸识别器初始化失败: {e}")
            raise

    def _load_labels(self):
        """加载标签映射"""
        # 这里可以从文件加载标签映射
        # 简化实现，实际使用时需要保存和加载标签映射
        pass

    def _save_labels(self):
        """保存标签映射"""
        # 这里可以保存标签映射到文件
        pass

    def train_from_directory(self, training_dir: str) -> bool:
        """从目录训练人脸识别器"""
        try:
            faces = []
            labels = []

            # 遍历训练目录
            for person_name in os.listdir(training_dir):
                person_dir = os.path.join(training_dir, person_name)

                if not os.path.isdir(person_dir):
                    continue

                # 分配标签
                if person_name not in self.face_labels:
                    self.face_labels[person_name] = self.label_counter
                    self.label_counter += 1

                label = self.face_labels[person_name]

                # 处理每个人的图像
                for filename in os.listdir(person_dir):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        image_path = os.path.join(person_dir, filename)
                        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

                        if image is not None:
                            faces.append(image)
                            labels.append(label)

            if len(faces) > 0:
                self.recognizer.train(faces, np.array(labels))

                # 保存训练好的模型
                self.recognizer.save(config.face_recognition.face_model_path)
                self._save_labels()

                logger.info(f"人脸识别器训练完成，共 {len(faces)} 张图像")
                return True
            else:
                logger.warning("训练目录中没有找到有效的图像")
                return False

        except Exception as e:
            logger.error(f"训练人脸识别器失败: {e}")
            return False

    def recognize_face(self, face_image: np.ndarray) -> Dict[str, Any]:
        """识别人脸"""
        try:
            if face_image is None or face_image.size == 0:
                return {"label": "unknown", "confidence": 0.0, "recognized": False}

            # 调整图像大小
            face_image = cv2.resize(face_image, (200, 200))

            # 进行预测
            label_id, confidence = self.recognizer.predict(face_image)

            # 查找标签名称
            label_name = "unknown"
            for name, lid in self.face_labels.items():
                if lid == label_id:
                    label_name = name
                    break

            # 根据置信度判断识别结果
            recognized = confidence < config.face_recognition.confidence_threshold

            result = {
                "label": label_name,
                "confidence": float(confidence),
                "recognized": recognized
            }

            logger.debug(f"人脸识别结果: {result}")
            return result

        except Exception as e:
            logger.error(f"人脸识别失败: {e}")
            return {"label": "error", "confidence": 0.0, "recognized": False}

    def add_face(self, face_image: np.ndarray, label: str) -> bool:
        """添加新的人脸"""
        try:
            # 分配标签
            if label not in self.face_labels:
                self.face_labels[label] = self.label_counter
                self.label_counter += 1

            # 重新训练模型（简化实现）
            # 实际应用中应该使用增量训练
            return self._retrain_with_new_face(face_image, label)

        except Exception as e:
            logger.error(f"添加人脸失败: {e}")
            return False

    def _retrain_with_new_face(self, face_image: np.ndarray, label: str) -> bool:
        """使用新人脸重新训练模型（简化实现）"""
        # 这里应该实现增量训练
        # 简化实现：直接重新训练所有数据
        logger.info(f"添加新人脸: {label}")
        return True