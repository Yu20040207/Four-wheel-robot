# main.py
import json
import time
import logging
import cv2
from typing import Dict, Any
from config import config
from mqtt_client import MQTTClient
from face_detector import FaceDetector
from face_recognizer import FaceRecognizer
from face_database import FaceDatabase
from utils import setup_logging, base64_to_image, create_response

logger = logging.getLogger(__name__)


class FaceRecognitionServer:
    """增强的人脸识别服务器"""

    def __init__(self):
        self.mqtt_client = None
        self.face_detector = None
        self.face_recognizer = None
        self.face_database = None
        self.running = False

    def initialize(self):
        """初始化服务器"""
        try:
            setup_logging(config.server.log_level)
            logger.info("🚀 正在初始化人脸识别服务器...")

            # 初始化各个组件
            logger.info("初始化人脸检测器...")
            self.face_detector = FaceDetector()

            logger.info("初始化人脸识别器...")
            self.face_recognizer = FaceRecognizer()

            logger.info("初始化人脸数据库...")
            self.face_database = FaceDatabase()

            # 初始化MQTT客户端
            logger.info("初始化MQTT客户端...")
            self.mqtt_client = MQTTClient()
            self.mqtt_client.set_message_callback(self.handle_mqtt_message)
            self.mqtt_client.connect()

            self.running = True
            logger.info("✅ 人脸识别服务器初始化完成")

            # 发送启动通知
            self.send_startup_notification()

        except Exception as e:
            logger.error(f"❌ 服务器初始化失败: {e}")
            raise

    def send_startup_notification(self):
        """发送启动通知"""
        notification = {
            "type": "server_startup",
            "message": "人脸识别服务器已启动",
            "timestamp": time.time(),
            "status": "ready"
        }
        self.mqtt_client.publish(config.mqtt.topic_publish, notification)

    def handle_mqtt_message(self, topic: str, payload: str):
        """处理MQTT消息"""
        try:
            # 解析JSON数据
            data = json.loads(payload)
            logger.info(f"📨 收到OpenMV人脸检测数据")

            # 处理人脸数据
            self.process_face_data(data)

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}, 原始数据: {payload}")
        except Exception as e:
            logger.error(f"❌ 处理MQTT消息失败: {e}")

    def process_face_data(self, data: Dict[str, Any]):
        """处理人脸数据"""
        try:
            device_id = data.get("device_id", "unknown")
            timestamp = data.get("timestamp", 0)
            face_detected = data.get("face_detected", False)
            fps = data.get("fps", 0)

            logger.info(f"📊 设备 {device_id} - 人脸检测: {face_detected}, FPS: {fps}")

            if face_detected:
                # 提取人脸信息
                face_info = {
                    "x": data.get("face_x", 0),
                    "y": data.get("face_y", 0),
                    "width": data.get("face_width", 0),
                    "height": data.get("face_height", 0),
                    "center_x": data.get("center_x", 0),
                    "center_y": data.get("center_y", 0),
                    "pan_error": data.get("pan_error", 0),
                    "tilt_error": data.get("tilt_error", 0)
                }

                logger.info(f"👤 检测到人脸: 位置({face_info['x']}, {face_info['y']}), "
                            f"尺寸({face_info['width']}x{face_info['height']})")

                # 发送处理响应
                response = create_response(
                    success=True,
                    message="人脸数据接收并处理成功",
                    data={
                        "processed": True,
                        "timestamp": time.time(),
                        "face_info": face_info,
                        "server_time": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                )

                self.mqtt_client.publish(config.mqtt.topic_publish, response)

            else:
                logger.debug(f"设备 {device_id} 未检测到人脸")

        except Exception as e:
            logger.error(f"❌ 处理人脸数据失败: {e}")

    def process_local_image(self, image_path: str) -> Dict[str, Any]:
        """处理本地图像文件"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return create_response(False, "无法读取图像文件")

            # 检测人脸
            faces = self.face_detector.detect_faces(image)

            results = []
            for face in faces:
                # 识别人脸
                recognition_result = self.face_recognizer.recognize_face(face["roi"])

                face_result = {
                    "bbox": face["bbox"],
                    "center": face["center"],
                    "size": face["size"],
                    "recognition": recognition_result
                }
                results.append(face_result)

                # 如果是未知人脸，保存到数据库
                if (not recognition_result["recognized"] and
                        config.face_recognition.save_unknown_faces):
                    self.face_database.save_unknown_face(
                        face["roi"],
                        recognition_result["confidence"]
                    )

            # 绘制结果
            result_image = self.face_detector.draw_faces(image, faces)

            response_data = {
                "face_count": len(faces),
                "faces": results,
                "image_size": [image.shape[1], image.shape[0]]
            }

            return create_response(True, "处理完成", response_data)

        except Exception as e:
            logger.error(f"❌ 处理本地图像失败: {e}")
            return create_response(False, f"处理失败: {str(e)}")

    def add_known_face(self, image_path: str, name: str) -> Dict[str, Any]:
        """添加已知人脸"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return create_response(False, "无法读取图像文件")

            # 检测人脸
            faces = self.face_detector.detect_faces(image)

            if len(faces) == 0:
                return create_response(False, "图像中未检测到人脸")

            # 使用最大的人脸
            largest_face = max(faces, key=lambda f: f["size"])

            # 添加到数据库
            success = self.face_database.add_known_face(
                largest_face["roi"],
                name,
                {"source": image_path}
            )

            if success:
                # 重新训练识别器
                self.face_recognizer.train_from_directory(config.face_recognition.known_faces_dir)

                # 发送训练完成通知
                notification = {
                    "type": "model_updated",
                    "message": f"已添加新人脸: {name}",
                    "timestamp": time.time(),
                    "person_name": name
                }
                self.mqtt_client.publish(config.mqtt.topic_publish, notification)

                return create_response(True, f"已添加人脸: {name}")
            else:
                return create_response(False, "添加人脸失败")

        except Exception as e:
            logger.error(f"❌ 添加已知人脸失败: {e}")
            return create_response(False, f"添加失败: {str(e)}")

    def send_command_to_openmv(self, command: str, data: Dict[str, Any] = None):
        """发送命令到OpenMV"""
        try:
            message = {
                "type": "command",
                "command": command,
                "timestamp": time.time(),
                "data": data or {}
            }

            if self.mqtt_client.publish(config.mqtt.topic_publish, message):
                logger.info(f"📤 已发送命令到OpenMV: {command}")
                return True
            else:
                logger.error(f"❌ 发送命令失败: {command}")
                return False

        except Exception as e:
            logger.error(f"❌ 发送命令时发生错误: {e}")
            return False

    def run(self):
        """运行服务器"""
        try:
            self.initialize()

            logger.info("🎯 人脸识别服务器运行中，按Ctrl+C退出...")

            # 主循环
            last_status_time = time.time()
            while self.running:
                # 每30秒发送一次状态报告
                current_time = time.time()
                if current_time - last_status_time > 30:
                    self.send_status_report()
                    last_status_time = current_time

                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("⏹️ 收到中断信号，正在停止服务器...")
        except Exception as e:
            logger.error(f"❌ 服务器运行错误: {e}")
        finally:
            self.shutdown()

    def send_status_report(self):
        """发送状态报告"""
        status = {
            "type": "status_report",
            "timestamp": time.time(),
            "status": "running",
            "components": {
                "face_detector": "active",
                "face_recognizer": "active",
                "database": "active",
                "mqtt": "connected" if self.mqtt_client.is_connected() else "disconnected"
            }
        }
        self.mqtt_client.publish(config.mqtt.topic_publish, status)
        logger.info("📊 发送状态报告")

    def shutdown(self):
        """关闭服务器"""
        try:
            # 发送关闭通知
            notification = {
                "type": "server_shutdown",
                "message": "人脸识别服务器正在关闭",
                "timestamp": time.time()
            }
            self.mqtt_client.publish(config.mqtt.topic_publish, notification)

            if self.mqtt_client:
                self.mqtt_client.disconnect()

            self.running = False
            logger.info("🛑 服务器已关闭")

        except Exception as e:
            logger.error(f"❌ 关闭服务器时发生错误: {e}")


def main():
    """主函数"""
    server = FaceRecognitionServer()
    server.run()


if __name__ == "__main__":
    main()
    