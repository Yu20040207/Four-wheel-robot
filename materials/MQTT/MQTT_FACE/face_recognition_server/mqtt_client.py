# mqtt_client.py
import paho.mqtt.client as mqtt
import json
import logging
import time
from typing import Callable, Optional, Dict, Any
from config import config

logger = logging.getLogger(__name__)


class MQTTClient:
    """增强的MQTT客户端类"""

    def __init__(self):
        self.client = None
        self.message_callback = None
        self.connected = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        self.setup_client()

    def setup_client(self):
        """设置MQTT客户端"""
        try:
            self.client = mqtt.Client(client_id=config.mqtt.client_id)

            # 设置认证
            if config.mqtt.username:
                self.client.username_pw_set(
                    config.mqtt.username,
                    config.mqtt.password
                )
                logger.info(f"使用MQTT认证: 用户名={config.mqtt.username}")

            # 设置回调函数
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish
            self.client.on_subscribe = self._on_subscribe

            logger.info("MQTT客户端初始化完成")

        except Exception as e:
            logger.error(f"MQTT客户端初始化失败: {e}")
            raise

    def _on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        if rc == 0:
            self.connected = True
            self.connection_attempts = 0
            # 订阅主题
            client.subscribe(config.mqtt.topic_subscribe)
            logger.info(f"✅ MQTT连接成功，已订阅主题: {config.mqtt.topic_subscribe}")
        else:
            self.connected = False
            error_messages = {
                1: "连接被拒绝 - 不正确的协议版本",
                2: "连接被拒绝 - 无效的客户端标识符",
                3: "连接被拒绝 - 服务器不可用",
                4: "连接被拒绝 - 错误的用户名或密码",
                5: "连接被拒绝 - 未经授权"
            }
            error_msg = error_messages.get(rc, f"未知错误代码: {rc}")
            logger.error(f"❌ MQTT连接失败: {error_msg}")

    def _on_message(self, client, userdata, msg):
        """消息回调"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')

            logger.info(f"📨 收到MQTT消息 [主题: {topic}]")

            if self.message_callback:
                self.message_callback(topic, payload)

        except Exception as e:
            logger.error(f"处理MQTT消息失败: {e}")

    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        self.connected = False
        if rc != 0:
            logger.warning("MQTT意外断开连接")
            # 尝试重新连接
            self._try_reconnect()
        else:
            logger.info("MQTT正常断开连接")

    def _on_publish(self, client, userdata, mid):
        """发布消息回调"""
        logger.debug(f"消息发布成功 [消息ID: {mid}]")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """订阅主题回调"""
        logger.debug(f"主题订阅成功 [消息ID: {mid}, QoS: {granted_qos}]")

    def _try_reconnect(self):
        """尝试重新连接"""
        if self.connection_attempts < self.max_connection_attempts:
            self.connection_attempts += 1
            logger.info(f"尝试重新连接 ({self.connection_attempts}/{self.max_connection_attempts})...")
            time.sleep(5)  # 等待5秒后重试
            try:
                self.connect()
            except Exception:
                pass
        else:
            logger.error("达到最大重连次数，停止尝试")

    def connect(self):
        """连接MQTT代理"""
        try:
            logger.info(f"连接MQTT服务器: {config.mqtt.host}:{config.mqtt.port}")
            self.client.connect(
                config.mqtt.host,
                config.mqtt.port,
                keepalive=config.mqtt.keepalive
            )
            self.client.loop_start()
            logger.info("MQTT客户端已启动")

            # 等待连接建立
            for i in range(10):
                if self.connected:
                    break
                time.sleep(0.5)

            if not self.connected:
                raise Exception("MQTT连接超时")

        except Exception as e:
            logger.error(f"MQTT连接失败: {e}")
            raise

    def set_message_callback(self, callback: Callable):
        """设置消息回调函数"""
        self.message_callback = callback

    def publish(self, topic: str, payload: Dict[str, Any]):
        """发布消息"""
        try:
            if not self.connected:
                logger.warning("MQTT未连接，无法发布消息")
                return False

            payload_str = json.dumps(payload, ensure_ascii=False)
            result = self.client.publish(topic, payload_str)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"📤 消息发布成功 [主题: {topic}]")
                return True
            else:
                logger.error(f"消息发布失败 [主题: {topic}], 错误码: {result.rc}")
                return False

        except Exception as e:
            logger.error(f"发布消息失败: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT客户端已断开连接")

    def is_connected(self):
        """检查连接状态"""
        return self.connected
