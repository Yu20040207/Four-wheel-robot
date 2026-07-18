# utils.py
import cv2
import numpy as np
import base64
import json
import logging
from typing import Dict, Any, Optional, List  # 添加 List 导入
from datetime import datetime

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO"):
    """设置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('face_server.log', encoding='utf-8')
        ]
    )


def image_to_base64(image: np.ndarray) -> str:
    """将OpenCV图像转换为base64字符串"""
    try:
        _, buffer = cv2.imencode('.jpg', image)
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        return image_base64
    except Exception as e:
        logger.error(f"图像转换base64失败: {e}")
        return ""


def base64_to_image(image_base64: str) -> Optional[np.ndarray]:
    """将base64字符串转换为OpenCV图像"""
    try:
        image_data = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return image
    except Exception as e:
        logger.error(f"base64转换图像失败: {e}")
        return None


def create_response(success: bool, message: str = "", data: Dict[str, Any] = None) -> Dict[str, Any]:
    """创建标准响应格式"""
    response = {
        "success": success,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "data": data or {}
    }
    return response


def validate_image_data(image_data: Dict[str, Any]) -> bool:
    """验证图像数据"""
    required_fields = ["image_base64", "timestamp"]
    return all(field in image_data for field in required_fields)


def draw_detection_result(image: np.ndarray, faces: List[Dict[str, Any]]) -> np.ndarray:
    """在图像上绘制检测结果"""
    try:
        result_image = image.copy()

        for i, face in enumerate(faces):
            bbox = face.get("bbox", [])
            if len(bbox) == 4:
                x, y, w, h = bbox

                # 绘制人脸框
                cv2.rectangle(result_image, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # 绘制识别结果
                recognition = face.get("recognition", {})
                label = recognition.get("label", "unknown")
                confidence = recognition.get("confidence", 0)

                label_text = f"{label} ({confidence:.1f})"
                cv2.putText(result_image, label_text, (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        return result_image

    except Exception as e:
        logger.error(f"绘制检测结果失败: {e}")
        return image
