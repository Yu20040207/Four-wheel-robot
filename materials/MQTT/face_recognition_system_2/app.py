import warnings

warnings.filterwarnings("ignore", category=UserWarning)

from flask import Flask, render_template, Response, jsonify, request
import json
import time
import threading
import os
import cv2
import numpy as np
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
import face_recognition
import logging
from typing import List, Dict, Any, Optional, Tuple

app = Flask(__name__)

# 配置日志 - 只显示警告和错误信息
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 特别设置Werkzeug的日志级别为ERROR，取消访问日志
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# 导入自定义模块
from mqtt_manager import MQTTManager
from face_database import FaceDatabase

# 配置常量 - 新增帧率优化配置
CONFIG = {
    'recognition_interval': 2,
    'frame_skip_interval': 2,
    'min_process_interval': 0.05,  # 减小处理间隔，从0.1改为0.05
    'attendance_data_file': 'attendance_data.json',
    'face_collection_total': 5,
    'recognition_confidence_threshold': 60,
    'face_detection_model': 'hog',
    'image_scale_factor': 0.5,
    'background_processing_interval': 0.5,
    'face_collection_status_topic': 'face_collection_status',
    # 新增帧率优化配置
    'display_scale_factor': 0.6,  # 显示时的缩放因子
    'jpeg_quality': 70,  # JPEG压缩质量（70%以减小传输大小）
    'video_feed_sleep': 0.02,  # 视频流休眠时间，从0.03改为0.02
    'max_display_width': 640,  # 最大显示宽度
    'max_display_height': 480,  # 最大显示高度
    'frame_cache_time': 0.05,  # 帧缓存时间
    'min_frame_interval': 0.016,  # 最小帧间隔（约60fps）
}


# 全局状态管理类
class GlobalState:
    def __init__(self):
        self.current_frame = None
        self.last_raw_frame = None  # 新增：原始帧缓存
        self.frame_lock = threading.Lock()
        self.connected_clients = 0
        self.recognition_enabled = False
        self.last_recognition_time = 0
        self.face_collection_active = False
        self.attendance_system_enabled = False
        self.frame_skip_counter = 0
        self.last_processed_time = 0
        self.last_recognition_results = []

        self.video_stream_active = False
        self.video_stream_start_time = 0

        self.background_processing = False
        self.last_background_process_time = 0
        self.background_processing_results = []

        # 新增：帧率优化相关状态
        self.frame_cache = None
        self.last_cache_time = 0
        self.frame_count = 0
        self.last_fps_calc_time = time.time()
        self.fps = 0

        # 新增：显示帧缓存
        self.display_frame_cache = None
        self.display_frame_lock = threading.Lock()

        self.attendance_settings = {
            'morning_start_time': '09:00',
            'morning_end_time': '12:00',
            'afternoon_start_time': '13:00',
            'afternoon_end_time': '18:00'
        }

        self.stats = {
            'fps': 0, 'frames_received': 0, 'latency': 0, 'clients': 0,
            'last_frame_time': 0, 'last_recognized_names': [], 'processing_time': 0,
            'frame_skip_rate': 0, 'recognition_status': 'stopped', 'current_recognitions': [],
            'known_faces': 0, 'mqtt_connected': False, 'face_collection_active': False,
            'attendance_system_enabled': False, 'loaded_faces': 0, 'collection_progress': '0/5',
            'background_processing': False,
            'last_video_print_time': 0,
            'video_feed_fps': 0,  # 新增：视频流实际帧率
            'frame_size': 'N/A',  # 新增：帧大小信息
        }

        self.face_collection_state = {
            'active': False, 'person_name': None, 'images_collected': 0,
            'total_images': CONFIG['face_collection_total'], 'last_capture_time': 0,
            'status_message': '',
            'last_status_send_time': 0,
            'completion_sent': False
        }


# 初始化全局状态和模块
state = GlobalState()
face_db = FaceDatabase()
mqtt_manager = MQTTManager()

# 新增：后台处理线程
background_thread = None
background_thread_running = False


def background_face_processing():
    """后台人脸识别处理线程"""
    global state, background_thread_running
    print("🔧 启动后台人脸识别处理线程")

    while background_thread_running:
        try:
            current_time = time.time()

            if (state.recognition_enabled and
                    not state.face_collection_active and
                    current_time - state.last_background_process_time > CONFIG['background_processing_interval']):

                with state.frame_lock:
                    if state.current_frame is not None:
                        recognition_results = face_processor.recognize_faces(state.current_frame)
                        state.background_processing_results = recognition_results

                        current_names = []
                        current_recognitions = []
                        confidence_scores = []

                        for (top, right, bottom, left), (name, confidence) in recognition_results:
                            if name != "Unknown" and confidence > CONFIG['recognition_confidence_threshold']:
                                current_names.append(name)
                                confidence_scores.append(round(confidence, 1))
                                current_recognitions.append({
                                    'name': name,
                                    'confidence': round(confidence, 1),
                                    'time': datetime.now().strftime('%H:%M:%S')
                                })

                        state.stats['last_recognized_names'] = current_names
                        state.stats['current_recognitions'] = current_recognitions

                        if (current_names and
                                current_time - state.last_recognition_time > CONFIG['recognition_interval'] and
                                mqtt_manager.is_connected):
                            unique_names = list(set(current_names))
                            mqtt_manager.send_recognition_result(unique_names, confidence_scores)
                            state.last_recognition_time = current_time
                            process_face_recognition_for_attendance(unique_names)

                        state.last_background_process_time = current_time
                        state.stats['background_processing'] = True

            time.sleep(0.05)  # 减少休眠时间

        except Exception as e:
            logger.error(f"后台处理错误: {e}")
            time.sleep(0.5)


def start_background_processing():
    """启动后台处理线程"""
    global background_thread, background_thread_running

    if background_thread is None or not background_thread.is_alive():
        background_thread_running = True
        background_thread = threading.Thread(target=background_face_processing, daemon=True)
        background_thread.start()
        print("✅ 后台人脸识别处理线程已启动")


def stop_background_processing():
    """停止后台处理线程"""
    global background_thread_running
    background_thread_running = False
    print("⏹️ 后台人脸识别处理线程已停止")


