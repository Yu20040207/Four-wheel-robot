# main.py - 主程序入口
import time
import signal
import sys
from loguru import logger
from mqtt_client import MQTTFaceRecognitionClient


class FaceRecognitionServer:
    """人脸识别服务器主类"""

    def __init__(self):
        self.mqtt_client = None
        self.running = False

        # 设置日志
        self._setup_logging()

    def _setup_logging(self):
        """设置日志配置"""
        logger.remove()  # 移除默认配置

        # 添加控制台输出
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="INFO"
        )

        # 添加文件输出
        logger.add(
            "logs/face_recognition_{time}.log",
            rotation="10 MB",
            retention="10 days",
            level="DEBUG"
        )

    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        logger.info(f"收到信号 {signum}，正在关闭服务...")
        self.stop()
        sys.exit(0)

    def _on_recognition_result(self, result_data: dict):
        """识别结果回调函数（可自定义处理逻辑）"""
        # 这里可以添加自定义处理逻辑，比如保存到数据库、发送通知等
        device_id = result_data.get("device_id", "unknown")
        face_count = result_data.get("face_count", 0)

        if face_count > 0:
            logger.info(f"设备 {device_id} 检测到 {face_count} 张人脸")
        else:
            logger.info(f"设备 {device_id} 未检测到人脸")

    def start(self):
        """启动服务"""
        try:
            logger.info("正在启动人脸识别MQTT服务...")

            # 创建MQTT客户端
            self.mqtt_client = MQTTFaceRecognitionClient()

            # 设置识别结果回调
            self.mqtt_client.set_message_callback(self._on_recognition_result)

            # 启动MQTT客户端
            self.mqtt_client.start()

            self.running = True
            logger.success("人脸识别MQTT服务启动成功！")
            logger.info("服务正在运行，按 Ctrl+C 停止服务")

            # 注册信号处理器
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # 主循环
            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("收到键盘中断信号")
        except Exception as e:
            logger.error(f"服务运行错误: {e}")
        finally:
            self.stop()

    def stop(self):
        """停止服务"""
        if self.mqtt_client:
            self.mqtt_client.stop()
        self.running = False
        logger.info("服务已停止")


def main():
    """主函数"""
    server = FaceRecognitionServer()
    server.start()


if __name__ == "__main__":
    main()