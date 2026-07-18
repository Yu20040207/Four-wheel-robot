# standalone_face_recognition.py - 完全独立的人脸识别MQTT服务
import time
import signal
import sys
import json
import base64
import random
import hashlib
from datetime import datetime
from loguru import logger
import paho.mqtt.client as mqtt


class StandaloneFaceRecognitionServer:
    """独立的人脸识别MQTT服务器（无外部依赖）"""

    def __init__(self, host="127.0.0.1", port=8083, username="sy_1", password="123"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.running = False
        self.start_time = None

        # 模拟的已知人脸数据库
        self.known_faces_db = {}
        self.recognition_history = []

        self._setup_logging()
        self._initialize_database()

    def _setup_logging(self):
        """设置日志"""
        logger.remove()
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO"
        )

    def _initialize_database(self):
        """初始化模拟数据库"""
        # 预定义一些已知人脸
        self.known_faces_db = {
            "emp_001": {
                "id": "emp_001",
                "name": "张三",
                "department": "技术部",
                "role": "工程师",
                "access_level": "high",
                "registration_date": "2024-01-15"
            },
            "emp_002": {
                "id": "emp_002",
                "name": "李四",
                "department": "行政部",
                "role": "经理",
                "access_level": "high",
                "registration_date": "2024-02-20"
            },
            "emp_003": {
                "id": "emp_003",
                "name": "王五",
                "department": "安保部",
                "role": "保安",
                "access_level": "medium",
                "registration_date": "2024-03-10"
            },
            "visitor_001": {
                "id": "visitor_001",
                "name": "赵六",
                "department": "访客",
                "role": "客户",
                "access_level": "low",
                "registration_date": "2024-09-26"
            }
        }
        logger.info(f"初始化数据库完成，共 {len(self.known_faces_db)} 个注册人员")

    def setup_mqtt_client(self):
        """设置MQTT客户端"""
        try:
            # 使用WebSocket
            self.client = mqtt.Client(transport='websockets')
            self.client.ws_set_options(path="/mqtt")

            # 设置认证
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            # 设置回调
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect

            logger.success("MQTT客户端初始化完成")

        except Exception as e:
            logger.error(f"MQTT客户端初始化失败: {e}")
            raise

    def _on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        if rc == 0:
            logger.success(f"✅ 成功连接到MQTT服务器 {self.host}:{self.port}")

            # 订阅主题
            topics = [
                "face_recognition/data",
                "face_recognition/control",
                "face_recognition/admin"
            ]
            for topic in topics:
                client.subscribe(topic)
                logger.info(f"已订阅主题: {topic}")

            # 发布在线状态
            client.publish("face_recognition/status", "online", retain=True)

        else:
            logger.error(f"❌ 连接失败，错误代码: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        if rc != 0:
            logger.warning("意外断开连接")

    def _on_message(self, client, userdata, msg):
        """消息处理回调"""
        try:
            logger.debug(f"收到消息来自主题: {msg.topic}")
            data = json.loads(msg.payload.decode('utf-8'))

            if msg.topic == "face_recognition/data":
                self._process_recognition_request(data)
            elif msg.topic == "face_recognition/control":
                self._process_control_command(data)
            elif msg.topic == "face_recognition/admin":
                self._process_admin_command(data)

        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            self._send_error("处理错误", str(e))

    def _process_recognition_request(self, data):
        """处理识别请求"""
        receive_time = datetime.now()
        device_id = data.get('device_id', 'unknown_device')
        request_id = data.get('request_id', f'req_{int(time.time())}')

        logger.info(f"🔍 处理识别请求 [{request_id}] 来自设备 {device_id}")

        # 分析图像数据（模拟）
        image_analysis = self._analyze_image_data(data.get('image_data', ''))

        # 进行人脸识别（模拟）
        recognition_results = self._perform_face_recognition(device_id, image_analysis)

        # 记录识别历史
        self._record_recognition_history(device_id, recognition_results)

        # 构建响应
        response = {
            "request_id": request_id,
            "timestamp": receive_time.isoformat(),
            "process_time": datetime.now().isoformat(),
            "device_id": device_id,
            "face_count": len(recognition_results),
            "recognition_results": recognition_results,
            "image_analysis": image_analysis,
            "status": "success",
            "server_info": {
                "version": "2.0-standalone",
                "model": "simulation",
                "database_size": len(self.known_faces_db)
            }
        }

        # 发送响应
        self.client.publish("face_recognition/result", json.dumps(response, ensure_ascii=False))
        logger.info(f"✅ 请求 [{request_id}] 处理完成: {len(recognition_results)} 人脸")

        # 如果需要，发送实时通知
        if len(recognition_results) > 0:
            self._send_real_time_notification(device_id, recognition_results)

    def _analyze_image_data(self, image_data):
        """分析图像数据（模拟）"""
        if not image_data:
            return {"status": "no_image", "message": "未提供图像数据"}

        try:
            # 解码Base64获取基本信息
            if isinstance(image_data, str):
                image_bytes = base64.b64decode(image_data)
            else:
                image_bytes = image_data

            # 模拟图像分析
            analysis = {
                "status": "analyzed",
                "image_size_bytes": len(image_bytes),
                "estimated_resolution": self._estimate_resolution(len(image_bytes)),
                "quality_score": round(random.uniform(0.7, 0.95), 2),
                "analysis_time_ms": random.randint(10, 50)
            }

            return analysis

        except Exception as e:
            return {"status": "error", "message": f"图像分析失败: {str(e)}"}

    def _estimate_resolution(self, image_size):
        """根据图像大小估计分辨率"""
        if image_size < 50000:
            return "320x240"
        elif image_size < 200000:
            return "640x480"
        elif image_size < 500000:
            return "1280x720"
        else:
            return "1920x1080"

    def _perform_face_recognition(self, device_id, image_analysis):
        """执行人脸识别（模拟）"""
        # 基于设备ID和图像质量生成确定性结果
        seed_str = f"{device_id}_{image_analysis.get('quality_score', 0.5)}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        random.seed(seed)

        # 根据图像质量决定识别成功率
        quality = image_analysis.get('quality_score', 0.5)
        recognition_chance = quality * 0.8  # 质量越高，识别机会越大

        # 模拟人脸检测
        face_count = 0
        if random.random() < 0.9:  # 90%的概率检测到人脸
            face_count = random.randint(0, 3)
            if quality > 0.8:
                face_count = min(face_count + 1, 4)  # 高质量图像可能检测到更多人脸

        results = []
        for i in range(face_count):
            # 决定是否识别为已知人脸
            is_known = random.random() < recognition_chance

            if is_known and self.known_faces_db:
                # 识别为已知人脸
                person_id, person_info = random.choice(list(self.known_faces_db.items()))
                confidence = round(0.7 + random.random() * 0.25, 2)  # 0.7-0.95
            else:
                # 识别为未知人脸
                person_id = f"unknown_{random.randint(1000, 9999)}"
                person_info = {
                    "name": "未知人员",
                    "department": "未知",
                    "role": "访客",
                    "access_level": "restricted"
                }
                confidence = round(0.5 + random.random() * 0.3, 2)  # 0.5-0.8

            result = {
                "face_id": f"face_{i + 1}",
                "person_id": person_id,
                "name": person_info["name"],
                "department": person_info["department"],
                "role": person_info["role"],
                "access_level": person_info["access_level"],
                "confidence": confidence,
                "bounding_box": self._generate_bounding_box(i),
                "timestamp": datetime.now().isoformat()
            }
            results.append(result)

        return results

    def _generate_bounding_box(self, index):
        """生成模拟的边界框"""
        base_x = 100 + index * 120
        base_y = 100
        width = 100
        height = 100

        return {
            "x": base_x,
            "y": base_y,
            "width": width,
            "height": height,
            "area": width * height
        }

    def _record_recognition_history(self, device_id, results):
        """记录识别历史"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "device_id": device_id,
            "faces_detected": len(results),
            "recognized_faces": [
                {
                    "person_id": r["person_id"],
                    "name": r["name"],
                    "confidence": r["confidence"]
                } for r in results
            ]
        }

        self.recognition_history.append(event)

        # 保持历史记录不超过1000条
        if len(self.recognition_history) > 1000:
            self.recognition_history = self.recognition_history[-1000:]

    def _send_real_time_notification(self, device_id, results):
        """发送实时通知"""
        notification = {
            "timestamp": datetime.now().isoformat(),
            "device_id": device_id,
            "event_type": "face_recognition",
            "recognized_count": len(results),
            "persons": [
                {
                    "id": r["person_id"],
                    "name": r["name"],
                    "role": r["role"],
                    "access_level": r["access_level"]
                } for r in results
            ],
            "security_level": self._calculate_security_level(results)
        }

        self.client.publish("face_recognition/notification", json.dumps(notification))
        logger.info(f"📢 发送实时通知: {len(results)} 人识别")

    def _calculate_security_level(self, results):
        """计算安全级别"""
        if not results:
            return "normal"

        access_levels = [r["access_level"] for r in results]

        if "restricted" in access_levels:
            return "alert"
        elif any(level == "unknown" for level in access_levels):
            return "warning"
        else:
            return "normal"

    def _process_control_command(self, data):
        """处理控制命令"""
        command = data.get("command", "")
        logger.info(f"收到控制命令: {command}")

        responses = {
            "status": self._get_status_info,
            "statistics": self._get_statistics,
            "database_info": self._get_database_info,
            "history": self._get_recent_history,
            "restart": self._restart_service
        }

        if command in responses:
            response = responses[command]()
            self.client.publish("face_recognition/control_response", json.dumps(response))
        else:
            self._send_error("未知命令", f"不支持的控制命令: {command}")

    def _get_status_info(self):
        """获取状态信息"""
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "running",
            "uptime_seconds": int(time.time() - self.start_time),
            "requests_processed": len(self.recognition_history),
            "database_size": len(self.known_faces_db),
            "version": "2.0-standalone"
        }

    def _get_statistics(self):
        """获取统计信息"""
        if not self.recognition_history:
            return {"message": "尚无识别记录"}

        total_faces = sum(event["faces_detected"] for event in self.recognition_history)

        return {
            "total_events": len(self.recognition_history),
            "total_faces_detected": total_faces,
            "average_faces_per_event": round(total_faces / len(self.recognition_history), 2),
            "last_24h_events": len([e for e in self.recognition_history
                                    if time.time() - datetime.fromisoformat(e["timestamp"]).timestamp() < 86400])
        }

    def _get_database_info(self):
        """获取数据库信息"""
        departments = {}
        for person in self.known_faces_db.values():
            dept = person["department"]
            departments[dept] = departments.get(dept, 0) + 1

        return {
            "total_persons": len(self.known_faces_db),
            "departments": departments,
            "access_levels": {
                "high": len([p for p in self.known_faces_db.values() if p["access_level"] == "high"]),
                "medium": len([p for p in self.known_faces_db.values() if p["access_level"] == "medium"]),
                "low": len([p for p in self.known_faces_db.values() if p["access_level"] == "low"])
            }
        }

    def _get_recent_history(self):
        """获取最近历史"""
        recent = self.recognition_history[-10:]  # 最近10条记录
        return {
            "recent_events": recent,
            "total_events": len(self.recognition_history)
        }

    def _restart_service(self):
        """重启服务（模拟）"""
        return {
            "message": "服务重启功能已调用",
            "timestamp": datetime.now().isoformat(),
            "action": "simulated_restart"
        }

    def _process_admin_command(self, data):
        """处理管理员命令"""
        command = data.get("action", "")

        if command == "add_person":
            self._add_person_to_database(data)
        elif command == "remove_person":
            self._remove_person_from_database(data)
        else:
            self._send_error("未知管理员命令", f"不支持的操作: {command}")

    def _add_person_to_database(self, data):
        """添加人员到数据库"""
        person_id = data.get("person_id", f"person_{int(time.time())}")

        new_person = {
            "id": person_id,
            "name": data.get("name", "新人员"),
            "department": data.get("department", "未分配"),
            "role": data.get("role", "员工"),
            "access_level": data.get("access_level", "medium"),
            "registration_date": datetime.now().strftime("%Y-%m-%d")
        }

        self.known_faces_db[person_id] = new_person

        response = {
            "action": "person_added",
            "person_id": person_id,
            "person_info": new_person,
            "database_size": len(self.known_faces_db)
        }

        self.client.publish("face_recognition/admin_response", json.dumps(response))
        logger.info(f"✅ 添加新人员: {new_person['name']} ({person_id})")

    def _remove_person_from_database(self, data):
        """从数据库移除人员"""
        person_id = data.get("person_id")

        if person_id in self.known_faces_db:
            removed_person = self.known_faces_db.pop(person_id)
            response = {
                "action": "person_removed",
                "person_id": person_id,
                "removed_person": removed_person,
                "database_size": len(self.known_faces_db)
            }
            logger.info(f"✅ 移除人员: {removed_person['name']} ({person_id})")
        else:
            response = {
                "action": "person_not_found",
                "person_id": person_id,
                "message": "指定的人员ID不存在"
            }
            logger.warning(f"⚠️ 尝试移除不存在的人员: {person_id}")

        self.client.publish("face_recognition/admin_response", json.dumps(response))

    def _send_error(self, error_type, error_message):
        """发送错误消息"""
        error_response = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "status": "error"
        }

        if self.client:
            self.client.publish("face_recognition/error", json.dumps(error_response))

    def start(self):
        """启动服务"""
        try:
            logger.info("🚀 启动独立版人脸识别MQTT服务...")
            self.start_time = time.time()

            self.setup_mqtt_client()
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()

            self.running = True
            logger.success("✅ 服务启动成功！")
            logger.info("⏹️  按 Ctrl+C 停止服务")
            logger.info("💡 支持的功能: 人脸识别模拟、人员管理、实时通知")

            # 注册信号处理
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # 主循环
            while self.running:
                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("收到键盘中断信号")
        except Exception as e:
            logger.error(f"服务运行错误: {e}")
        finally:
            self.stop()

    def _signal_handler(self, signum, frame):
        """信号处理"""
        logger.info(f"收到信号 {signum}，正在停止服务...")
        self.running = False

    def stop(self):
        """停止服务"""
        if self.client:
            logger.info("正在关闭MQTT连接...")
            self.client.publish("face_recognition/status", "offline", retain=True)
            time.sleep(0.5)
            self.client.loop_stop()
            self.client.disconnect()

        # 保存统计信息
        logger.info(f"服务运行统计: {len(self.recognition_history)} 次识别请求")
        logger.info("服务已停止")


def main():
    """主函数"""
    # 配置参数
    config = {
        "host": "127.0.0.1",
        "port": 8083,
        "username": "123",
        "password": "123"
    }

    server = StandaloneFaceRecognitionServer(**config)
    server.start()


if __name__ == "__main__":
    main()