# 修改AttendanceManager类的__init__方法
class AttendanceManager:
    """打卡管理类"""

    def __init__(self, data_file: str):
        # 确保路径是有效的
        if not data_file:
            # 使用默认路径
            self.data_file = 'attendance_data.json'
        else:
            self.data_file = data_file

        # 确保目录存在
        self._ensure_data_dir()
        self.records = []
        self.load_data()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        try:
            data_dir = os.path.dirname(self.data_file)
            if data_dir:  # 如果指定了目录路径
                os.makedirs(data_dir, exist_ok=True)
            else:
                # 如果没有指定目录，使用当前目录
                pass
        except Exception as e:
            logger.error(f"创建数据目录失败: {e}")

    def load_data(self) -> bool:
        """加载打卡数据 - 修复编码问题"""
        try:
            if os.path.exists(self.data_file):
                encodings = ['utf-8', 'gbk', 'latin-1', 'iso-8859-1']
                for encoding in encodings:
                    try:
                        with open(self.data_file, 'r', encoding=encoding) as f:
                            self.records = json.load(f)
                        print(f"✅ 使用 {encoding} 编码成功加载打卡数据")
                        return True
                    except UnicodeDecodeError:
                        continue
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON解析错误: {e}")
                        # 如果JSON损坏，创建备份并重置数据
                        if os.path.exists(self.data_file):
                            backup_file = self.data_file + '.backup'
                            os.rename(self.data_file, backup_file)
                            print(f"📦 已创建损坏文件的备份: {backup_file}")
                        self.records = []
                        return True

                # 如果所有编码都失败，使用二进制读取
                try:
                    with open(self.data_file, 'rb') as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        self.records = json.loads(content)
                    print("✅ 使用忽略错误方式加载打卡数据")
                    return True
                except:
                    self.records = []
                    return True
            else:
                print(f"📝 打卡数据文件不存在，将创建新文件: {self.data_file}")
                self.records = []
                return True
        except Exception as e:
            logger.error(f"❌ 加载打卡数据失败: {e}")
            self.records = []
            return False

    def save_data(self) -> bool:
        """保存打卡数据 - 修复编码问题"""
        try:
            # 确保目录存在
            self._ensure_data_dir()

            # 使用UTF-8编码保存
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
            print(f"✅ 打卡数据已保存到: {self.data_file}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存打卡数据失败: {e}")
            # 尝试使用备份方式保存
            try:
                with open(self.data_file, 'wb') as f:
                    content = json.dumps(self.records, ensure_ascii=False, indent=2)
                    f.write(content.encode('utf-8'))
                print(f"✅ 使用二进制方式保存打卡数据到: {self.data_file}")
                return True
            except Exception as e2:
                logger.error(f"❌ 备份保存也失败: {e2}")
                return False

    @staticmethod
    def get_time_difference(time1_str: str, time2_str: str) -> float:
        """计算两个时间的差值（分钟）"""
        try:
            time1 = datetime.strptime(time1_str, '%H:%M')
            time2 = datetime.strptime(time2_str, '%H:%M')
            return (time2 - time1).total_seconds() / 60
        except Exception:
            return 0

    def determine_check_type(self, record: Dict, current_time_str: str, settings: Dict) -> Tuple[
        Optional[str], Optional[str]]:
        """根据时间自动判断打卡类型"""
        try:
            morning_start = settings['morning_start_time']
            morning_end = settings['morning_end_time']
            afternoon_start = settings['afternoon_start_time']
            afternoon_end = settings['afternoon_end_time']

            has_morning_checkin = record.get('morning_check_in') is not None
            has_morning_checkout = record.get('morning_check_out') is not None
            has_afternoon_checkin = record.get('afternoon_check_in') is not None
            has_afternoon_checkout = record.get('afternoon_check_out') is not None

            current_time = datetime.strptime(current_time_str, '%H:%M')
            morning_start_time = datetime.strptime(morning_start, '%H:%M')
            morning_end_time = datetime.strptime(morning_end, '%H:%M')
            afternoon_start_time = datetime.strptime(afternoon_start, '%H:%M')
            afternoon_end_time = datetime.strptime(afternoon_end, '%H:%M')

            if morning_start_time <= current_time <= morning_end_time:
                if not has_morning_checkin:
                    diff_minutes = self.get_time_difference(morning_start, current_time_str)
                    if diff_minutes <= 0:
                        return 'morning_check_in', '正常'
                    elif diff_minutes <= 60:
                        return 'morning_check_in', '迟到'
                    else:
                        return 'morning_check_in', '迟到'
                elif not has_morning_checkout:
                    diff_minutes = self.get_time_difference(current_time_str, morning_end)
                    if diff_minutes >= 0:
                        return 'morning_check_out', '早退'
                    else:
                        return 'morning_check_out', '正常'

            elif morning_end_time < current_time < afternoon_start_time:
                return None, None

            elif afternoon_start_time <= current_time <= afternoon_end_time:
                if not has_afternoon_checkin:
                    diff_minutes = self.get_time_difference(afternoon_start, current_time_str)
                    if diff_minutes <= 0:
                        return 'afternoon_check_in', '正常'
                    elif diff_minutes <= 60:
                        return 'afternoon_check_in', '迟到'
                    else:
                        return 'afternoon_check_in', '迟到'
                elif not has_afternoon_checkout:
                    diff_minutes = self.get_time_difference(current_time_str, afternoon_end)
                    if diff_minutes >= 0:
                        return 'afternoon_check_out', '早退'
                    else:
                        return 'afternoon_check_out', '正常'

            elif current_time > afternoon_end_time:
                if not has_afternoon_checkout:
                    return 'afternoon_check_out', '正常'

            elif current_time < morning_start_time:
                if not has_morning_checkin:
                    return 'morning_check_in', '正常'

            return None, None

        except Exception as e:
            logger.error(f"判断打卡类型失败: {e}")
            return 'morning_check_in', '正常'

    def record_attendance(self, person_name: str, settings: Dict) -> bool:
        """记录打卡"""
        try:
            now = datetime.now()
            today = now.date().isoformat()
            current_time = now.strftime('%H:%M')

            today_record = None
            for record in self.records:
                if record['name'] == person_name and record['date'] == today:
                    today_record = record
                    break

            if not today_record:
                today_record = {
                    'name': person_name,
                    'date': today,
                    'morning_check_in': None,
                    'morning_check_out': None,
                    'afternoon_check_in': None,
                    'afternoon_check_out': None,
                    'status': '缺勤',
                    'work_duration': None,
                    'auto_status': True
                }
                self.records.append(today_record)

            check_type, auto_status = self.determine_check_type(today_record, current_time, settings)

            if check_type and auto_status:
                if today_record.get('auto_status', True):
                    if check_type == 'morning_check_in' and not today_record['morning_check_in']:
                        today_record['morning_check_in'] = current_time
                    elif check_type == 'morning_check_out' and not today_record['morning_check_out']:
                        today_record['morning_check_out'] = current_time
                    elif check_type == 'afternoon_check_in' and not today_record['afternoon_check_in']:
                        today_record['afternoon_check_in'] = current_time
                    elif check_type == 'afternoon_check_out' and not today_record['afternoon_check_out']:
                        today_record['afternoon_check_out'] = current_time
                    else:
                        return True
                else:
                    return True

            self.update_attendance_status(today_record, settings)
            return self.save_data()

        except Exception as e:
            logger.error(f"❌ 记录打卡失败: {e}")
            return False

    def update_attendance_status(self, record: Dict, settings: Dict):
        """更新打卡状态"""
        try:
            morning_check_in = record.get('morning_check_in')
            morning_check_out = record.get('morning_check_out')
            afternoon_check_in = record.get('afternoon_check_in')
            afternoon_check_out = record.get('afternoon_check_out')

            total_minutes = 0

            if morning_check_in and morning_check_out:
                try:
                    start_time = datetime.strptime(morning_check_in, '%H:%M')
                    end_time = datetime.strptime(morning_check_out, '%H:%M')
                    work_duration = end_time - start_time
                    total_minutes += work_duration.seconds // 60
                except Exception:
                    pass

            if afternoon_check_in and afternoon_check_out:
                try:
                    start_time = datetime.strptime(afternoon_check_in, '%H:%M')
                    end_time = datetime.strptime(afternoon_check_out, '%H:%M')
                    work_duration = end_time - start_time
                    total_minutes += work_duration.seconds // 60
                except Exception:
                    pass

            if total_minutes > 0:
                hours = total_minutes // 60
                minutes = total_minutes % 60
                record['work_duration'] = f"{hours}小时{minutes}分钟"
            else:
                record['work_duration'] = "0小时0分钟"

            if record.get('auto_status', True):
                all_checks = [morning_check_in, morning_check_out, afternoon_check_in, afternoon_check_out]
                completed_checks = [check for check in all_checks if check is not None]

                if len(completed_checks) == 0:
                    record['status'] = '缺勤'
                elif len(completed_checks) < 4:
                    record['status'] = '部分打卡'
                else:
                    morning_start = settings['morning_start_time']
                    morning_end = settings['morning_end_time']
                    afternoon_start = settings['afternoon_start_time']
                    afternoon_end = settings['afternoon_end_time']

                    morning_late = self.get_time_difference(morning_start, morning_check_in) > 0
                    morning_early = self.get_time_difference(morning_check_out, morning_end) > 0
                    afternoon_late = self.get_time_difference(afternoon_start, afternoon_check_in) > 0
                    afternoon_early = self.get_time_difference(afternoon_check_out, afternoon_end) > 0

                    if (morning_late or afternoon_late) and (morning_early or afternoon_early):
                        record['status'] = '迟到早退'
                    elif morning_late or afternoon_late:
                        record['status'] = '迟到'
                    elif morning_early or afternoon_early:
                        record['status'] = '早退'
                    else:
                        record['status'] = '正常'

        except Exception as e:
            logger.error(f"❌ 更新打卡状态失败: {e}")
            record['status'] = '异常'

    def get_records_by_date(self, target_date: str = None) -> List[Dict]:
        """根据日期获取打卡记录"""
        try:
            if not target_date:
                end_date = datetime.now().date()
                start_date = end_date - timedelta(days=7)

                recent_records = []
                for record in self.records:
                    try:
                        record_date = datetime.strptime(record['date'], '%Y-%m-%d').date()
                        if start_date <= record_date <= end_date:
                            recent_records.append(record)
                    except:
                        continue

                recent_records.sort(key=lambda x: x['date'], reverse=True)
                return recent_records[-50:]
            else:
                filtered_records = []
                for record in self.records:
                    if record.get('date') == target_date:
                        filtered_records.append(record)

                filtered_records.sort(key=lambda x: x.get('name', ''))
                return filtered_records

        except Exception as e:
            logger.error(f"获取日期记录失败: {e}")
            return []

    def get_today_stats(self, target_date: str = None) -> Dict:
        """获取指定日期的统计信息"""
        try:
            if not target_date:
                target_date = datetime.now().date().isoformat()

            today_stats = {
                'today_checkins': 0,
                'on_time': 0,
                'late': 0,
                'early_leave': 0,
                'date': target_date
            }

            for record in self.records:
                if record.get('date') == target_date:
                    today_stats['today_checkins'] += 1
                    status = record.get('status', '')
                    if status == '正常':
                        today_stats['on_time'] += 1
                    elif status == '迟到':
                        today_stats['late'] += 1
                    elif status == '早退':
                        today_stats['early_leave'] += 1

            return today_stats
        except Exception as e:
            logger.error(f"获取今日统计失败: {e}")
            return {'today_checkins': 0, 'on_time': 0, 'late': 0, 'early_leave': 0, 'date': target_date}


