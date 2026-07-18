# face_database.py
import os
import np
import cv2
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import config

logger = logging.getLogger(__name__)


class FaceDatabase:
    """人脸数据库管理"""

    def __init__(self):
        self.known_faces_dir = config.face_recognition.known_faces_dir
        self.unknown_faces_dir = config.face_recognition.unknown_faces_dir
        self.database_file = os.path.join(self.known_faces_dir, "face_database.json")
        self.face_records = {}

        self.load_database()

    def load_database(self):
        """加载数据库"""
        try:
            if os.path.exists(self.database_file):
                with open(self.database_file, 'r', encoding='utf-8') as f:
                    self.face_records = json.load(f)
                logger.info(f"已加载人脸数据库，共 {len(self.face_records)} 条记录")
            else:
                self.face_records = {}
                logger.info("创建新的人脸数据库")
        except Exception as e:
            logger.error(f"加载人脸数据库失败: {e}")
            self.face_records = {}

    def save_database(self):
        """保存数据库"""
        try:
            with open(self.database_file, 'w', encoding='utf-8') as f:
                json.dump(self.face_records, f, ensure_ascii=False, indent=2)
            logger.debug("人脸数据库已保存")
        except Exception as e:
            logger.error(f"保存人脸数据库失败: {e}")

    def add_known_face(self, face_image: np.ndarray, name: str, metadata: Dict[str, Any] = None) -> bool:
        """添加已知人脸"""
        try:
            # 创建人员目录
            person_dir = os.path.join(self.known_faces_dir, name)
            os.makedirs(person_dir, exist_ok=True)

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.jpg"
            filepath = os.path.join(person_dir, filename)

            # 保存图像
            cv2.imwrite(filepath, face_image)

            # 更新数据库记录
            if name not in self.face_records:
                self.face_records[name] = {
                    "name": name,
                    "images": [],
                    "metadata": metadata or {},
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }

            self.face_records[name]["images"].append({
                "filename": filename,
                "filepath": filepath,
                "added_at": datetime.now().isoformat()
            })
            self.face_records[name]["updated_at"] = datetime.now().isoformat()

            # 保存数据库
            self.save_database()

            logger.info(f"已添加已知人脸: {name}")
            return True

        except Exception as e:
            logger.error(f"添加已知人脸失败: {e}")
            return False

    def save_unknown_face(self, face_image: np.ndarray, confidence: float = 0.0) -> bool:
        """保存未知人脸"""
        try:
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"unknown_{timestamp}_{int(confidence)}.jpg"
            filepath = os.path.join(self.unknown_faces_dir, filename)

            # 保存图像
            cv2.imwrite(filepath, face_image)

            logger.info(f"已保存未知人脸: {filename}")
            return True

        except Exception as e:
            logger.error(f"保存未知人脸失败: {e}")
            return False

    def get_all_faces(self) -> List[Dict[str, Any]]:
        """获取所有人脸记录"""
        return list(self.face_records.values())

    def search_face(self, name: str) -> Optional[Dict[str, Any]]:
        """搜索人脸记录"""
        return self.face_records.get(name)

    def delete_face(self, name: str) -> bool:
        """删除人脸记录"""
        try:
            if name in self.face_records:
                # 删除图像文件
                person_dir = os.path.join(self.known_faces_dir, name)
                if os.path.exists(person_dir):
                    import shutil
                    shutil.rmtree(person_dir)

                # 删除记录
                del self.face_records[name]
                self.save_database()

                logger.info(f"已删除人脸记录: {name}")
                return True
            else:
                logger.warning(f"未找到人脸记录: {name}")
                return False

        except Exception as e:
            logger.error(f"删除人脸记录失败: {e}")
            return False
