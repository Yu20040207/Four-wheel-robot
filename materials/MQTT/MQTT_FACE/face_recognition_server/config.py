# config.py
import os
from dataclasses import dataclass
from typing import Tuple


@dataclass
class MQTTConfig:
    """MQTT配置"""
    host: str = "192.168.13.225"  # 您的MQTT服务器IP
    port: int = 1883  # MQTT端口
    client_id: str = "face_server_pc"  # 客户端ID
    topic_subscribe: str = "openmv/face/detection"  # 订阅主题
    topic_publish: str = "openmv/face/command"  # 发布主题
    username: str = "sy_1"  # 用户名
    password: str = "123"  # 密码
    keepalive: int = 60  # 保持连接时间


@dataclass
class FaceRecognitionConfig:
    """人脸识别配置"""
    known_faces_dir: str = "known_faces"
    unknown_faces_dir: str = "unknown_faces"
    face_model_path: str = "models/face_model.yml"
    detection_scale: float = 1.1
    min_neighbors: int = 5
    min_size: Tuple[int, int] = (30, 30)
    confidence_threshold: float = 70
    save_unknown_faces: bool = True


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = True
    log_level: str = "INFO"


class Config:
    """总配置类"""

    def __init__(self):
        self.mqtt = MQTTConfig()
        self.face_recognition = FaceRecognitionConfig()
        self.server = ServerConfig()
        self._create_directories()

    def _create_directories(self):
        """创建必要的目录"""
        os.makedirs(self.face_recognition.known_faces_dir, exist_ok=True)
        os.makedirs(self.face_recognition.unknown_faces_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.face_recognition.face_model_path), exist_ok=True)


config = Config()