# 初始化打卡管理器
attendance_manager = AttendanceManager(CONFIG['attendance_data_file'])


class FaceProcessor:
    """人脸处理类"""

    def __init__(self, face_db: FaceDatabase):
        self.face_db = face_db
        # 新增：缓存识别结果
        self.last_recognition_cache = None
        self.last_cache_time = 0

    def detect_faces(self, frame_data: bytes) -> List[Tuple]:
        """检测人脸并返回人脸位置"""
        try:
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                return []

            small_frame = cv2.resize(frame, (0, 0), fx=CONFIG['image_scale_factor'], fy=CONFIG['image_scale_factor'])
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_frame, model=CONFIG['face_detection_model'])

            scale_factor = int(1 / CONFIG['image_scale_factor'])
            original_face_locations = []
            for (top, right, bottom, left) in face_locations:
                original_face_locations.append((
                    top * scale_factor, right * scale_factor,
                    bottom * scale_factor, left * scale_factor
                ))

            return original_face_locations

        except Exception as e:
            logger.error(f"人脸检测错误: {e}")
            return []

    def recognize_faces(self, frame_data: bytes) -> List[Tuple]:
        """识别人脸"""
        if len(self.face_db.known_face_encodings) == 0:
            return []

        try:
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                return []

            small_frame = cv2.resize(frame, (0, 0), fx=CONFIG['image_scale_factor'], fy=CONFIG['image_scale_factor'])
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_frame, model=CONFIG['face_detection_model'])

            if len(face_locations) == 0:
                return []

            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            if len(face_encodings) == 0:
                return []

            face_names = []
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(
                    self.face_db.known_face_encodings,
                    face_encoding,
                    tolerance=0.6
                )
                face_distances = face_recognition.face_distance(
                    self.face_db.known_face_encodings,
                    face_encoding
                )

                best_match_index = np.argmin(face_distances)
                min_distance = face_distances[best_match_index]

                if matches[best_match_index] and min_distance < 0.6:
                    name = self.face_db.known_face_names[best_match_index]
                    confidence = (1 - min_distance) * 100
                    face_names.append((name, confidence))
                else:
                    face_names.append(("Unknown", 0))

            scale_factor = int(1 / CONFIG['image_scale_factor'])
            original_face_locations = []
            for (top, right, bottom, left) in face_locations:
                original_face_locations.append((
                    top * scale_factor, right * scale_factor,
                    bottom * scale_factor, left * scale_factor
                ))

            return list(zip(original_face_locations, face_names))

        except Exception as e:
            logger.error(f"人脸识别错误: {e}")
            return []


# 初始化人脸处理器
face_processor = FaceProcessor(face_db)


def process_face_recognition_for_attendance(recognized_names: List[str]):
    """处理人脸识别结果用于打卡"""
    if not state.attendance_system_enabled or not recognized_names:
        return

    try:
        for name in recognized_names:
            if name != "Unknown":
                attendance_manager.record_attendance(name, state.attendance_settings)
    except Exception as e:
        logger.error(f"❌ 处理打卡识别失败: {e}")


