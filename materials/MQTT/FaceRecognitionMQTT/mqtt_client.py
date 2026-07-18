# mqtt_client.py - MQTT客户端类
import json
import base64
from datetime import datetime
from loguru import logger
import paho.mqtt.client as mqtt
from typing import Callable, Any
import random

from config import mqtt_config
from face_recognizer import FaceRecognizer


class MQTTFaceRecognitionClient:
    """MQTT人脸识别客户端"""

    def __init__(self):
        self.client = None
        self.face_recognizer = FaceRecognizer()
        self.message_callback = None
        self.setup_mqtt_client()

    def setup_mqtt_client(self):
        """初始化MQTT客户端"""
        try:
            # 从配置中获取MQTT参数
            mqtt_config = self.config.mqtt

            # 确保端口是整数
            port = int(mqtt_config.port)

            # 创建客户端
            client_id = mqtt_config.client_id or f"face_recognizer_{random.randint(1000, 9999)}"
            self.client = mqtt.Client(client_id=client_id)

            # 设置用户名和密码（如果有）
            if mqtt_config.username:
                # 确保密码是字符串
                password = str(mqtt_config.password) if mqtt_config.password else None
                self.client.username_pw_set(str(mqtt_config.username), password)

            # 设置TLS（如果需要）
            if mqtt_config.use_tls:
                self.client.tls_set()

            # 连接MQTT服务器
            self.client.connect(mqtt_config.host, port, keepalive=60)

            # 设置回调函数
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message

            logger.success("MQTT客户端初始化完成")

        except Exception as e:
            logger.error(f"MQTT客户端初始化失败: {e}")
            raise

    def set_message_callback(self, callback: Callable[[dict], Any]):
        """设置消息回调函数"""
        self.message_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        if rc == 0:
            logger.success(f"成功连接到MQTT代理: {mqtt_config.broker}:{mqtt_config.port}")

            # 订阅主题
            client.subscribe(mqtt_config.topic_data)
            logger.info(f"已订阅主题: {mqtt_config.topic_data}")

            # 发布在线状态
            client.publish(
                mqtt_config.topic_status,
                payload="online",
                retain=True
            )
        else:
            logger.error(f"连接失败，错误代码: {rc}")

    def _on_message(self, client, userdata, msg):
        """消息接收回调"""
        try:
            logger.info(f"收到消息来自主题: {msg.topic}, 大小: {len(msg.payload)} 字节")

            # 解析JSON数据
            data = json.loads(msg.payload.decode('utf-8'))

            # 处理人脸识别请求
            if msg.topic == mqtt_config.topic_data:
                self._process_face_recognition(data)

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            self._send_error("JSON解析错误", str(e))
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            self._send_error("处理消息错误", str(e))

    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        if rc != 0:
            logger.warning("意外断开连接，正在尝试重连...")
        else:
            logger.info("正常断开连接")

    def _on_publish(self, client, userdata, mid):
        """发布消息回调"""
        logger.debug(f"消息已发布 (MID: {mid})")

    def _process_face_recognition(self, data: dict):
        """处理人脸识别请求"""
        try:
            receive_time = datetime.now()

            # 提取图像数据
            image_data_str = data.get("image_data", "")
            if not image_data_str:
                logger.error("消息中缺少图像数据")
                self._send_error("缺少图像数据", "image_data字段为空")
                return

            # 解码Base64图像数据
            try:
                if isinstance(image_data_str, str):
                    image_bytes = base64.b64decode(image_data_str)
                else:
                    image_bytes = image_data_str
            except Exception as e:
                logger.error(f"Base64解码失败: {e}")
                self._send_error("图像数据解码失败", str(e))
                return

            # 预处理图像
            image = self.face_recognizer.preprocess_image(image_bytes)
            if image is None:
                logger.error("图像预处理失败")
                self._send_error("图像处理失败", "无法解码图像")
                return

            # 进行人脸识别
            recognition_results = self.face_recognizer.detect_faces(image)

            # 构建响应消息
            response = {
                "timestamp": receive_time.isoformat(),
                "process_time": datetime.now().isoformat(),
                "device_id": data.get("device_id", "unknown"),
                "request_id": data.get("request_id", "unknown"),
                "face_count": len(recognition_results),
                "recognition_results": recognition_results,
                "status": "success",
                "image_size": len(image_bytes)
            }

            # 发布识别结果
            self.publish_result(response)

            logger.success(f"人脸识别完成: 检测到 {len(recognition_results)} 张人脸")

            # 调用自定义回调函数（如果有）
            if self.message_callback:
                self.message_callback(response)

        except Exception as e:
            logger.error(f"处理人脸识别请求失败: {e}")
            self._send_error("处理请求失败", str(e))

    def _send_error(self, error_type: str, error_message: str):
        """发送错误消息"""
        error_response = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "status": "error"
        }

        self.client.publish(
            mqtt_config.topic_error,
            payload=json.dumps(error_response),
            qos=1
        )

    def publish_result(self, result_data: dict):
        """发布识别结果"""
        try:
            self.client.publish(
                mqtt_config.topic_result,
                payload=json.dumps(result_data, ensure_ascii=False),
                qos=1,
                retain=False
            )
        except Exception as e:
            logger.error(f"发布结果失败: {e}")

    def connect(self):
        """连接到MQTT代理"""
        try:
            logger.info(f"正在连接到 {mqtt_config.broker}:{mqtt_config.port}")
            self.client.connect(
                mqtt_config.broker,
                mqtt_config.port,
                keepalive=60
            )
        except Exception as e:
            logger.error(f"连接失败: {e}")
            raise

    def start(self):
        """启动客户端"""
        try:
            self.connect()
            self.client.loop_start()
            logger.success("MQTT客户端已启动")
        except Exception as e:
            logger.error(f"启动客户端失败: {e}")
            raise

    def stop(self):
        """停止客户端"""
        logger.info("正在停止MQTT客户端...")
        self.client.publish(
            mqtt_config.topic_status,
            payload="offline",
            retain=True
        )
        self.client.loop_stop()
        self.client.disconnect()
        logger.success("MQTT客户端已停止")