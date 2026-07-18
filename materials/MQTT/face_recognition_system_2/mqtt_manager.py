import paho.mqtt.client as mqtt
import json
import time
import socket
from typing import Callable, Optional, List, Dict
from datetime import datetime


class MQTTManager:
    def __init__(self):
        self.client = None
        self.is_connected = False
        self.message_callback = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5

        # EMQX配置
        self.EMQX_BROKER = "192.168.13.225"
        # self.EMQX_BROKER = "localhost"
        #self.EMQX_BROKER = "192.168.123.107"


        self.EMQX_PORT = 1883
        self.EMQX_USERNAME = "sy"
        self.EMQX_PASSWORD = "123"

        # MQTT主题
        self.VIDEO_TOPIC = "openmv/video/stream"
        self.STATUS_TOPIC = "openmv/status"
        self.CONTROL_TOPIC = "camera_control"
        self.RECOGNITION_RESULT_TOPIC = "openmv_recognition_result"
        self.RECOGNITION_ACK_TOPIC = "openmv/recognition_ack"
        self.FLASK_CONTROL_TOPIC = "flask/control"
        self.FACE_COLLECTION_TOPIC = "face_collection"  # 新增：人脸采集主题
        self.COLLECTION_ACK_TOPIC = "openmv/collection_ack"  # 新增：采集确认主题
        self.FACE_COLLECTION_STATUS_TOPIC = "face_collection_status"  # 新增：人脸采集状态主题

        # 人名到编号的映射表
        self.name_to_id_map = {}
        self.id_to_name_map = {}

        # 统计信息
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0,
            'last_error': None,
            'last_connect_time': None,
            'last_disconnect_time': None,
            'recognition_results_sent': 0,
            'last_recognition_result': None,
            'face_collection_commands_sent': 0,  # 新增：人脸采集命令统计
            'face_collection_status_sent': 0  # 新增：人脸采集状态发送统计
        }

    def send_face_collection_status(self, status_code: int):
        """发送人脸采集状态"""
        try:
            if self.is_connected:
                message = {
                    "status": status_code,
                    "timestamp": time.time(),
                    "message": "采集状态更新"
                }

                if status_code == 0:
                    message["description"] = "未检测到人脸"
                elif status_code == 1:
                    message["description"] = "采集完成"
                elif status_code == -1:
                    message["description"] = "采集已取消"

                self.client.publish("openmv/collection_status", json.dumps(message))
                print(f"📤 发送采集状态: {status_code}")
                return True
        except Exception as e:
            print(f"❌ 发送采集状态失败: {e}")
        return False

    def set_message_callback(self, callback: Callable):
        """设置消息处理回调"""
        if not callable(callback):
            raise ValueError("回调函数必须是可调用的")
        self.message_callback = callback

    def update_name_mapping(self, name_to_id_dict: Dict[str, str]):
        """更新人名到编号的映射表"""
        self.name_to_id_map = name_to_id_dict
        self.id_to_name_map = {v: k for k, v in name_to_id_dict.items()}
        print(f"🔄 更新人名映射表: 共 {len(self.name_to_id_map)} 个人名")
        # 调试：打印映射内容
        for name, id_str in name_to_id_dict.items():
            print(f"   {name} -> {id_str}")

    def update_name_id_mapping(self, name_to_id_dict: Dict[str, str]):
        """更新人名到编号的映射表 (update_name_mapping 的别名)"""
        self.update_name_mapping(name_to_id_dict)

    def get_id_for_name(self, name: str) -> str:
        """获取人名对应的编号，如果没有则返回 '000'"""
        if name in self.name_to_id_map:
            return self.name_to_id_map[name]

        # 尝试从反向映射中查找
        for id_str, mapped_name in self.id_to_name_map.items():
            if mapped_name == name:
                # 发现不一致，修复映射
                self.name_to_id_map[name] = id_str
                print(f"🔄 修复映射不一致: {name} -> {id_str} (通过反向映射发现)")
                return id_str

        # 如果找不到，记录警告
        print(f"⚠️  警告: 未找到 {name} 的ID映射，使用默认值000")
        print(f"   当前映射表: {self.name_to_id_map}")
        return "000"


    def get_name_for_id(self, id_str: str) -> str:
        """获取编号对应的人名，如果没有则返回 '未知'"""
        return self.id_to_name_map.get(id_str, "未知")

    def _update_stats(self, key: str, value=None):
        """更新统计信息"""
        if value is not None:
            self.stats[key] = value
        else:
            self.stats[key] = self.stats.get(key, 0) + 1

    def _print_recognition_result(self, names: List[str], confidence_scores: Optional[List[float]] = None):
        """打印识别结果到控制台"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("\n" + "=" * 60)
        print(f"🎯 人脸识别结果 - {timestamp}")
        print("=" * 60)

        if names:
            print(f"✅ 识别到 {len(names)} 个人:")
            for i, name in enumerate(names):
                # 优先使用映射表中的ID，如果没有则使用默认值
                if name in self.name_to_id_map:
                    person_id = self.name_to_id_map[name]
                else:
                    # 尝试从反向映射中查找
                    person_id = "000"  # 默认值
                    # 检查是否有任何映射值匹配这个姓名
                    for id_str, mapped_name in self.id_to_name_map.items():
                        if mapped_name == name:
                            person_id = id_str
                            break

                confidence_text = ""
                if confidence_scores and i < len(confidence_scores):
                    confidence_text = f" (置信度: {confidence_scores[i]:.2f})"
                print(f"   👤 {i + 1}. {name} [{person_id}]{confidence_text}")

                # 如果发现使用的是默认值000，记录警告
                if person_id == "000":
                    print(f"⚠️  警告: {name} 的ID映射缺失，使用默认值000")
                    print(f"   当前映射表: {self.name_to_id_map}")

            self.stats['last_recognition_result'] = {
                'timestamp': timestamp,
                'names': names,
                'ids': [self.get_id_for_name(name) for name in names],
                'confidence_scores': confidence_scores,
                'count': len(names)
            }
        else:
            print("❌ 未识别到任何人脸")

        print("=" * 60 + "\n")


    def _check_network_connectivity(self) -> bool:
        """检查网络连通性"""
        try:
            socket.create_connection((self.EMQX_BROKER, self.EMQX_PORT), timeout=5)
            return True
        except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError) as e:
            print(f"⚠️ 网络连通性检查失败: {e}")
            return False

    def connect(self) -> bool:
        """连接EMQX服务器"""
        try:
            if not self._check_network_connectivity():
                print("❌ 无法连接到EMQX服务器，请检查网络连接")
                return False

            self.client = mqtt.Client()
            self.client.username_pw_set(self.EMQX_USERNAME, self.EMQX_PASSWORD)

            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect
            self.client.on_publish = self.on_publish
            self.client.on_subscribe = self.on_subscribe

            self.client.reconnect_delay_set(min_delay=1, max_delay=30)
            self.client.max_queued_messages_set(100)

            self.client.connect(self.EMQX_BROKER, self.EMQX_PORT, keepalive=60)
            self.client.loop_start()

            for i in range(10):
                if self.is_connected:
                    break
                time.sleep(0.5)

            if not self.is_connected:
                print("❌ 连接超时，无法建立MQTT连接")
                self._cleanup()
                return False

            self._update_stats('last_connect_time', time.time())
            self.reconnect_attempts = 0
            return True

        except Exception as e:
            print(f"❌ 连接失败: {e}")
            self._update_stats('errors')
            self._update_stats('last_error', f"连接失败: {e}")
            self._cleanup()
            return False

    def _cleanup(self):
        """清理资源"""
        try:
            if self.client:
                self.client.loop_stop()
                self.client.disconnect()
                self.client = None
            self.is_connected = False
        except Exception as e:
            print(f"⚠️ 清理资源时出现警告: {e}")

    def on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        try:
            if rc == 0:
                self.is_connected = True

                subscriptions = [
                    (self.VIDEO_TOPIC, 0),
                    (self.STATUS_TOPIC, 0),
                    (self.RECOGNITION_ACK_TOPIC, 0),
                    (self.FLASK_CONTROL_TOPIC, 0),
                    (self.FACE_COLLECTION_TOPIC, 0)  # 新增：订阅人脸采集主题
                ]

                for topic, qos in subscriptions:
                    try:
                        result = client.subscribe(topic, qos)
                        if result[0] != mqtt.MQTT_ERR_SUCCESS:
                            print(f"❌ 订阅主题失败 {topic}: 错误码 {result[0]}")
                        else:
                            print(f"✅ 成功订阅主题: {topic}")
                    except Exception as e:
                        print(f"❌ 订阅主题异常 {topic}: {e}")

            else:
                error_messages = {
                    1: "连接被拒绝 - 不正确的协议版本",
                    2: "连接被拒绝 - 无效的客户端标识符",
                    3: "连接被拒绝 - 服务器不可用",
                    4: "连接被拒绝 - 错误的用户名或密码",
                    5: "连接被拒绝 - 未经授权"
                }
                error_msg = error_messages.get(rc, f"连接失败，错误代码: {rc}")
                print(f"❌ {error_msg}")
                self._update_stats('errors')
                self._update_stats('last_error', error_msg)
                self.is_connected = False

        except Exception as e:
            print(f"❌ 连接回调处理异常: {e}")
            self._update_stats('errors')
            self._update_stats('last_error', f"连接回调异常: {e}")
            self.is_connected = False

    def update_name_id_mapping(self, name_to_id_dict: Dict[str, str]):
        """更新人名到编号的映射表 (update_name_mapping 的别名)"""
        self.update_name_mapping(name_to_id_dict)

    def on_message(self, client, userdata, msg):
        """消息接收回调"""
        try:
            self._update_stats('messages_received')

            topic = msg.topic
            payload = msg.payload.decode('utf-8')

            #print(f"📥 MQTT收到消息 - 主题: {topic}, 长度: {len(payload)}")

            message_data = {
                'topic': topic,
                'payload': None
            }

            # 处理所有主题的消息
            try:
                data = json.loads(payload)
                message_data['payload'] = data

                # 调用回调函数处理消息
                if self.message_callback:
                    self.message_callback(message_data)
                else:
                    print(f"⚠️ 收到消息但没有设置回调函数: {topic}")

            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}, payload: {payload[:100]}...")
                self._update_stats('errors')
                self._update_stats('last_error', f"JSON解析失败: {e}")

        except Exception as e:
            print(f"❌ 消息处理异常: {e}")
            self._update_stats('errors')
            self._update_stats('last_error', f"消息处理异常: {e}")

    def on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        self.is_connected = False
        self._update_stats('last_disconnect_time', time.time())

        if rc != 0:
            print(f"⚠️ MQTT连接意外断开，返回码: {rc}")
            self._update_stats('errors')
            self._update_stats('last_error', f"意外断开: {rc}")
            self._attempt_reconnect()

    def on_publish(self, client, userdata, mid):
        """发布消息回调"""
        pass

    def on_subscribe(self, client, userdata, mid, granted_qos):
        """订阅回调"""
        pass

    def _attempt_reconnect(self):
        """尝试重新连接"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            print(f"❌ 已达到最大重连次数 ({self.max_reconnect_attempts})，停止重连")
            return

        self.reconnect_attempts += 1
        delay = self.reconnect_delay * self.reconnect_attempts

        print(f"🔄 尝试重新连接 ({self.reconnect_attempts}/{self.max_reconnect_attempts})，等待 {delay} 秒...")
        time.sleep(delay)

        if not self.connect():
            print("❌ 重新连接失败")

    def send_control(self, command: str) -> bool:
        """发送控制命令"""
        try:
            if not self.is_connected:
                print("❌ MQTT未连接，无法发送控制命令")
                return False

            message = {"command": command}
            payload = json.dumps(message)

            result = self.client.publish(self.CONTROL_TOPIC, payload, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self._update_stats('messages_sent')
                return True
            else:
                print(f"❌ 控制命令发送失败，错误码: {result.rc}")
                self._update_stats('errors')
                self._update_stats('last_error', f"控制命令发送失败: {result.rc}")
                return False

        except Exception as e:
            print(f"❌ 发送控制命令异常: {e}")
            self._update_stats('errors')
            self._update_stats('last_error', f"发送控制命令异常: {e}")
            return False

    def send_recognition_result(self, names: List[str], confidence_scores: Optional[List[float]] = None) -> bool:
        """发送识别结果到OpenMV"""
        try:
            if not self.is_connected:
                print("❌ MQTT未连接，无法发送识别结果")
                self._update_stats('errors')
                self._update_stats('last_error', "MQTT未连接")
                return False

            if not isinstance(names, list):
                print(f"❌ names 参数必须是列表，实际类型: {type(names)}")
                return False

            if confidence_scores and not isinstance(confidence_scores, list):
                print(f"❌ confidence_scores 参数必须是列表，实际类型: {type(confidence_scores)}")
                return False

            if confidence_scores and len(confidence_scores) != len(names):
                print(f"❌ 置信度数量 ({len(confidence_scores)}) 与姓名数量 ({len(names)}) 不匹配")
                return False

            recognized_ids = [self.get_id_for_name(name) for name in names]

            message = {
                "recognized_names": names,
                "recognized_ids": recognized_ids,
                "count": len(names),
                "timestamp": int(time.time() * 1000),
            }

            if confidence_scores:
                message["confidence_scores"] = confidence_scores

            payload = json.dumps(message, ensure_ascii=False)

            result = self.client.publish(self.RECOGNITION_RESULT_TOPIC, payload, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self._update_stats('messages_sent')
                self._update_stats('recognition_results_sent')
                self._print_recognition_result(names, confidence_scores)
                return True
            else:
                error_messages = {
                    mqtt.MQTT_ERR_NO_CONN: "未连接",
                    mqtt.MQTT_ERR_PROTOCOL: "协议错误",
                    mqtt.MQTT_ERR_PAYLOAD_SIZE: "消息过大",
                    mqtt.MQTT_ERR_NOT_SUPPORTED: "不支持",
                    mqtt.MQTT_ERR_QUEUE_SIZE: "队列已满"
                }
                error_msg = error_messages.get(result.rc, f"未知错误: {result.rc}")
                print(f"❌ 识别结果发送失败: {error_msg}")
                self._update_stats('errors')
                self._update_stats('last_error', f"发送失败: {error_msg}")
                return False

        except Exception as e:
            print(f"❌ 发送识别结果异常: {e}")
            self._update_stats('errors')
            self._update_stats('last_error', f"发送识别结果异常: {e}")
            return False

    def send_face_collection_status(self, status: int) -> bool:
        """发送人脸采集状态到ESP32C3"""
        try:
            if not self.is_connected:
                print("❌ MQTT未连接，无法发送人脸采集状态")
                return False

            message = {
                "status": status,
                "timestamp": int(time.time() * 1000)
            }

            payload = json.dumps(message, ensure_ascii=False)

            result = self.client.publish(self.FACE_COLLECTION_STATUS_TOPIC, payload, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self._update_stats('messages_sent')
                self._update_stats('face_collection_status_sent')

                # 根据状态值输出不同的日志
                if status == 0:
                    print(f"📤 发送人脸采集状态: 0 (未检测到人脸)")
                else:
                    print(f"📤 发送人脸采集状态: 1 (人脸采集完成)")
                return True
            else:
                print(f"❌ 人脸采集状态发送失败，错误码: {result.rc}")
                self._update_stats('errors')
                self._update_stats('last_error', f"人脸采集状态发送失败: {result.rc}")
                return False

        except Exception as e:
            print(f"❌ 发送人脸采集状态异常: {e}")
            self._update_stats('errors')
            self._update_stats('last_error', f"发送人脸采集状态异常: {e}")
            return False


    def send_message(self, topic: str, message: Dict, qos: int = 0) -> bool:
        """发送通用消息到指定主题"""
        try:
            if not self.is_connected:
                print(f"❌ MQTT未连接，无法发送消息到主题: {topic}")
                return False

            payload = json.dumps(message, ensure_ascii=False)
            result = self.client.publish(topic, payload, qos=qos)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self._update_stats('messages_sent')
                if topic == self.COLLECTION_ACK_TOPIC:
                    self._update_stats('face_collection_commands_sent')
                print(f"✅ 消息发送成功到主题: {topic}")
                return True
            else:
                print(f"❌ 消息发送失败到主题 {topic}，错误码: {result.rc}")
                self._update_stats('errors')
                self._update_stats('last_error', f"消息发送失败: {result.rc}")
                return False

        except Exception as e:
            print(f"❌ 发送消息异常到主题 {topic}: {e}")
            self._update_stats('errors')
            self._update_stats('last_error', f"发送消息异常: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        try:
            self._cleanup()
        except Exception as e:
            print(f"❌ 断开连接时出现异常: {e}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self.stats.copy()
        stats.update({
            'is_connected': self.is_connected,
            'reconnect_attempts': self.reconnect_attempts,
            'max_reconnect_attempts': self.max_reconnect_attempts,
            'name_mapping_count': len(self.name_to_id_map)
        })
        return stats

    def print_detailed_stats(self):
        """打印详细统计信息"""
        stats = self.get_stats()
        print("\n" + "=" * 50)
        print("📊 MQTT管理器详细统计信息")
        print("=" * 50)
        print(f"连接状态: {'🟢 已连接' if stats['is_connected'] else '🔴 未连接'}")
        print(f"发送消息总数: {stats['messages_sent']}")
        print(f"接收消息总数: {stats['messages_received']}")
        print(f"发送的识别结果数: {stats.get('recognition_results_sent', 0)}")
        print(f"发送的人脸采集命令数: {stats.get('face_collection_commands_sent', 0)}")
        print(f"发送的人脸采集状态数: {stats.get('face_collection_status_sent', 0)}")
        print(f"错误次数: {stats['errors']}")
        print(f"人名映射数量: {stats['name_mapping_count']}")

        if stats['last_connect_time']:
            last_connect = datetime.fromtimestamp(stats['last_connect_time']).strftime("%Y-%m-%d %H:%M:%S")
            print(f"最后连接时间: {last_connect}")

        if stats['last_recognition_result']:
            last_recog = stats['last_recognition_result']
            names_with_ids = []
            for i, name in enumerate(last_recog['names']):
                person_id = last_recog['ids'][i] if i < len(last_recog['ids']) else self.get_id_for_name(name)
                names_with_ids.append(f"{name}[{person_id}]")
            print(f"最后识别结果: {', '.join(names_with_ids)} (时间: {last_recog['timestamp']})")

        if stats['last_error']:
            print(f"最后错误: {stats['last_error']}")
        print("=" * 50)

    def __del__(self):
        """析构函数"""
        self.disconnect()


# 使用示例
if __name__ == "__main__":
    def message_callback(data):
        """消息回调示例"""
        topic = data['topic']
        payload = data['payload']
        #print(f"收到消息 - 主题: {topic}, 数据: {payload}")


    # 创建MQTT管理器
    mqtt_manager = MQTTManager()
    mqtt_manager.set_message_callback(message_callback)

    # 设置人名映射
    name_mapping = {
        "张三": "001",
        "李四": "002",
        "王五": "003"
    }
    mqtt_manager.update_name_mapping(name_mapping)

    # 连接服务器
    if mqtt_manager.connect():
        print("✅ MQTT连接成功")

        # 模拟发送识别结果
        names = ["张三", "李四"]
        confidence_scores = [0.85, 0.92]

        if mqtt_manager.send_recognition_result(names, confidence_scores):
            print("✅ 识别结果发送成功")

        # 模拟发送人脸采集状态
        if mqtt_manager.send_face_collection_status(1):
            print("✅ 人脸采集状态发送成功")

        # 打印统计信息
        mqtt_manager.print_detailed_stats()

        # 保持运行
        time.sleep(5)

        # 断开连接
        mqtt_manager.disconnect()
    else:
        print("❌ MQTT连接失败")