def update_mqtt_mapping() -> bool:
    """更新MQTT的人名到ID的映射"""
    try:
        if hasattr(face_db, 'fix_all_metadata_ids'):
            success, message = face_db.fix_all_metadata_ids()
            if success:
                print(f"✅ {message}")
            else:
                print(f"⚠️ 修复元数据失败: {message}")

        name_mapping = face_db.get_name_id_mapping()
        print(f"🔄 更新MQTT映射: {len(name_mapping)} 条记录")

        print("📋 当前映射详情:")
        for name, id_str in name_mapping.items():
            print(f"   {name} -> {id_str}")

        if hasattr(mqtt_manager, 'update_name_id_mapping'):
            mqtt_manager.update_name_id_mapping(name_mapping)
            # print("✅ 通过 update_name_id_mapping 更新MQTT映射")
        elif hasattr(mqtt_manager, 'update_name_mapping'):
            mqtt_manager.update_name_mapping(name_mapping)
            print("✅ 通过 update_name_mapping 更新MQTT映射")
        else:
            mqtt_manager.name_to_id_map = name_mapping
            mqtt_manager.id_to_name_map = {v: k for k, v in name_mapping.items()}
            print("✅ 直接设置属性更新MQTT映射")

        print("🔍 验证MQTT管理器中的映射:")
        if hasattr(mqtt_manager, 'name_to_id_map'):
            print(f"   MQTT管理器映射: {mqtt_manager.name_to_id_map}")
            print(f"   映射条目数: {len(mqtt_manager.name_to_id_map)}")

        return True
    except Exception as e:
        logger.error(f"更新MQTT映射失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def start_face_collection(person_name: str, person_id: str = None) -> Tuple[bool, str]:
    """开始人脸采集过程 - 修复版本"""
    global state

    if state.face_collection_state['active']:
        return False, "正在采集其他人脸，请稍后再试"

    # 停止人脸识别
    state.recognition_enabled = False
    state.face_collection_active = True

    state.face_collection_state = {
        'active': True,
        'person_name': person_name,
        'person_id': person_id,
        'images_collected': 0,
        'total_images': CONFIG['face_collection_total'],
        'last_capture_time': 0,
        'status_message': f'开始为 {person_name} 采集人脸数据...',
        'last_status_send_time': 0,
        'completion_sent': False  # 重置完成状态
    }

    print(f"📸 开始人脸采集: {person_name} (ID: {person_id})")
    print("⏸️ 人脸识别已自动暂停")
    return True, f"开始为 {person_name} 采集人脸数据，请确保人脸在摄像头前"


def process_face_collection():
    """处理人脸采集过程 - 修复版本"""
    global state

    if not state.face_collection_state['active']:
        return

    current_time = time.time()

    # 检查采集间隔
    if current_time - state.face_collection_state['last_capture_time'] < 2.0:
        return

    with state.frame_lock:
        if state.current_frame is None:
            # 没有帧数据，检查是否需要发送0
            if (mqtt_manager.is_connected and
                    current_time - state.face_collection_state['last_status_send_time'] > 1.0):
                mqtt_manager.send_face_collection_status(0)
                state.face_collection_state['last_status_send_time'] = current_time
            return

        face_locations = face_processor.detect_faces(state.current_frame)

        if len(face_locations) > 0:
            # 检测到人脸，采集图片
            success, message = face_db.add_face_image(
                state.face_collection_state['person_name'],
                state.current_frame,
                state.face_collection_state['person_id']
            )

            if success:
                state.face_collection_state['images_collected'] += 1
                state.face_collection_state['last_capture_time'] = current_time
                state.face_collection_state['status_message'] = \
                    f'已采集 {state.face_collection_state["images_collected"]}/{CONFIG["face_collection_total"]} 张图片'

                # 采集完成
                if (state.face_collection_state['images_collected'] >= CONFIG['face_collection_total'] and
                        not state.face_collection_state['completion_sent']):

                    # 更新MQTT映射
                    update_mqtt_mapping()

                    state.face_collection_state['status_message'] = \
                        f'已完成 {state.face_collection_state["person_name"]} 的人脸采集'

                    # 发送完成信号（状态码 1）
                    if mqtt_manager.is_connected:
                        mqtt_manager.send_face_collection_status(1)
                        state.face_collection_state['completion_sent'] = True

                    # 等待1秒后停止采集
                    print(f"🎉 人脸采集完成: {state.face_collection_state['person_name']}")
                    time.sleep(1)
                    state.face_collection_state['active'] = False
                    state.face_collection_active = False
        else:
            # 未检测到人脸，检查是否需要发送0（间隔1秒）
            if (mqtt_manager.is_connected and
                    current_time - state.face_collection_state['last_status_send_time'] > 2.5):
                mqtt_manager.send_face_collection_status(0)
                state.face_collection_state['last_status_send_time'] = current_time

            state.face_collection_state['status_message'] = '未检测到人脸，请确保人脸在摄像头前'


def optimize_frame_size(frame):
    """优化帧大小以提升传输效率"""
    try:
        height, width = frame.shape[:2]

        # 如果帧太大，调整大小
        if width > CONFIG['max_display_width'] or height > CONFIG['max_display_height']:
            # 计算缩放比例
            scale_width = CONFIG['max_display_width'] / width
            scale_height = CONFIG['max_display_height'] / height
            scale = min(scale_width, scale_height, CONFIG['display_scale_factor'])

            new_width = int(width * scale)
            new_height = int(height * scale)

            # 使用快速插值方法
            frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

        return frame
    except Exception as e:
        logger.error(f"优化帧大小失败: {e}")
        return frame


def process_frame_with_faces(frame_data: bytes) -> bytes:
    """处理帧中的人脸检测和识别 - 优化版本"""
    global state

    start_time = time.time()

    try:
        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return frame_data

        current_time = time.time()

        if current_time - state.last_processed_time < CONFIG['min_process_interval']:
            state.frame_skip_counter += 1
            recognition_results = state.last_recognition_results
        else:
            state.last_processed_time = current_time

            if state.face_collection_active:
                face_locations = face_processor.detect_faces(frame_data)

                for (top, right, bottom, left) in face_locations:
                    color = (255, 255, 0)
                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                    cv2.putText(frame,
                                f"Collecting: {state.face_collection_state['images_collected'] + 1}/{CONFIG['face_collection_total']}",
                                (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                state.last_recognition_results = list(zip(face_locations, [("Collecting", 100)] * len(face_locations)))
                recognition_results = state.last_recognition_results

            else:
                face_locations = face_processor.detect_faces(frame_data)

                if len(face_locations) > 0:
                    recognition_results = face_processor.recognize_faces(frame_data)

                    current_names = []
                    current_recognitions = []
                    confidence_scores = []

                    for (top, right, bottom, left), (name, confidence) in recognition_results:
                        if name != "Unknown" and confidence > CONFIG['recognition_confidence_threshold']:
                            current_names.append(name)
                            confidence_scores.append(round(confidence, 1))
                            current_recognitions.append({
                                'name': name,
                                'confidence': round(confidence, 1),
                                'time': datetime.now().strftime('%H:%M:%S')
                            })

                    state.stats['last_recognized_names'] = current_names
                    state.stats['current_recognitions'] = current_recognitions

                    if (current_names and
                            current_time - state.last_recognition_time > CONFIG['recognition_interval'] and
                            mqtt_manager.is_connected):
                        unique_names = list(set(current_names))
                        mqtt_manager.send_recognition_result(unique_names, confidence_scores)
                        state.last_recognition_time = current_time
                        process_face_recognition_for_attendance(unique_names)
                else:
                    recognition_results = []
                    state.last_recognition_results = []

                state.last_recognition_results = recognition_results

        # 优化：减少绘制的矩形框厚度
        for (top, right, bottom, left), (name, confidence) in recognition_results:
            color = (0, 255, 0)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 1)  # 厚度从2改为1

            if name == "Unknown":
                text = "Unknown"
                text_color = (0, 0, 255)
            elif name == "Collecting":
                text = f"Collecting: {state.face_collection_state['images_collected'] + 1}/{CONFIG['face_collection_total']}"
                text_color = (255, 255, 0)
            else:
                text = f"{name} ({confidence:.1f}%)"
                text_color = (0, 255, 0)

            cv2.putText(frame, text, (left, top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1)  # 字体大小和厚度减小

        # 优化帧大小
        frame = optimize_frame_size(frame)

        # 优化编码参数
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CONFIG['jpeg_quality']]
        _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)

        processing_time = (time.time() - start_time) * 1000
        state.stats['processing_time'] = round(processing_time, 2)
        state.stats['frame_skip_rate'] = state.frame_skip_counter

        # 记录帧大小信息
        state.stats['frame_size'] = f"{jpeg_data.size // 1024}KB"

        return jpeg_data.tobytes()

    except Exception as e:
        logger.error(f"处理帧错误: {e}")
        return frame_data


def process_frame_for_display(frame_data: bytes) -> bytes:
    """处理帧用于显示（不进行识别，只绘制已有结果）- 优化版本"""
    global state

    try:
        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return frame_data

        recognition_results = state.background_processing_results

        # 优化：减少绘制频率
        current_time = time.time()
        if (recognition_results and
                current_time - state.last_processed_time > CONFIG['min_frame_interval']):

            for (top, right, bottom, left), (name, confidence) in recognition_results:
                color = (0, 255, 0)
                cv2.rectangle(frame, (left, top), (right, bottom), color, 1)  # 厚度从2改为1

                if name == "Unknown":
                    text = "Unknown"
                    text_color = (0, 0, 255)
                else:
                    text = f"{name} ({confidence:.1f}%)"
                    text_color = (0, 255, 0)

                cv2.putText(frame, text, (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1)  # 字体大小和厚度减小

            state.last_processed_time = current_time

        # 优化帧大小
        frame = optimize_frame_size(frame)

        # 优化编码参数
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CONFIG['jpeg_quality']]
        _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)

        return jpeg_data.tobytes()

    except Exception as e:
        logger.error(f"显示处理帧错误: {e}")
        return frame_data


def handle_video_data(data: Dict):
    """处理接收到的视频数据 - 优化版本"""
    global state
    try:
        if 'data' in data:
            hex_data = data['data']
            if isinstance(hex_data, bytes):
                hex_data = hex_data.decode('latin-1')
            jpeg_bytes = bytes.fromhex(hex_data)

            with state.frame_lock:
                state.current_frame = jpeg_bytes
                state.last_raw_frame = jpeg_bytes  # 保存原始帧

            state.stats['frames_received'] += 1
            state.stats['last_frame_time'] = time.time()

            # 计算FPS
            state.frame_count += 1
            current_time = time.time()
            if current_time - state.last_fps_calc_time >= 1.0:
                state.fps = state.frame_count
                state.frame_count = 0
                state.last_fps_calc_time = current_time
                state.stats['fps'] = state.fps

            if 'timestamp' in data:
                state.stats['latency'] = int((time.time() * 1000) - data['timestamp'])

    except Exception as e:
        logger.error(f"处理视频数据错误: {e}")


def handle_flask_control_message(data: Dict):
    """处理来自OpenMV的Flask控制消息"""
    global state
    try:
        command = data.get('command')
        client_id = data.get('client_id', '未知客户端')

        print(f"📨 收到来自 {client_id} 的控制命令: {command}")

        if command == 'start_recognition' or command == 'recognition_on':
            state.recognition_enabled = True
            state.stats['recognition_status'] = 'running'
            start_background_processing()
            print("🔍 Flask人脸识别已开启 (由OpenMV触发)")
            print("🔧 后台处理线程已激活")

        elif command == 'stop_recognition' or command == 'recognition_off':
            state.recognition_enabled = False
            state.stats['recognition_status'] = 'stopped'
            stop_background_processing()
            print("⏹️ Flask人脸识别已关闭 (由OpenMV触发)")

        elif command == 'attendance_on':
            state.attendance_system_enabled = True
            state.recognition_enabled = True
            state.stats['recognition_status'] = 'running'
            start_background_processing()
            print("🟢 上下班打卡系统已开启 (由OpenMV触发)，并自动开启人脸识别")
            print("🔧 后台处理线程已激活")

        elif command == 'attendance_off':
            state.attendance_system_enabled = False
            # 修改：关闭打卡系统时也关闭人脸识别
            state.recognition_enabled = False
            state.stats['recognition_status'] = 'stopped'
            stop_background_processing()
            print("🔴 上下班打卡系统已关闭 (由OpenMV触发)，并自动关闭人脸识别")
            print("⏹️ 后台处理线程已停止")

        else:
            print(f"⚠️ 未知的控制命令: {command}")

    except Exception as e:
        logger.error(f"❌ 处理Flask控制消息失败: {e}")


