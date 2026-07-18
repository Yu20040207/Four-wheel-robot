# config.py - 配置文件
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class MQTTConfig:
    """MQTT配置"""
    broker: str = "127.0.0.1"  # MQTT代理地址
    port: int = 8083  # MQTT端口
    username: Optional[str] = 123  # 用户名（可选）
    password: Optional[str] = 123  # 密码（可选）
    client_id: str = "emqx_MjI5MD"  # 客户端ID

    # 主题配置
    topic_data: str = "face_recognition/data"  # 接收数据的主题
    topic_result: str = "face_recognition/result"  # 发送结果的主题
    topic_status: str = "face_recognition/status"  # 状态主题
    topic_error: str = "face_recognition/error"  # 错误主题


@dataclass
class FaceRecognitionConfig:
    """人脸识别配置"""
    # 人脸检测模型路径
    cascade_path: str = os.path.join("models", "haarcascade_frontalface_default.xml")

    # 图像处理参数
    scale_factor: float = 1.1  # 检测尺度参数
    min_neighbors: int = 5  # 最小邻居数
    min_size: tuple = (30, 30)  # 最小人脸尺寸

    # 识别参数
    confidence_threshold: float = 0.7  # 置信度阈值


@dataclass
class AppConfig:
    """应用配置"""
    log_level: str = "INFO"  # 日志级别
    save_images: bool = False  # 是否保存接收的图像（调试用）
    save_path: str = "received_images"  # 图像保存路径


# 全局配置实例
mqtt_config = MQTTConfig()
face_config = FaceRecognitionConfig()
app_config = AppConfig()