def handle_face_collection_message(data: Dict):
    """处理人脸采集消息"""
    global state
    try:
        action = data.get('action')
        client_id = data.get('client_id', '未知设备')

        print(f"📨 收到人脸采集消息: {action} 来自 {client_id}")

        if action == 'start_collection':
            if state.face_collection_active:
                print("⚠️ 人脸采集正在进行中，无法开始新的采集")
                if mqtt_manager.is_connected:
                    mqtt_manager.send_message("openmv/collection_ack", {
                        "status": "error",
                        "message": "人脸采集正在进行中，请等待完成"
                    })
                return

            person_name, person_id = face_db.generate_auto_name_and_id()
            print(f"🆔 开始人脸采集: {person_name} (ID: {person_id})")

            success, message = start_face_collection(person_name, person_id)
            if success:
                print(f"📸 人脸采集已开始: {person_name} (ID: {person_id})，来自设备: {client_id}")
                if mqtt_manager.is_connected:
                    mqtt_manager.send_message("openmv/collection_ack", {
                        "status": "started",
                        "person_name": person_name,
                        "person_id": person_id,
                        "message": "人脸采集已开始"
                    })
            else:
                print(f"❌ 人脸采集失败: {message}，来自设备: {client_id}")
                if mqtt_manager.is_connected:
                    mqtt_manager.send_message("openmv/collection_ack", {
                        "status": "error",
                        "message": message
                    })

        elif action == 'cancel_collection':
            if state.face_collection_active:
                print(f"⏹️ 收到取消采集指令，来自设备: {client_id}")
                # 调用取消采集函数
                cancel_collection_internal()

    except Exception as e:
        logger.error(f"处理人脸采集消息错误: {e}")


def cancel_collection_internal():
    """内部取消采集函数 - 确保彻底清理采集状态"""
    global state

    if not state.face_collection_active:
        print("⚠️ 没有活动的采集任务可以取消")
        return False

    try:
        # 获取采集信息
        person_name = state.face_collection_state['person_name']
        person_id = state.face_collection_state['person_id']
        images_collected = state.face_collection_state['images_collected']

        print(f"⏹️ 开始取消人脸采集: {person_name} (ID: {person_id})")
        print(f"📊 已采集图片: {images_collected}/{CONFIG['face_collection_total']}")

        # 首先重置状态，避免后续处理
        state.face_collection_active = False
        state.face_collection_state = {
            'active': False,
            'person_name': None,
            'person_id': None,
            'images_collected': 0,
            'total_images': CONFIG['face_collection_total'],
            'last_capture_time': 0,
            'status_message': '人脸采集已取消',
            'last_status_send_time': 0,
            'completion_sent': True  # 设置为 True 防止重复发送完成信号
        }

        # 删除已采集的图片
        if person_name and images_collected > 0:
            try:
                # 调用face_db删除已采集的图片
                success, message = face_db.delete_collection_progress(person_name)
                if success:
                    print(f"🗑️ {message}")
                else:
                    print(f"⚠️ 删除图片失败: {message}")
            except Exception as e:
                print(f"⚠️ 删除图片时出错: {e}")

        # 恢复识别状态
        if not state.attendance_system_enabled:
            state.recognition_enabled = False
        else:
            state.recognition_enabled = True

        # 发送取消状态到MQTT（-1 表示取消）
        if mqtt_manager.is_connected:
            try:
                mqtt_manager.send_face_collection_status(-1)
                print("📤 已发送采集取消状态到MQTT")
            except Exception as e:
                print(f"⚠️ 发送MQTT消息失败: {e}")

        print(f"✅ 人脸采集已成功取消: {person_name}")
        return True

    except Exception as e:
        logger.error(f"取消采集时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def handle_mqtt_message(data: Dict):
    """处理MQTT消息"""
    try:
        if 'topic' in data and 'payload' in data:
            topic = data['topic']
            payload = data['payload']

            current_time = time.time()
            is_video_topic = topic == mqtt_manager.VIDEO_TOPIC

            if not is_video_topic:
                print(f"📨 Flask收到MQTT消息: 主题={topic}")
            elif current_time - state.stats['last_video_print_time'] > 1.0:
                state.stats['last_video_print_time'] = current_time

            processed_payload = None

            if isinstance(payload, bytes):
                try:
                    payload_str = payload.decode('utf-8')
                    if not is_video_topic:
                        print(f"🔤 解码后的payload字符串: {payload_str[:100]}...")
                    processed_payload = json.loads(payload_str)
                except UnicodeDecodeError:
                    try:
                        payload_str = payload.decode('latin-1')
                        if not is_video_topic:
                            print(f"🔤 使用latin-1解码: {payload_str[:100]}...")
                        processed_payload = json.loads(payload_str)
                    except Exception as e:
                        print(f"❌ 解码失败: {e}")
                        return
                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    return
            elif isinstance(payload, str):
                try:
                    if not is_video_topic:
                        print(f"🔤 原始payload字符串: {payload[:100]}...")
                    processed_payload = json.loads(payload)
                except json.JSONDecodeError as e:
                    print(f"❌ JSON解析失败: {e}")
                    return
            else:
                processed_payload = payload

            if processed_payload is None:
                print("❌ 无法处理payload")
                return

            if not is_video_topic and topic != mqtt_manager.STATUS_TOPIC:
                print(f"✅ 成功解析消息: {processed_payload}")

            if topic == mqtt_manager.VIDEO_TOPIC:
                handle_video_data(processed_payload)
            elif topic == mqtt_manager.FLASK_CONTROL_TOPIC:
                print("🎛️ 处理控制消息")
                handle_flask_control_message(processed_payload)
            elif topic == "face_collection":
                print("📸 处理人脸采集消息")
                handle_face_collection_message(processed_payload)
            elif topic == mqtt_manager.STATUS_TOPIC:
                handle_openmv_status_message(processed_payload)
            else:
                print(f"⚠️ 未知主题: {topic}")

    except Exception as e:
        logger.error(f"❌ 处理MQTT消息错误: {e}")
        import traceback
        traceback.print_exc()


def handle_openmv_status_message(data: Dict):
    """处理OpenMV状态消息"""
    try:
        frames_sent = data.get('frames_sent', 0)
        camera_active = data.get('camera_active', False)
        recognition_active = data.get('recognition_active', False)
        client_id = data.get('client_id', 'unknown')
        system_state = data.get('system_state', 0)

        if frames_sent % 100 == 0:
            print(f"📊 OpenMV状态更新: {client_id}, 帧数: {frames_sent}, "
                  f"摄像头: {'活动' if camera_active else '停止'}, "
                  f"识别: {'开启' if recognition_active else '关闭'}, "
                  f"系统状态: {system_state}")

    except Exception as e:
        logger.error(f"处理OpenMV状态消息错误: {e}")


def generate_black_frame() -> bytes:
    """生成黑色帧"""
    # 生成较小的黑色帧
    img = Image.new('RGB', (320, 240), color='black')
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=80)
    return img_byte_arr.getvalue()


def generate_optimized_frame(frame_data: bytes) -> bytes:
    """生成优化后的帧，用于快速传输"""
    try:
        if frame_data is None:
            return generate_black_frame()

        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return generate_black_frame()

        # 快速优化帧大小
        frame = optimize_frame_size(frame)

        # 使用优化的编码参数
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CONFIG['jpeg_quality']]
        _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)

        return jpeg_data.tobytes()

    except Exception as e:
        logger.error(f"生成优化帧失败: {e}")
        return generate_black_frame()


# 设置MQTT消息回调
mqtt_manager.set_message_callback(handle_mqtt_message)

# 初始更新
update_mqtt_mapping()


# Flask路由
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/flask_status')
def get_flask_status():
    """获取Flask识别状态"""
    status = "running" if state.recognition_enabled else "stopped"
    state.stats['recognition_status'] = status
    return jsonify({
        "recognition_enabled": state.recognition_enabled,
        "status": status
    })


@app.route('/face_management')
def face_management():
    face_data = face_db.get_all_faces()
    return render_template('face_management.html', faces=face_data)


@app.route('/attendance')
def attendance_page():
    """打卡系统页面"""
    return render_template('attendance.html')


@app.route('/video_feed')
def video_feed():
    """视频流生成器 - 优化版本"""

    def generate():
        last_frame_time = 0
        frame_count = 0
        last_sent_frame = None
        last_sent_time = 0

        print("🎬 开始视频流传输 (优化版本)")

        while True:
            process_face_collection()

            with state.frame_lock:
                if state.current_frame:
                    current_frame = state.current_frame
                else:
                    current_frame = None

            if current_frame is not None:
                try:
                    current_time = time.time()

                    # 检查是否需要跳过帧以维持帧率
                    time_since_last = current_time - last_frame_time
                    if time_since_last < CONFIG['min_frame_interval']:
                        continue

                    # 使用帧缓存减少重复处理
                    if (current_time - state.last_cache_time < CONFIG['frame_cache_time'] and
                            state.frame_cache is not None and
                            not state.face_collection_active and
                            not state.recognition_enabled):
                        processed_frame = state.frame_cache
                    else:
                        if state.face_collection_active:
                            processed_frame = process_frame_with_faces(current_frame)
                        elif state.recognition_enabled and frame_count % 2 == 0:  # 改为每2帧处理一次
                            processed_frame = process_frame_for_display(current_frame)
                        else:
                            # 如果没有识别或采集，使用优化帧
                            processed_frame = generate_optimized_frame(current_frame)

                        # 缓存处理后的帧
                        if not state.face_collection_active:
                            state.frame_cache = processed_frame
                            state.last_cache_time = current_time

                    # 检查是否与上一帧相同
                    if processed_frame != last_sent_frame or (current_time - last_sent_time) > 0.5:
                        yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + processed_frame + b'\r\n')
                        last_sent_frame = processed_frame
                        last_sent_time = current_time

                    last_frame_time = current_time
                    frame_count += 1

                    # 更新视频流帧率统计
                    if frame_count % 10 == 0:
                        state.stats['video_feed_fps'] = int(10 / (current_time - (last_frame_time - time_since_last)))

                except Exception as e:
                    logger.error(f"处理帧失败: {e}")
                    if current_frame:
                        yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + current_frame + b'\r\n')
            else:
                current_time = time.time()
                if last_frame_time == 0 or current_time - last_frame_time > 1.0:
                    black_frame = generate_black_frame()
                    yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + black_frame + b'\r\n')
                    last_frame_time = current_time

            time.sleep(CONFIG['video_feed_sleep'])  # 使用配置的休眠时间

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/refresh_stream')
def refresh_stream():
    """刷新视频流"""
    # 清空帧缓存
    state.frame_cache = None
    return jsonify({"status": "success", "message": "视频流已刷新"})


@app.route('/api/face_recognition/<action>')
def toggle_face_recognition(action):
    global state
    if action == 'start':
        state.recognition_enabled = True
        state.frame_skip_counter = 0
        state.stats['recognition_status'] = 'running'
        start_background_processing()
        print("🟢 人脸识别已开启 (由Web界面触发)")
        print("🔧 后台处理线程已激活")
        return jsonify({"status": "success", "message": "人脸识别已开启"})
    elif action == 'stop':
        state.recognition_enabled = False
        state.stats['recognition_status'] = 'stopped'
        stop_background_processing()
        print("🔴 人脸识别已关闭 (由Web界面触发)")
        return jsonify({"status": "success", "message": "人脸识别已关闭"})
    return jsonify({"status": "error", "message": "无效操作"})


@app.route('/api/test_mapping')
def test_mapping():
    """测试映射API"""
    try:
        face_mapping = face_db.get_name_id_mapping()
        mqtt_mapping = {}
        if hasattr(mqtt_manager, 'name_to_id_map'):
            mqtt_mapping = mqtt_manager.name_to_id_map

        is_consistent = face_mapping == mqtt_mapping

        return jsonify({
            'face_db_mapping': face_mapping,
            'mqtt_manager_mapping': mqtt_mapping,
            'is_consistent': is_consistent,
            'face_db_count': len(face_mapping),
            'mqtt_manager_count': len(mqtt_mapping)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_face', methods=['POST'])
def add_face():
    try:
        data = request.get_json()
        person_name = data.get('name')
        person_id = data.get('id', '').strip()

        if not person_name:
            return jsonify({"status": "error", "message": "请输入姓名"})

        if not person_id:
            existing_faces = face_db.get_all_faces()
            for face in existing_faces:
                if face['name'] == person_name:
                    return jsonify({"status": "error", "message": "该姓名已存在，请使用其他姓名"})

            try:
                _, auto_id = face_db.generate_auto_name_and_id()
                person_id = auto_id
                print(f"🆔 为 {person_name} 自动分配ID: {person_id}")
            except Exception as e:
                logger.error(f"自动分配ID失败: {e}")
                person_id = "001"
                print(f"🆔 为 {person_name} 使用默认ID: {person_id}")

        if len(person_id) != 3 or not person_id.isdigit():
            return jsonify({"status": "error", "message": "ID必须是3位数字"})

        existing_faces = face_db.get_all_faces()
        for face in existing_faces:
            if face['id'] == person_id:
                return jsonify({"status": "error", "message": f"ID {person_id} 已被使用，请使用其他ID"})

        success, message = start_face_collection(person_name, person_id)
        return jsonify({"status": "success" if success else "error", "message": message})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/cancel_collection', methods=['POST'])
def cancel_collection():
    """取消人脸采集 - API接口"""
    global state

    try:
        # 检查是否有采集活动
        if not state.face_collection_active:
            return jsonify({
                "status": "error",
                "message": "当前没有进行中的人脸采集"
            })

        # 执行取消操作
        success = cancel_collection_internal()

        if success:
            return jsonify({
                "status": "success",
                "message": "人脸采集已成功取消",
                "collection_status": "cancelled"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "取消采集失败，请重试"
            })

    except Exception as e:
        logger.error(f"取消采集API错误: {e}")
        return jsonify({
            "status": "error",
            "message": f"取消采集时发生错误: {str(e)}"
        })


@app.route('/api/delete_face/<person_name>')
def delete_face(person_name):
    """删除人脸数据"""
    try:
        success, message = face_db.delete_face(person_name)
        if success:
            update_mqtt_mapping()
            print(f"🗑️ 已删除人脸数据: {person_name}")
        return jsonify({"status": "success" if success else "error", "message": message})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/rename_face', methods=['POST'])
def rename_face():
    """重命名人脸"""
    try:
        data = request.get_json()
        old_name = data.get('old_name')
        new_name = data.get('new_name')

        if not old_name or not new_name:
            return jsonify({"status": "error", "message": "原名称和新名称不能为空"})

        success, message = face_db.rename_face(old_name, new_name)
        if success:
            update_mqtt_mapping()
            print(f"✏️ 人脸重命名: {old_name} -> {new_name}")
        return jsonify({"status": "success" if success else "error", "message": message})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/reload_faces')
def reload_faces():
    """重新加载人脸数据"""
    try:
        face_db.load_known_faces()
        update_mqtt_mapping()
        print("🔄 人脸数据已重新加载")
        return jsonify({"status": "success", "message": "人脸数据已重新加载"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/debug_faces')
def debug_faces():
    """调试人脸数据"""
    face_data = face_db.get_all_faces()
    debug_info = {
        'known_faces_count': len(face_db.known_face_names),
        'known_face_names': list(set(face_db.known_face_names)),
        'total_encodings': len(face_db.known_face_encodings),
        'face_data': face_data
    }
    return jsonify(debug_info)


@app.route('/api/collection_status')
def get_collection_status():
    """获取人脸采集状态"""
    return jsonify(state.face_collection_state)


@app.route('/api/send_recognition_result')
def send_recognition_result():
    """手动发送当前的识别结果"""
    try:
        if mqtt_manager.is_connected and state.stats['last_recognized_names']:
            mqtt_manager.send_recognition_result(state.stats['last_recognized_names'])
            print(f"📤 手动发送识别结果: {state.stats['last_recognized_names']}")
            return jsonify({"status": "success", "message": f"已发送识别结果: {state.stats['last_recognized_names']}"})
        else:
            return jsonify({"status": "error", "message": "没有识别到人脸或MQTT未连接"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/stats')
def get_stats():
    """获取系统统计数据"""
    try:
        state.stats['clients'] = state.connected_clients
        state.stats['recognition_enabled'] = state.recognition_enabled
        state.stats['known_faces'] = len(face_db.get_all_faces())
        state.stats['mqtt_connected'] = mqtt_manager.is_connected
        state.stats['face_collection_active'] = state.face_collection_state['active']
        state.stats[
            'collection_progress'] = f"{state.face_collection_state['images_collected']}/{state.face_collection_state['total_images']}"
        state.stats['loaded_faces'] = len(face_db.known_face_names)
        state.stats['attendance_system_enabled'] = state.attendance_system_enabled
        state.stats['background_processing'] = state.background_processing
        state.stats['recognition_status'] = "running" if state.recognition_enabled else "stopped"
        state.stats['video_feed_fps'] = state.stats.get('video_feed_fps', 0)

        current_time = time.time()
        if hasattr(get_stats, 'last_calc_time'):
            time_diff = current_time - get_stats.last_calc_time
            if time_diff > 0:
                frames_diff = state.stats['frames_received'] - get_stats.last_frame_count
                state.stats['fps'] = round(frames_diff / time_diff, 1)
            get_stats.last_calc_time = current_time
            get_stats.last_frame_count = state.stats['frames_received']
        else:
            get_stats.last_calc_time = current_time
            get_stats.last_frame_count = state.stats['frames_received']
            state.stats['fps'] = 0

        required_fields = ['clients', 'frames_received', 'fps', 'latency', 'known_faces',
                           'recognition_enabled', 'mqtt_connected', 'face_collection_active',
                           'collection_progress', 'loaded_faces', 'processing_time', 'frame_skip_rate',
                           'recognition_status', 'current_recognitions', 'background_processing',
                           'last_video_print_time', 'video_feed_fps', 'frame_size']

        for field in required_fields:
            if field not in state.stats:
                if field == 'current_recognitions':
                    state.stats[field] = []
                elif field == 'background_processing':
                    state.stats[field] = False
                elif field == 'last_video_print_time':
                    state.stats[field] = 0
                elif field == 'video_feed_fps':
                    state.stats[field] = 0
                elif field == 'frame_size':
                    state.stats[field] = 'N/A'
                else:
                    state.stats[field] = 0

        return jsonify(state.stats)

    except Exception as e:
        logger.error(f"获取统计信息错误: {e}")
        default_stats = {
            'clients': state.connected_clients,
            'frames_received': 0,
            'fps': 0,
            'latency': 0,
            'known_faces': 0,
            'recognition_enabled': state.recognition_enabled,
            'mqtt_connected': mqtt_manager.is_connected,
            'face_collection_active': state.face_collection_state['active'],
            'collection_progress': f"{state.face_collection_state['images_collected']}/{state.face_collection_state['total_images']}",
            'loaded_faces': 0,
            'processing_time': 0,
            'frame_skip_rate': 0,
            'attendance_system_enabled': state.attendance_system_enabled,
            'recognition_status': "stopped",
            'current_recognitions': [],
            'background_processing': False,
            'last_video_print_time': 0,
            'video_feed_fps': 0,
            'frame_size': 'N/A'
        }
        return jsonify(default_stats)


@app.before_request
def before_request():
    state.connected_clients += 1


@app.teardown_request
def teardown_request(exception=None):
    state.connected_clients -= 1


@app.route('/api/update_mqtt_mapping')
def api_update_mqtt_mapping():
    """手动更新MQTT映射的API接口"""
    try:
        if update_mqtt_mapping():
            print("🔄 MQTT映射已更新")
            return jsonify({'status': 'success', 'message': 'MQTT映射更新成功'})
        else:
            return jsonify({'status': 'error', 'message': 'MQTT映射更新失败'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'MQTT映射更新异常: {str(e)}'})


@app.route('/api/search_faces', methods=['POST'])
def api_search_faces():
    """搜索人脸数据"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()

        if not query:
            faces = face_db.get_all_faces()
        else:
            faces = face_db.search_faces(query)

        return jsonify({
            'status': 'success',
            'faces': faces,
            'count': len(faces)
        })

    except Exception as e:
        logger.error(f"搜索人脸失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'搜索失败: {str(e)}'
        }), 500


# 打卡系统路由
@app.route('/api/attendance/settings')
def get_attendance_settings():
    """获取打卡系统设置"""
    return jsonify({
        'status': 'success',
        'settings': {
            'enabled': state.attendance_system_enabled,
            'morning_start_time': state.attendance_settings['morning_start_time'],
            'morning_end_time': state.attendance_settings['morning_end_time'],
            'afternoon_start_time': state.attendance_settings['afternoon_start_time'],
            'afternoon_end_time': state.attendance_settings['afternoon_end_time']
        }
    })


@app.route('/api/attendance/toggle', methods=['POST'])
def toggle_attendance_system():
    """切换打卡系统开关"""
    global state
    try:
        data = request.get_json()
        enabled = data.get('enabled', False)

        state.attendance_system_enabled = enabled

        if enabled:
            state.recognition_enabled = True
            state.stats['recognition_status'] = 'running'
            start_background_processing()
            status = "开启"
            print(f"🟢 打卡系统已{status}，并自动开启人脸识别")
            print("🔧 后台处理线程已激活")
        else:
            # 修改：关闭打卡系统时也关闭人脸识别
            state.recognition_enabled = False
            state.stats['recognition_status'] = 'stopped'
            stop_background_processing()
            status = "关闭"
            print(f"🔴 打卡系统已{status}，并自动关闭人脸识别")
            print("⏹️ 后台处理线程已停止")

        return jsonify({
            'status': 'success',
            'message': f'打卡系统已{status}' + ('，并自动开启人脸识别' if enabled else '，并自动关闭人脸识别')
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'操作失败: {str(e)}'
        })


@app.route('/api/update_face_id', methods=['POST'])
def update_face_id():
    """更新人脸的ID"""
    try:
        data = request.get_json()
        person_name = data.get('person_name')
        old_id = data.get('old_id')
        new_id = data.get('new_id')

        if not person_name or not new_id:
            return jsonify({"status": "error", "message": "人员名称和新的ID不能为空"})

        if len(new_id) != 3 or not new_id.isdigit():
            return jsonify({"status": "error", "message": "ID必须是3位数字"})

        existing_faces = face_db.get_all_faces()
        for face in existing_faces:
            if face['id'] == new_id and face['name'] != person_name:
                return jsonify({"status": "error", "message": f"ID {new_id} 已被其他人使用"})

        print(f"🔄 开始更新ID: {person_name} -> {new_id}")

        success, message = face_db.update_face_id(person_name, new_id)

        if success:
            print("🔍 强制重新加载人脸数据...")
            face_db.load_known_faces()

            print("🔍 更新MQTT映射...")
            update_success = update_mqtt_mapping()

            print(f"✅ 更新人员ID: {person_name} -> {new_id}")
            print(f"🔄 MQTT映射更新: {'成功' if update_success else '失败'}")

            return jsonify({
                "status": "success",
                "message": message,
                "person_name": person_name,
                "old_id": old_id,
                "new_id": new_id
            })
        else:
            return jsonify({"status": "error", "message": message})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"更新过程中出现异常: {str(e)}"})


@app.route('/api/face_db_status')
def face_db_status():
    """检查人脸数据库状态"""
    try:
        face_count = len(face_db.metadata)
        encoding_count = len(face_db.known_face_encodings)
        name_count = len(face_db.known_face_names)
        mapping_count = len(face_db.name_to_id_map)

        return jsonify({
            "status": "success",
            "data": {
                "face_count": face_count,
                "encoding_count": encoding_count,
                "name_count": name_count,
                "mapping_count": mapping_count,
                "metadata_keys": list(face_db.metadata.keys())[:10],
                "known_names": face_db.known_face_names[:10]
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/attendance/update_time', methods=['POST'])
def update_attendance_time():
    """更新打卡时间设置"""
    try:
        data = request.get_json()
        time_type = data.get('time_type')
        time_value = data.get('time_value')

        time_mapping = {
            'morning_start': 'morning_start_time',
            'morning_end': 'morning_end_time',
            'afternoon_start': 'afternoon_start_time',
            'afternoon_end': 'afternoon_end_time'
        }

        if time_type in time_mapping and time_value:
            key = time_mapping[time_type]
            state.attendance_settings[key] = time_value
            print(f"⏰ 更新{time_type}时间为: {time_value}")
            return jsonify({
                'status': 'success',
                'message': '时间设置已更新'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '无效的参数'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'更新失败: {str(e)}'
        })


@app.route('/api/attendance/update_status', methods=['POST'])
def update_attendance_status_api():
    """更新打卡记录状态"""
    try:
        data = request.get_json()
        person_name = data.get('name')
        date = data.get('date')
        new_status = data.get('status')

        if not all([person_name, date, new_status]):
            return jsonify({
                'status': 'error',
                'message': '姓名、日期和状态不能为空'
            })

        target_record = None
        for record in attendance_manager.records:
            if record.get('name') == person_name and record.get('date') == date:
                target_record = record
                break

        if not target_record:
            return jsonify({
                'status': 'error',
                'message': f'未找到 {person_name} 在 {date} 的记录'
            })

        old_status = target_record.get('status', '未知')
        target_record['status'] = new_status
        target_record['auto_status'] = False

        save_success = attendance_manager.save_data()

        if save_success:
            print(f"✏️ 更新打卡状态: {person_name} {date} {old_status} -> {new_status}")
            return jsonify({
                'status': 'success',
                'message': f'成功更新 {person_name} 的状态为 {new_status}',
                'old_status': old_status,
                'new_status': new_status,
                'record': target_record
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '数据保存失败'
            })

    except Exception as e:
        logger.error(f"❌ 更新状态失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'更新失败: {str(e)}'
        })


@app.route('/api/attendance/delete', methods=['POST'])
def delete_attendance_record():
    """删除打卡记录"""
    try:
        data = request.get_json()
        person_name = data.get('name')
        date = data.get('date')

        if not all([person_name, date]):
            return jsonify({
                'status': 'error',
                'message': '姓名和日期不能为空'
            })

        initial_count = len(attendance_manager.records)
        attendance_manager.records[:] = [record for record in attendance_manager.records
                                         if not (record.get('name') == person_name and record.get('date') == date)]

        deleted_count = initial_count - len(attendance_manager.records)

        if deleted_count > 0:
            save_success = attendance_manager.save_data()
            if save_success:
                print(f"🗑️ 删除打卡记录: {person_name} {date}")
                return jsonify({
                    'status': 'success',
                    'message': f'成功删除 {person_name} 在 {date} 的打卡记录'
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': '数据保存失败'
                })
        else:
            return jsonify({
                'status': 'error',
                'message': f'未找到 {person_name} 在 {date} 的记录'
            })

    except Exception as e:
        logger.error(f"❌ 删除记录失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'删除失败: {str(e)}'
        })


@app.route('/api/attendance/records')
def get_attendance_records():
    """获取打卡记录"""
    try:
        date_filter = request.args.get('date', '')

        if date_filter:
            records = attendance_manager.get_records_by_date(date_filter)
            today_stats = attendance_manager.get_today_stats(date_filter)
        else:
            records = attendance_manager.get_records_by_date()
            today_stats = attendance_manager.get_today_stats()

        return jsonify({
            'status': 'success',
            'records': records,
            'today_stats': today_stats,
            'date_filter': date_filter
        })
    except Exception as e:
        logger.error(f"获取打卡记录失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'获取记录失败: {str(e)}'
        })


@app.route('/api/attendance/status_records')
def get_status_records():
    """获取特定状态的打卡记录"""
    try:
        status = request.args.get('status', '')
        date = request.args.get('date', datetime.now().date().isoformat())

        if not status:
            return jsonify({
                'status': 'error',
                'message': '状态参数不能为空'
            })

        filtered_records = []
        for record in attendance_manager.records:
            if record.get('date') == date:
                if status == 'all' or record.get('status') == status:
                    filtered_records.append(record)

        return jsonify({
            'status': 'success',
            'records': filtered_records,
            'count': len(filtered_records),
            'date': date,
            'query_status': status
        })

    except Exception as e:
        logger.error(f"获取状态记录失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'获取记录失败: {str(e)}'
        })


@app.route('/api/trigger_face_collection', methods=['POST'])
def trigger_face_collection():
    """触发人脸采集"""
    try:
        person_name = "OpenMV_User"
        person_id = face_db.generate_auto_id()

        success, message = start_face_collection(person_name, person_id)

        return jsonify({
            "status": "success" if success else "error",
            "message": message,
            "person_name": person_name,
            "person_id": person_id
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"触发人脸采集失败: {str(e)}"
        })


@app.route('/api/attendance/export')
def export_attendance_excel():
    """导出打卡记录为Excel"""
    try:
        try:
            import pandas as pd
        except ImportError:
            return jsonify({
                'status': 'error',
                'message': '请安装pandas库: pip install pandas openpyxl'
            }), 500

        export_date = request.args.get('date', '')

        if export_date:
            records_to_export = attendance_manager.get_records_by_date(export_date)
            if not records_to_export:
                return jsonify({
                    'status': 'error',
                    'message': f'在 {export_date} 没有找到打卡记录'
                }), 400
        else:
            records_to_export = attendance_manager.records
            if not records_to_export:
                return jsonify({
                    'status': 'error',
                    'message': '没有打卡记录可导出'
                }), 400

        print(f"📊 导出打卡记录: {export_date if export_date else '全部'}，共 {len(records_to_export)} 条记录")

        processed_records = []
        for record in records_to_export:
            processed_record = {
                '姓名': record.get('name', ''),
                '日期': record.get('date', ''),
                '上午上班': record.get('morning_check_in', ''),
                '上午下班': record.get('morning_check_out', ''),
                '下午上班': record.get('afternoon_check_in', ''),
                '下午下班': record.get('afternoon_check_out', ''),
                '状态': record.get('status', ''),
                '工作时长': record.get('work_duration', '')
            }
            processed_records.append(processed_record)

        df = pd.DataFrame(processed_records)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='打卡记录', index=False)

            worksheet = writer.sheets['打卡记录']
            worksheet.column_dimensions['A'].width = 15
            worksheet.column_dimensions['B'].width = 12
            worksheet.column_dimensions['C'].width = 12
            worksheet.column_dimensions['D'].width = 12
            worksheet.column_dimensions['E'].width = 12
            worksheet.column_dimensions['F'].width = 12
            worksheet.column_dimensions['G'].width = 10
            worksheet.column_dimensions['H'].width = 15

        output.seek(0)
        file_data = output.getvalue()

        if export_date:
            filename = f'attendance_records_{export_date}.xlsx'
        else:
            today = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'attendance_records_{today}.xlsx'

        from flask import make_response
        response = make_response(file_data)
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'

        return response

    except Exception as e:
        logger.error(f"导出Excel失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'导出失败: {str(e)}'
        }), 500


# 在应用启动时加载打卡数据
attendance_manager.load_data()


def get_local_ip() -> str:
    """获取本机IP地址"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def initialize_app():
    """应用初始化函数"""
    print("🚀 应用启动，初始化后台处理线程")
    print("🔄 初始化MQTT映射...")
    update_mqtt_mapping()

    if state.recognition_enabled:
        start_background_processing()


import atexit


@atexit.register
def cleanup():
    """应用关闭时执行"""
    print("🛑 应用关闭，停止后台处理线程")
    stop_background_processing()


if __name__ == '__main__':
    print("=" * 50)
    print("🚀 启动基于face_recognition的人脸识别服务器 (优化版本)")
    print("=" * 50)
    print(f"📊 视频流优化配置:")
    print(f"   - 显示缩放因子: {CONFIG['display_scale_factor']}")
    print(f"   - JPEG质量: {CONFIG['jpeg_quality']}%")
    print(f"   - 视频流休眠: {CONFIG['video_feed_sleep']}秒")
    print(f"   - 最大显示尺寸: {CONFIG['max_display_width']}x{CONFIG['max_display_height']}")
    print("=" * 50)

    initialize_app()

    if mqtt_manager.connect():
        local_ip = get_local_ip()
        print(f"🌐 服务器访问地址:")
        print(f"   http://localhost:5000")
        print(f"   http://{local_ip}:5000")
        print("=" * 50)

        from werkzeug.serving import WSGIRequestHandler

        WSGIRequestHandler.protocol_version = "HTTP/1.1"

        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    else:
        logger.error("❌ MQTT连接失败，服务器无法启动")
