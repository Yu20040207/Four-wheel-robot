import warnings

warnings.filterwarnings("ignore", category=UserWarning)

import os
import sys


def _configure_console_encoding():
    """Windows 默认 GBK 控制台无法输出 emoji，会导致 PyInstaller 版闪退。"""
    if sys.platform != 'win32':
        return
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
                continue
            except Exception:
                pass
        buf = getattr(stream, 'buffer', None)
        if buf is not None:
            import io
            wrapper = io.TextIOWrapper(buf, encoding='utf-8', errors='replace', line_buffering=True)
            setattr(sys, name, wrapper)


_configure_console_encoding()

from flask import Flask, render_template, Response, jsonify, request, make_response, session
import json
import time
import threading
import cv2
import numpy as np
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
import face_recognition
import logging
from typing import List, Dict, Any, Optional, Tuple
import atexit
import threading
import webbrowser

# 固定从 app.py 所在目录加载模板/静态文件，避免 PyCharm 工作目录不同导致读到旧页面
_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def get_resource_dir() -> str:
    """打包后从 PyInstaller 解压目录读取 templates/static；开发时用源码目录"""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', _APP_DIR)
    return _APP_DIR


app = Flask(
    __name__,
    template_folder=os.path.join(get_resource_dir(), 'templates'),
    static_folder=os.path.join(get_resource_dir(), 'static'),
)


@app.after_request
def disable_static_cache(response):
    """避免浏览器长期使用旧的 main.js / CSS"""
    if request.path.startswith('/static/') or request.path in ('/', '/index'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/favicon.ico')
def favicon():
    return '', 204

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
# 导入人体跟踪模块
from human_tracker import get_human_tracker
from garbage_tracker import get_garbage_tracker
from auth import init_auth, check_request_auth, require_robot_for_control, is_robot_control_api
from flask_login import current_user

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
    'face_track_detect_interval': 0.35,  # Flask 人脸检测最短间隔（秒）
    'face_track_head_interval': 0.3,  # 舵机指令发送间隔（秒）
    # 新增人体跟踪配置
    'human_detection_interval': 5,  # 人体检测间隔（帧数）
    'min_human_confidence': 0.5,  # 人体检测最小置信度
    'tracking_iou_threshold': 0.3,  # 跟踪IOU阈值
    'max_tracking_distance': 150,  # 最大跟踪距离（像素）
    'control_interval': 0.5,  # 控制指令发送间隔（秒）
    # 垃圾捡取配置（调试时可修改）
    'garbage_model_path': 'garbage.pt',
    'garbage_confidence_threshold': 0.45,
    'garbage_center_threshold': 0.12,
    'garbage_center_deadzone': 0.055,
    'garbage_turn_release': 0.11,
    'garbage_forward_abort': 0.15,
    'garbage_large_offset': 0.08,
    'garbage_edge_offset': 0.22,
    'garbage_offset_snap': 0.12,
    'garbage_align_gate': 0.09,
    'garbage_offset_smooth': 0.16,
    'garbage_control_cx_smooth': 0.15,
    'garbage_vel_output_smooth': 0.32,
    'garbage_forward_y_scale': 0.45,
    'garbage_turn_min_cmd': 0.028,
    'garbage_forward_min_cmd': 0.012,
    'garbage_turn_settle_frames': 3,
    'garbage_turn_sign': 1,
    'garbage_vel_y_kp': 0.32,
    'garbage_vel_y_ki': 0.006,
    'garbage_vel_y_kd': 0.05,
    'garbage_vel_y_max': 0.10,
    'garbage_vel_y_integral_limit': 0.08,
    'garbage_vel_x_kp': 1.2,
    'garbage_vel_x_ki': 0.035,
    'garbage_vel_x_kd': 0.04,
    'garbage_vel_x_max': 0.26,
    'garbage_vel_x_integral_limit': 0.18,
    'garbage_min_area_ratio': 0.04,
    'garbage_max_area_ratio': 0.30,
    'garbage_aligned_area_ratio': 0.14,
    'garbage_control_interval': 0.18,
    'garbage_detection_interval': 2,
    'garbage_aligned_frames': 4,
    'garbage_target_distance_cm': 25,  # 超声波停车距离(cm)
    # 多目标决策权重（见 garbage_tracker.py）
    'garbage_target_center_weight': 0.45,
    'garbage_target_conf_weight': 0.30,
    'garbage_target_area_weight': 0.25,
    'garbage_target_lock_iou': 0.25,
    'garbage_target_lock_bonus': 0.35,
    'garbage_target_lock_lost_max': 8,
}


def get_app_base_dir() -> str:
    """项目根目录（兼容开发环境与 PyInstaller 打包 exe）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return _APP_DIR


RUBBISH_PHOTO_DIR = os.path.join(get_app_base_dir(), 'rubbish_photo')


def parse_robot_id_from_video_topic(topic: str) -> Optional[str]:
    """从 robots/{robot_id}/video/stream 解析 robot_id"""
    prefix = 'robots/'
    suffix = '/video/stream'
    if topic.startswith(prefix) and topic.endswith(suffix):
        robot_id = topic[len(prefix):-len(suffix)]
        return robot_id or None
    return None


def parse_robot_id_from_topic(topic: str) -> Optional[str]:
    """从 robots/{robot_id}/... 解析 robot_id"""
    prefix = 'robots/'
    if not topic.startswith(prefix):
        return None
    parts = topic.split('/')
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    return None


def record_robot_presence_from_payload(
    robot_id: Optional[str],
    payload: Any,
    source: str = 'device',
) -> None:
    """根据 MQTT 状态/心跳消息更新机器人在线状态（不依赖视频流）"""
    from robot_context import record_robot_heartbeat

    if isinstance(payload, dict):
        rid = payload.get('robot_id') or robot_id
        state = payload.get('state') or payload.get('status') or 'online'
        if isinstance(state, (int, float)):
            state = str(int(state))
        else:
            state = str(state)
    else:
        rid = robot_id
        state = 'online'

    if rid:
        record_robot_heartbeat(str(rid), source=source, state=state)


def store_robot_frame(robot_id: Optional[str], jpeg_bytes: bytes, latency_ms: Optional[int] = None) -> None:
    """按 robot_id 存储视频帧；无 robot_id 时写入 legacy 全局帧"""
    from robot_context import record_robot_frame

    with state.frame_lock:
        if robot_id:
            state.robot_frames[robot_id] = jpeg_bytes
            state.robot_raw_frames[robot_id] = jpeg_bytes
            state.robot_frame_times[robot_id] = time.time()
            record_robot_frame(robot_id, latency_ms)
        state.current_frame = jpeg_bytes
        state.last_raw_frame = jpeg_bytes


def get_robot_frame(robot_id: Optional[str]) -> Optional[bytes]:
    if not robot_id:
        return None
    with state.frame_lock:
        frame = state.robot_frames.get(robot_id)
        if frame is not None:
            return frame
        # OpenMV robot_id 与 Web 所选不一致时，仍显示最近收到的视频帧
        if state.current_frame is not None:
            return state.current_frame
        return None


def get_robot_raw_frame(robot_id: Optional[str]) -> Optional[bytes]:
    if not robot_id:
        return None
    with state.frame_lock:
        return state.robot_raw_frames.get(robot_id)


# 全局状态管理类
class GlobalState:
    def __init__(self):
        self.current_frame = None
        self.last_raw_frame = None  # 新增：原始帧缓存
        self.robot_frames: Dict[str, bytes] = {}
        self.robot_raw_frames: Dict[str, bytes] = {}
        self.robot_frame_times: Dict[str, float] = {}
        self.openmv_stats_by_robot: Dict[str, Dict] = {}
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

        # 新增：人体跟踪相关状态
        self.human_tracking_enabled = False
        self.human_tracking_active = False
        self.last_human_detection_time = 0
        self.human_detection_results = []
        self.human_tracking_results = []
        self.current_human_target = None
        self.human_tracking_stats = {
            'detected_count': 0,
            'tracking_count': 0,
            'fps': 0,
            'detection_time': 0,
            'total_humans_detected': 0,
            'last_control_command': None,
            'last_control_time': 0
        }

        # 垃圾捡取相关状态
        self.garbage_tracking_enabled = False
        self.garbage_tracking_active = False
        self.garbage_detection_results = []
        self.current_garbage_target = None
        self.garbage_tracking_stats = {
            'detected_count': 0,
            'tracking_count': 0,
            'fps': 0,
            'detection_time': 0,
            'last_control_command': None,
            'last_control_time': 0,
            'pickup_in_progress': False,
            'model_loaded': False,
        }

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
            # 新增人体跟踪统计
            'human_tracking_enabled': False,
            'human_tracking_active': False,
            'humans_detected': 0,
            'humans_tracking': 0,
            'human_detection_fps': 0,
            'current_human_target': None,
            'last_control_command': None,
            # 垃圾捡取统计
            'garbage_tracking_enabled': False,
            'garbage_tracking_active': False,
            'garbage_detected': 0,
            'garbage_pickup_in_progress': False,
        }

        self.face_collection_state = {
            'active': False, 'person_name': None, 'images_collected': 0,
            'total_images': CONFIG['face_collection_total'], 'last_capture_time': 0,
            'status_message': '',
            'last_status_send_time': 0,
            'completion_sent': False
        }
        self.last_face_track_head_time = 0.0
        self.face_track_cache = {'jpeg': None, 'track_info': None, 'last_detect_time': 0.0}
        self.face_tracking_command_time = 0.0
        self.face_tracking_command_active = None
        self.face_tracking_desired: Dict[str, bool] = {}
        self.last_face_track_stop_retry: Dict[str, float] = {}


# 初始化全局状态和模块
state = GlobalState()
face_db = FaceDatabase()
mqtt_manager = MQTTManager()
auth_database = init_auth(app, get_app_base_dir())

# 初始化人体跟踪器
human_tracker = get_human_tracker(CONFIG)

# 初始化垃圾跟踪器
garbage_tracker = get_garbage_tracker(CONFIG)

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


def process_frame_with_humans(frame_data: bytes, robot_id: Optional[str] = None) -> bytes:
    """处理帧中的人体检测和跟踪"""
    global state, human_tracker

    try:
        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)

        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            print("⚠️ 无法解码帧数据")
            return frame_data

        if not robot_id or not rt.get('human_tracking_enabled'):
            return frame_data

        frame_count = rt.get('frames_received', 0)
        if frame_count % 30 == 0:
            print(
                f"🎯 帧 {frame_count} robot={robot_id}: "
                f"人体跟踪 启用={rt.get('human_tracking_enabled')} "
                f"活跃={rt.get('human_tracking_active')}"
            )

        processed_frame, tracking_info = human_tracker.process_frame(frame, robot_id=robot_id)

        rt['humans_detected'] = len(tracking_info.get('detections', []))
        rt['humans_tracking'] = len(tracking_info.get('tracked_persons', []))
        rt['current_human_target'] = tracking_info.get('current_target')
        if tracking_info.get('stats', {}).get('last_control_command'):
            rt['last_control_command'] = tracking_info['stats']['last_control_command']

        # 使用处理后的帧
        if processed_frame is not None and processed_frame is not frame:
            frame = processed_frame
            # print("🎨 使用处理后的帧（包含人体检测框）")
        else:
            # print("⚠️ 使用原始帧，处理后的帧无变化或为None")
            pass

        # 优化帧大小
        frame = optimize_frame_size(frame)

        # 编码为JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CONFIG['jpeg_quality']]
        _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)

        # 帧大小调试
        if frame_count % 60 == 0:  # 每60帧打印一次
            print(f"📦 编码后帧大小: {jpeg_data.size} 字节")

        return jpeg_data.tobytes()

    except Exception as e:
        print(f"❌ 处理人体跟踪帧错误: {e}")
        import traceback
        traceback.print_exc()
        return frame_data


def process_frame_with_garbage(frame_data: bytes, robot_id: Optional[str] = None) -> bytes:
    """处理帧中的垃圾检测和跟踪"""
    global state, garbage_tracker

    try:
        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)

        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return frame_data

        if not robot_id or not rt.get('garbage_tracking_enabled'):
            return frame_data

        processed_frame, tracking_info = garbage_tracker.process_frame(frame, robot_id=robot_id)

        rt['garbage_detected'] = len(tracking_info.get('detections', []))
        rt['current_garbage_target'] = tracking_info.get('current_target')
        if tracking_info.get('stats', {}).get('last_control_command'):
            rt['last_control_command'] = tracking_info['stats']['last_control_command']
        rt['garbage_pickup_in_progress'] = bool(garbage_tracker.pickup_in_progress)

        if processed_frame is not None:
            frame = processed_frame

        frame = optimize_frame_size(frame)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CONFIG['jpeg_quality']]
        _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)
        return jpeg_data.tobytes()
    except Exception as e:
        print(f"❌ 处理垃圾跟踪帧错误: {e}")
        return frame_data


_face_track_cascade = None


def _get_face_track_cascade():
    global _face_track_cascade
    if _face_track_cascade is None:
        path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        _face_track_cascade = cv2.CascadeClassifier(path)
    return _face_track_cascade


def get_face_tracking_desired(robot_id: Optional[str]) -> bool:
    if not robot_id:
        return False
    return bool(state.face_tracking_desired.get(str(robot_id), False))


def _set_face_tracking_stats(robot_id: str, active: bool) -> None:
    """记录 Web 端用户意图；仅由 API 修改，不被 OpenMV MQTT 覆盖"""
    rid = str(robot_id)
    state.face_tracking_desired[rid] = active
    state.stats['openmv_face_tracking_active'] = active
    entry = dict(state.openmv_stats_by_robot.get(rid, {}))
    entry['openmv_face_tracking_active'] = active
    if not active:
        entry['openmv_faces_detected'] = 0
    state.openmv_stats_by_robot[rid] = entry
    state.face_track_cache = {'jpeg': None, 'track_info': None, 'last_detect_time': 0.0}


def publish_face_tracking_head(track_info: Dict, robot_id: Optional[str] = None) -> None:
    """将 Flask 检测到的人脸中心发给 OpenMV，驱动头部舵机"""
    if not track_info or not mqtt_manager.is_connected:
        return
    now = time.time()
    if now - state.last_face_track_head_time < CONFIG['face_track_head_interval']:
        return
    state.last_face_track_head_time = now
    payload = {
        'cx': int(track_info['cx']),
        'cy': int(track_info['cy']),
        'fw': int(track_info['fw']),
        'fh': int(track_info['fh']),
    }
    mqtt_manager.publish_to_robot('cmd/face_tracking/head', payload, qos=0, robot_id=robot_id)


def process_frame_for_face_tracking(frame_data: bytes):
    """Web 端人脸跟踪画框（降采样检测以减轻 CPU 负担）"""
    try:
        cascade = _get_face_track_cascade()
        if cascade.empty():
            return frame_data, None

        nparr = np.frombuffer(frame_data, np.uint8)
        color = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if color is not None:
            gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
            draw_frame = color
        else:
            gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                return frame_data, None
            draw_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        detect_scale = 0.5
        small_gray = cv2.resize(gray, (0, 0), fx=detect_scale, fy=detect_scale)
        inv = 1.0 / detect_scale

        def run_detect(src):
            raw = cascade.detectMultiScale(
                src, scaleFactor=1.15, minNeighbors=3, minSize=(24, 24)
            )
            scaled = []
            for (x, y, w, h) in raw:
                scaled.append((
                    int(x * inv), int(y * inv),
                    int(w * inv), int(h * inv),
                ))
            return scaled

        faces = run_detect(small_gray)
        if len(faces) == 0:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            faces = run_detect(clahe.apply(small_gray))

        track_idx = -1
        max_area = 0
        track_info = None
        for i, (x, y, w, h) in enumerate(faces):
            area = w * h
            if area > max_area:
                max_area = area
                track_idx = i

        for i, (x, y, w, h) in enumerate(faces):
            if i == track_idx:
                cv2.rectangle(draw_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(
                    draw_frame, 'Track', (x, max(y - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1,
                )
                track_info = {
                    'cx': int(x + w // 2),
                    'cy': int(y + h // 2),
                    'fw': int(draw_frame.shape[1]),
                    'fh': int(draw_frame.shape[0]),
                    'x': int(x),
                    'y': int(y),
                    'w': int(w),
                    'h': int(h),
                }
            else:
                cv2.rectangle(draw_frame, (x, y), (x + w, y + h), (128, 128, 128), 1)

        _, jpeg_data = cv2.imencode('.jpg', draw_frame, [int(cv2.IMWRITE_JPEG_QUALITY), CONFIG['jpeg_quality']])
        return jpeg_data.tobytes(), track_info
    except Exception as e:
        logger.error(f"人脸跟踪画框错误: {e}")
        return frame_data, None


def draw_face_track_overlay(frame_data: bytes, track_info: Optional[Dict]) -> bytes:
    """在最新帧上快速绘制缓存的跟踪框（不做检测）"""
    if not track_info:
        return frame_data
    try:
        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                return frame_data
            frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        x = int(track_info.get('x', 0))
        y = int(track_info.get('y', 0))
        w = int(track_info.get('w', 0))
        h = int(track_info.get('h', 0))
        if w > 0 and h > 0:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                frame, 'Track', (x, max(y - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1,
            )
        _, jpeg_data = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), CONFIG['jpeg_quality']])
        return jpeg_data.tobytes()
    except Exception:
        return frame_data


def apply_face_tracking_overlay(frame_data: bytes):
    """带缓存的人脸跟踪叠加，避免每帧都做 OpenCV 检测"""
    cache = state.face_track_cache
    now = time.time()
    last_detect = float(cache.get('last_detect_time') or 0.0)
    track_info = cache.get('track_info')

    if track_info and now - last_detect < CONFIG['face_track_detect_interval']:
        return draw_face_track_overlay(frame_data, track_info), track_info

    processed, track_info = process_frame_for_face_tracking(frame_data)
    state.face_track_cache = {
        'jpeg': processed,
        'track_info': track_info,
        'last_detect_time': now,
    }
    return processed, track_info


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


def handle_video_data(data: Dict, robot_id: Optional[str] = None):
    """处理接收到的视频数据 - 优化版本"""
    global state
    try:
        if 'robot_id' in data and data['robot_id']:
            robot_id = data['robot_id']

        if 'data' in data:
            hex_data = data['data']
            if isinstance(hex_data, bytes):
                hex_data = hex_data.decode('latin-1')
            jpeg_bytes = bytes.fromhex(hex_data)
            latency_ms = None
            if 'timestamp' in data:
                latency_ms = int((time.time() * 1000) - data['timestamp'])
            store_robot_frame(robot_id, jpeg_bytes, latency_ms=latency_ms)

            if not robot_id:
                state.stats['frames_received'] += 1
                state.stats['last_frame_time'] = time.time()
                state.frame_count += 1
                current_time = time.time()
                if current_time - state.last_fps_calc_time >= 1.0:
                    state.fps = state.frame_count
                    state.frame_count = 0
                    state.last_fps_calc_time = current_time
                    state.stats['fps'] = state.fps
                if latency_ms is not None:
                    state.stats['latency'] = latency_ms

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
            state.stats['recognition_enabled'] = True
            state.stats['recognition_status'] = 'running'
            start_background_processing()
            print("🔍 Flask人脸识别已开启 (由OpenMV触发)")
            print("🔧 后台处理线程已激活")

        elif command == 'stop_recognition' or command == 'recognition_off':
            state.recognition_enabled = False
            state.stats['recognition_enabled'] = False
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

        # 添加对9和A命令的处理（A代表10）
        elif command == '9':
            # 命令9：开启人体跟踪
            human_tracker.enable_tracking()
            state.human_tracking_enabled = True
            state.human_tracking_active = True
            state.stats['human_tracking_enabled'] = True
            state.stats['human_tracking_active'] = True
            print("🎯 人体跟踪已开启 (由OpenMV触发)")

        elif command == 'A':
            # 命令A（代表10）：关闭人体跟踪 - 确保完全停止
            print("🔴 收到关闭人体跟踪指令")

            # 1. 停止人体跟踪器
            try:
                human_tracker.disable_tracking()
                print("✅ 人体跟踪器已停止")
            except Exception as e:
                print(f"⚠️ 停止人体跟踪器失败: {e}")

            # 2. 重置状态
            state.human_tracking_enabled = False
            state.human_tracking_active = False
            state.stats['human_tracking_enabled'] = False
            state.stats['human_tracking_active'] = False
            state.current_human_target = None
            state.human_detection_results = []
            state.human_tracking_results = []

            # 3. 重置统计信息
            state.human_tracking_stats = {
                'detected_count': 0,
                'tracking_count': 0,
                'fps': 0,
                'detection_time': 0,
                'total_humans_detected': 0,
                'last_control_command': None,
                'last_control_time': 0
            }

            # 4. 发送最后的停止指令到OpenMV
            try:
                if hasattr(mqtt_manager, 'client') and mqtt_manager.is_connected:
                    # 发送停止指令到camera_control主题
                    mqtt_manager.client.publish("camera_control", "stop", qos=1)
                    print("📤 已发送最后的停止指令到OpenMV")
            except Exception as e:
                print(f"⚠️ 发送停止指令失败: {e}")

            print("⏹️ 人体跟踪已完全关闭 (由OpenMV触发)")

        elif command == 'B':
            # 命令B：开启垃圾捡取跟踪（避障模式下配合使用）
            garbage_tracker.enable_tracking()
            state.garbage_tracking_enabled = True
            state.garbage_tracking_active = True
            print("🗑️ 垃圾捡取跟踪已开启 (由OpenMV触发)")

        elif command == 'C':
            # 命令C：关闭垃圾捡取跟踪
            garbage_tracker.disable_tracking()
            state.garbage_tracking_enabled = False
            state.garbage_tracking_active = False
            state.current_garbage_target = None
            state.garbage_detection_results = []
            print("🗑️ 垃圾捡取跟踪已关闭 (由OpenMV触发)")

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


def handle_human_tracking_control(payload):
    """处理人体跟踪控制消息"""
    global state, human_tracker

    try:
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')

        if isinstance(payload, str):
            payload = json.loads(payload)

        command = payload.get('command')

        if command == 'start_detection':
            human_tracker.enable_tracking()
            state.human_tracking_enabled = True
            state.human_tracking_active = False
            print("👤 人体检测已开启 (由MQTT触发)")

        elif command == 'start_tracking':
            human_tracker.start_tracking()
            state.human_tracking_enabled = True
            state.human_tracking_active = True
            print("🎯 人体跟踪已开启 (由MQTT触发)")

        elif command == 'stop_tracking':
            human_tracker.stop_tracking()
            state.human_tracking_active = False
            print("⏹️ 人体跟踪已停止 (由MQTT触发)")

        elif command == 'disable_tracking':
            human_tracker.disable_tracking()
            state.human_tracking_enabled = False
            state.human_tracking_active = False
            state.current_human_target = None
            state.human_detection_results = []
            state.human_tracking_results = []
            print("🔴 人体跟踪已禁用 (由MQTT触发)")

    except Exception as e:
        print(f"❌ 处理人体跟踪控制消息失败: {e}")


def handle_garbage_pickup_mode(payload):
    """处理来自 ESP32 的避障/垃圾模式开关"""
    global state, garbage_tracker

    try:
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')
        if isinstance(payload, str):
            data = json.loads(payload)
        else:
            data = payload

        enabled = data.get('enabled', False)
        target_distance = data.get('target_distance_cm')
        if target_distance is not None:
            garbage_tracker.target_pickup_distance_cm = int(target_distance)

        # Web/API 已在 control_garbage_pickup 里处理过，忽略回声避免重复 disable
        if data.get('source') == 'web':
            return

        if enabled:
            garbage_tracker.enable_tracking()
            state.garbage_tracking_enabled = True
            state.garbage_tracking_active = True
            print(f"🗑️ 垃圾跟踪已开启 (ESP32避障模式)，目标距离={garbage_tracker.target_pickup_distance_cm}cm")
        else:
            garbage_tracker.disable_tracking()
            state.garbage_tracking_enabled = False
            state.garbage_tracking_active = False
            print("🗑️ 垃圾跟踪已关闭 (ESP32避障模式关闭)")
    except Exception as e:
        print(f"❌ 处理垃圾模式消息失败: {e}")


def handle_garbage_pickup_status(payload):
    """处理 ESP32 捡垃圾流程状态回报"""
    global state, garbage_tracker

    try:
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')
        if isinstance(payload, str):
            data = json.loads(payload)
        else:
            data = payload

        phase = data.get('phase', '')
        if phase == 'complete':
            garbage_tracker.on_pickup_complete()
            state.garbage_tracking_stats['pickup_in_progress'] = False
            print("✅ ESP32 报告垃圾捡取完成")
        elif phase == 'failed':
            garbage_tracker.pickup_in_progress = False
            print(f"⚠️ ESP32 报告垃圾捡取失败: {data.get('message', '')}")
    except Exception as e:
        print(f"❌ 处理垃圾状态消息失败: {e}")


def handle_battery_status(payload):
    """处理 ESP32 上报的电池电压/电量"""
    from robot_context import update_robot_battery

    try:
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')
        if isinstance(payload, str):
            data = json.loads(payload)
        else:
            data = payload

        robot_id = data.get('robot_id')
        if not robot_id:
            return

        valid = bool(data.get('valid', False))
        voltage = data.get('voltage')
        percent = data.get('percent')
        level = str(data.get('level') or 'normal')

        if voltage is not None:
            voltage = float(voltage)
        if percent is not None:
            percent = int(percent)

        update_robot_battery(robot_id, voltage, percent, level=level, valid=valid)
        record_robot_presence_from_payload(robot_id, data, source='esp32')
    except Exception as e:
        print(f"❌ 处理电池状态消息失败: {e}")


def handle_mqtt_message(data: Dict):
    """处理MQTT消息"""
    try:
        if 'topic' in data and 'payload' in data:
            topic = data['topic']
            payload = data['payload']

            current_time = time.time()
            robot_id_from_topic = parse_robot_id_from_video_topic(topic)
            status_robot_id = (
                parse_robot_id_from_topic(topic)
                if topic.startswith('robots/') and '/status/' in topic else None
            )
            is_video_topic = (
                topic == mqtt_manager.VIDEO_TOPIC or robot_id_from_topic is not None
            )

            if not is_video_topic:
                print(f"📨 Flask收到MQTT消息: 主题={topic}")
            elif current_time - state.stats['last_video_print_time'] > 1.0:
                state.stats['last_video_print_time'] = current_time

            processed_payload = None

            if isinstance(payload, bytes):
                if is_video_topic and payload[:2] == b'\xff\xd8':
                    store_robot_frame(robot_id_from_topic, payload)
                    if not robot_id_from_topic:
                        state.stats['frames_received'] += 1
                        state.stats['last_frame_time'] = time.time()
                    return
                try:
                    payload_str = payload.decode('utf-8')
                    processed_payload = json.loads(payload_str)
                except UnicodeDecodeError:
                    try:
                        payload_str = payload.decode('latin-1')
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

            if topic == mqtt_manager.VIDEO_TOPIC or robot_id_from_topic:
                handle_video_data(processed_payload, robot_id=robot_id_from_topic)
            elif status_robot_id and '/status/' in topic:
                source = 'openmv' if topic.endswith('/status/device') else 'esp32'
                record_robot_presence_from_payload(
                    status_robot_id, processed_payload, source=source
                )
                if topic.endswith('/status/garbage_pickup'):
                    handle_garbage_pickup_status(processed_payload)
                elif topic.endswith('/status/garbage_pickup/mode'):
                    handle_garbage_pickup_mode(processed_payload)
                elif topic.endswith('/status/battery'):
                    handle_battery_status(processed_payload)
            elif topic == mqtt_manager.FLASK_CONTROL_TOPIC:
                print("🎛️ 处理控制消息")
                handle_flask_control_message(processed_payload)
            elif topic == "face_collection":
                print("📸 处理人脸采集消息")
                handle_face_collection_message(processed_payload)
            elif topic == "human_tracking_control":
                print("🎯 处理人体跟踪控制消息")
                handle_human_tracking_control(payload)
            elif topic == mqtt_manager.GARBAGE_PICKUP_MODE_TOPIC:
                print("🗑️ 处理垃圾捡取模式消息")
                handle_garbage_pickup_mode(processed_payload if processed_payload else payload)
            elif topic == mqtt_manager.GARBAGE_PICKUP_STATUS_TOPIC:
                record_robot_presence_from_payload(
                    None, processed_payload if processed_payload else {}, source='esp32'
                )
                handle_garbage_pickup_status(processed_payload if processed_payload else payload)
            elif topic == mqtt_manager.STATUS_TOPIC:
                handle_openmv_status_message(processed_payload)
            else:
                print(f"⚠️ 未知主题: {topic}")

    except Exception as e:
        logger.error(f"❌ 处理MQTT消息错误: {e}")
        import traceback
        traceback.print_exc()


def handle_openmv_status_message(data: Dict):
    """处理OpenMV状态消息，并同步到 Web 可读的 stats 字段"""
    try:
        frames_sent = data.get('frames_sent', 0)
        camera_active = data.get('camera_active', False)
        recognition_active = data.get('recognition_active', False)
        client_id = data.get('client_id', 'unknown')
        system_state = data.get('system_state', 0)
        openmv_human_tracking = data.get('human_tracking_enabled')

        tracking_active = data.get('tracking_active')
        if tracking_active is None:
            tracking_active = int(system_state) >= 3

        robot_id = data.get('robot_id')
        if not robot_id and isinstance(client_id, str) and client_id.startswith('openmv_'):
            robot_id = client_id[len('openmv_'):]
        if robot_id:
            record_robot_presence_from_payload(robot_id, data, source='openmv')

        openmv_stats = {
            'openmv_frames_sent': frames_sent,
            'openmv_camera_active': bool(camera_active),
            'openmv_recognition_active': bool(recognition_active),
            'openmv_system_state': system_state,
            'openmv_device_tracking_active': bool(tracking_active),
            'head_pan_angle': float(data.get('pan_angle', 0)) if 'pan_angle' in data else None,
            'head_tilt_angle': float(data.get('tilt_angle', 0)) if 'tilt_angle' in data else None,
            'openmv_faces_detected': int(data.get('faces_detected', 0)),
        }
        if openmv_human_tracking is not None:
            openmv_stats['openmv_human_tracking_enabled'] = bool(openmv_human_tracking)

        if robot_id:
            rid = str(robot_id)
            prev = dict(state.openmv_stats_by_robot.get(rid, {}))
            prev.update(openmv_stats)
            prev['openmv_face_tracking_active'] = get_face_tracking_desired(rid)
            state.openmv_stats_by_robot[rid] = prev

            if not get_face_tracking_desired(rid) and tracking_active:
                last_retry = float(state.last_face_track_stop_retry.get(rid, 0.0))
                if time.time() - last_retry > 8.0:
                    state.last_face_track_stop_retry[rid] = time.time()
                    if _publish_camera_control("1"):
                        print(f"⏹️ Web 已关闭跟踪，补发关闭指令至 OpenMV (robot={rid})")

        state.stats.update(state.openmv_stats_by_robot.get(str(robot_id), openmv_stats) if robot_id else openmv_stats)
        if robot_id:
            state.stats['openmv_face_tracking_active'] = get_face_tracking_desired(str(robot_id))

        if frames_sent % 100 == 0:
            print(f"📊 OpenMV状态更新: {client_id}, 帧数: {frames_sent}, "
                  f"摄像头: {'活动' if camera_active else '停止'}, "
                  f"识别: {'开启' if recognition_active else '关闭'}, "
                  f"系统状态: {system_state}")

    except Exception as e:
        logger.error(f"处理OpenMV状态消息错误: {e}")


def build_stats_response(robot_id: Optional[str] = None) -> Dict:
    """构建可 JSON 序列化的系统状态（供 /api/stats 使用，按当前所选机器人隔离）"""
    from auth import get_selected_robot_id
    from robot_context import get_robot_runtime_copy, is_robot_online

    if robot_id is None:
        robot_id = get_selected_robot_id()

    rt = get_robot_runtime_copy(robot_id) if robot_id else {}
    robot_connected = is_robot_online(robot_id) if robot_id else False

    stats = dict(state.stats)
    if robot_id and robot_id in state.openmv_stats_by_robot:
        stats.update(state.openmv_stats_by_robot[robot_id])
    stats['clients'] = max(0, state.connected_clients)
    stats['recognition_enabled'] = bool(state.recognition_enabled)
    stats['known_faces'] = len(face_db.get_all_faces())
    stats['robot_connected'] = robot_connected
    stats['mqtt_connected'] = robot_connected
    stats['mqtt_broker_connected'] = mqtt_manager.is_connected
    last_seen = max(
        float(rt.get('last_heartbeat_time') or 0.0),
        float(rt.get('battery_updated_at') or 0.0),
    )
    stats['robot_last_seen'] = last_seen
    if last_seen > 0:
        stats['robot_last_seen_ago'] = round(time.time() - last_seen, 1)
    else:
        stats['robot_last_seen_ago'] = None
    stats['robot_heartbeat_source'] = rt.get('heartbeat_source')
    stats['face_collection_active'] = state.face_collection_state['active']
    stats['collection_progress'] = (
        f"{state.face_collection_state['images_collected']}/"
        f"{state.face_collection_state['total_images']}"
    )
    stats['loaded_faces'] = len(face_db.known_face_names)
    stats['attendance_system_enabled'] = state.attendance_system_enabled
    stats['background_processing'] = state.background_processing
    stats['recognition_status'] = "running" if state.recognition_enabled else "stopped"
    stats['video_feed_fps'] = state.stats.get('video_feed_fps', 0)
    stats['openmv_camera_active'] = bool(stats.get('openmv_camera_active'))
    vf_fps = float(stats.get('video_feed_fps') or 0)
    robot_fps = float(rt.get('fps') or 0) if robot_id else 0.0
    frames_rx = int(rt.get('frames_received') or 0) if robot_id else 0
    with state.frame_lock:
        has_recent_frame = False
        if robot_id and robot_id in state.robot_frame_times:
            has_recent_frame = time.time() - state.robot_frame_times[robot_id] < 5.0
        elif state.current_frame is not None and state.robot_frame_times:
            last_any = max(state.robot_frame_times.values())
            has_recent_frame = time.time() - last_any < 5.0
    has_stream = vf_fps > 0 or robot_fps > 0 or frames_rx > 0 or has_recent_frame
    stats['video_stream_active'] = has_stream
    if has_stream:
        stats['openmv_camera_active'] = True
    stats['openmv_face_tracking_active'] = get_face_tracking_desired(robot_id)
    stats['openmv_device_tracking_active'] = bool(
        (state.openmv_stats_by_robot.get(str(robot_id), {}) if robot_id else {}).get(
            'openmv_device_tracking_active', False
        )
    )
    stats['openmv_system_state'] = stats.get('openmv_system_state')
    stats['head_pan_angle'] = stats.get('head_pan_angle')
    stats['head_tilt_angle'] = stats.get('head_tilt_angle')
    stats['openmv_faces_detected'] = int(stats.get('openmv_faces_detected') or 0)
    stats['selected_robot_id'] = robot_id

    if robot_id:
        display_fps = robot_fps
        display_frames = int(rt.get('frames_received') or 0)
        if display_frames == 0 and has_recent_frame:
            with state.frame_lock:
                for rid, ft in state.robot_frame_times.items():
                    if time.time() - ft < 5.0:
                        alt_rt = get_robot_runtime_copy(rid)
                        display_frames = int(alt_rt.get('frames_received') or 0)
                        display_fps = float(alt_rt.get('fps') or 0)
                        break
        stats['frames_received'] = display_frames
        stats['fps'] = display_fps
        stats['latency'] = rt.get('latency', 0)
        stats['human_tracking_enabled'] = bool(rt.get('human_tracking_enabled'))
        stats['human_tracking_active'] = bool(rt.get('human_tracking_active'))
        stats['humans_detected'] = rt.get('humans_detected', 0)
        stats['humans_tracking'] = rt.get('humans_tracking', 0)
        stats['garbage_tracking_enabled'] = bool(rt.get('garbage_tracking_enabled'))
        stats['garbage_tracking_active'] = bool(rt.get('garbage_tracking_active'))
        stats['garbage_detected'] = rt.get('garbage_detected', 0)
        stats['garbage_pickup_in_progress'] = bool(rt.get('garbage_pickup_in_progress'))
        stats['last_control_command'] = rt.get('last_control_command')
        stats['battery_valid'] = bool(rt.get('battery_valid'))
        stats['battery_voltage'] = rt.get('battery_voltage')
        stats['battery_percent'] = rt.get('battery_percent')
        stats['battery_level'] = rt.get('battery_level') or 'unknown'
        stats['battery_updated_at'] = rt.get('battery_updated_at', 0)
        target = rt.get('current_human_target')
    else:
        stats['frames_received'] = 0
        stats['fps'] = 0
        stats['latency'] = 0
        stats['human_tracking_enabled'] = False
        stats['human_tracking_active'] = False
        stats['humans_detected'] = 0
        stats['humans_tracking'] = 0
        stats['garbage_tracking_enabled'] = False
        stats['garbage_tracking_active'] = False
        stats['garbage_detected'] = 0
        stats['garbage_pickup_in_progress'] = False
        stats['last_control_command'] = None
        stats['battery_valid'] = False
        stats['battery_voltage'] = None
        stats['battery_percent'] = None
        stats['battery_level'] = 'unknown'
        stats['battery_updated_at'] = 0
        target = None

    stats['garbage_model_loaded'] = bool(garbage_tracker.stats.get('model_loaded'))
    stats['garbage_model_path'] = garbage_tracker.stats.get('model_path')
    model_mtime = garbage_tracker.stats.get('model_mtime')
    stats['garbage_model_mtime'] = model_mtime
    stats['garbage_model_mtime_str'] = (
        time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(model_mtime))
        if model_mtime else None
    )
    stats['garbage_model_classes'] = garbage_tracker.stats.get('model_classes', [])

    if isinstance(target, dict):
        safe_target = {}
        for key, value in target.items():
            if isinstance(value, tuple):
                safe_target[key] = list(value)
            else:
                safe_target[key] = value
        stats['current_human_target'] = safe_target
    else:
        stats['current_human_target'] = None

    stats['human_tracking_stats'] = {
        'detected_count': stats['humans_detected'],
        'tracking_count': stats['humans_tracking'],
        'last_control_command': stats.get('last_control_command'),
    }

    required_fields = [
        'clients', 'frames_received', 'fps', 'latency', 'known_faces',
        'recognition_enabled', 'mqtt_connected', 'face_collection_active',
        'collection_progress', 'loaded_faces', 'processing_time', 'frame_skip_rate',
        'recognition_status', 'current_recognitions', 'background_processing',
        'last_video_print_time', 'video_feed_fps', 'frame_size',
        'human_tracking_enabled', 'human_tracking_active', 'humans_detected', 'humans_tracking'
    ]

    for field in required_fields:
        if field not in stats:
            if field in ('current_recognitions',):
                stats[field] = []
            elif field in ('background_processing', 'human_tracking_enabled', 'human_tracking_active'):
                stats[field] = False
            elif field in ('humans_detected', 'humans_tracking'):
                stats[field] = 0
            elif field == 'frame_size':
                stats[field] = 'N/A'
            else:
                stats[field] = 0

    return stats


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
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/api/flask_status')
def get_flask_status():
    """获取Flask识别状态"""
    status = "running" if state.recognition_enabled else "stopped"
    state.stats['recognition_status'] = status
    return jsonify({
        "recognition_enabled": state.recognition_enabled,
        "status": status
    })


@app.route('/api/human_tracking/<action>')
def control_human_tracking(action):
    """控制人体跟踪"""
    global state, human_tracker
    from auth import get_selected_robot_id
    from robot_context import get_robot_runtime

    robot_id = get_selected_robot_id()
    if not robot_id:
        return jsonify({"status": "error", "message": "请先选择要控制的机器人"})

    if not hasattr(human_tracker, 'mqtt_manager') or human_tracker.mqtt_manager is None:
        human_tracker.set_mqtt_manager(mqtt_manager)
        print("✅ 初始化人体跟踪器的MQTT管理器")

    rt = get_robot_runtime(robot_id)

    if action == 'start_detection':
        human_tracker.enable_detection_only(robot_id=robot_id)
        print(f"👤 人体检测已开启 robot={robot_id}")
        return jsonify({"status": "success", "message": "人体检测已开启（仅检测不跟踪）"})

    elif action == 'start_tracking':
        human_tracker.start_tracking(robot_id=robot_id)
        print(f"🎯 人体跟踪已开启 robot={robot_id}")
        return jsonify({"status": "success", "message": "人体跟踪已开启（检测+跟踪）"})

    elif action == 'stop_tracking':
        human_tracker.stop_tracking(robot_id=robot_id)
        print(f"⏹️ 人体跟踪已停止 robot={robot_id}")
        return jsonify({"status": "success", "message": "人体跟踪已停止（保持检测）"})

    elif action == 'disable':
        human_tracker.disable_tracking(robot_id=robot_id)
        print(f"🔴 人体跟踪已完全禁用 robot={robot_id}")
        return jsonify({"status": "success", "message": "人体跟踪已完全禁用"})

    elif action == 'reset':
        human_tracker.reset()
        rt['humans_detected'] = 0
        rt['humans_tracking'] = 0
        rt['current_human_target'] = None
        print(f"🔄 人体跟踪器已重置 robot={robot_id}")
        return jsonify({"status": "success", "message": "人体跟踪器已重置"})

    elif action == 'manual_command':
        command = request.args.get('command', 'stop')
        if command in ['forward', 'backward', 'left', 'right', 'stop']:
            human_tracker._send_control_command(command, robot_id=robot_id)
            return jsonify({"status": "success", "message": f"已发送指令: {command}"})
        else:
            return jsonify({"status": "error", "message": "无效指令"})

    return jsonify({"status": "error", "message": "无效操作"})


def _ensure_garbage_tracker_mqtt():
    """确保垃圾跟踪器已绑定 MQTT"""
    if not hasattr(garbage_tracker, 'mqtt_manager') or garbage_tracker.mqtt_manager is None:
        garbage_tracker.set_mqtt_manager(mqtt_manager)


def _sync_garbage_pickup_hardware(enabled: bool, robot_id: Optional[str] = None):
    """同步 ESP32 垃圾模式。检测在 Flask 端完成，不向 OpenMV 发 B/C，避免误关摄像头。"""
    if not robot_id:
        return False
    if not mqtt_manager.is_connected:
        print("⚠️ MQTT 未连接，无法同步硬件垃圾捡取模式")
        return False

    try:
        payload = json.dumps({
            "enabled": enabled,
            "target_distance_cm": garbage_tracker.target_pickup_distance_cm,
            "source": "web",
            "timestamp": time.time(),
        })
        mqtt_manager.publish_to_robot(
            'cmd/garbage_pickup/mode', payload, qos=1, robot_id=robot_id
        )
        return True
    except Exception as e:
        print(f"❌ 同步硬件垃圾捡取模式失败: {e}")
        return False


def _disable_human_tracking_for_garbage(robot_id: Optional[str] = None):
    """开启垃圾捡取前关闭人体跟踪，避免底盘指令冲突"""
    from robot_context import get_robot_runtime
    if not robot_id:
        return
    rt = get_robot_runtime(robot_id)
    if not rt.get('human_tracking_enabled') and not rt.get('human_tracking_active'):
        return
    try:
        human_tracker.disable_tracking(robot_id=robot_id)
    except Exception as e:
        print(f"⚠️ 关闭人体跟踪失败: {e}")


@app.route('/api/garbage_pickup/<action>')
def control_garbage_pickup(action):
    """Web 端控制垃圾检测、对准与捡取流程"""
    global state, garbage_tracker
    from auth import get_selected_robot_id
    from robot_context import get_robot_runtime

    robot_id = get_selected_robot_id()
    if not robot_id:
        return jsonify({"status": "error", "message": "请先选择要控制的机器人"})

    _ensure_garbage_tracker_mqtt()
    rt = get_robot_runtime(robot_id)

    if action == 'start':
        if not garbage_tracker.stats.get('model_loaded'):
            return jsonify({
                "status": "error",
                "message": "垃圾检测模型未加载，请将 garbage.pt 放入 face_recognition_system 目录",
            })

        if rt.get('garbage_tracking_enabled') and rt.get('garbage_tracking_active'):
            return jsonify({"status": "success", "message": "垃圾捡取已在进行中"})

        _disable_human_tracking_for_garbage(robot_id)

        garbage_tracker.enable_tracking(publish_mode=False, robot_id=robot_id)

        hardware_ok = _sync_garbage_pickup_hardware(True, robot_id=robot_id)
        msg = f"已开始拾取前方垃圾 (robot={robot_id})：正在检测并对准目标"
        if not hardware_ok:
            msg += "（MQTT 未连接，仅服务器端检测）"
        print(f"🗑️ {msg}")
        return jsonify({"status": "success", "message": msg})

    if action == 'stop':
        garbage_tracker.disable_tracking(publish_mode=False, robot_id=robot_id)
        _sync_garbage_pickup_hardware(False, robot_id=robot_id)
        print(f"⏹️ Web 已停止垃圾捡取 robot={robot_id}")
        return jsonify({"status": "success", "message": "已停止垃圾捡取"})

    if action == 'status':
        target = rt.get('current_garbage_target')
        safe_target = None
        if isinstance(target, dict):
            safe_target = {}
            for key, value in target.items():
                if isinstance(value, tuple):
                    safe_target[key] = list(value)
                else:
                    safe_target[key] = value

        model_mtime = garbage_tracker.stats.get('model_mtime')
        return jsonify({
            "status": "success",
            "robot_id": robot_id,
            "garbage_tracking_enabled": rt.get('garbage_tracking_enabled', False),
            "garbage_tracking_active": rt.get('garbage_tracking_active', False),
            "garbage_detected": rt.get('garbage_detected', 0),
            "garbage_pickup_in_progress": rt.get('garbage_pickup_in_progress', False),
            "model_loaded": garbage_tracker.stats.get('model_loaded', False),
            "model_path": garbage_tracker.stats.get('model_path'),
            "model_mtime": model_mtime,
            "model_mtime_str": (
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(model_mtime))
                if model_mtime else None
            ),
            "model_classes": garbage_tracker.stats.get('model_classes', []),
            "last_control_command": rt.get('last_control_command'),
            "current_target": safe_target,
        })

    if action == 'reload_model':
        ok = garbage_tracker.reload_model()
        state.stats['garbage_model_loaded'] = ok
        if ok:
            return jsonify({
                "status": "success",
                "message": (
                    f"模型已重新加载: {garbage_tracker.stats.get('model_path')} "
                    f"({', '.join(garbage_tracker.stats.get('model_classes', []))})"
                ),
            })
        return jsonify({
            "status": "error",
            "message": f"模型加载失败，请检查: {garbage_tracker.model_path}",
        })

    return jsonify({"status": "error", "message": "无效操作"})


@app.route('/api/test_human_detection')
def test_human_detection():
    """测试人体检测功能"""
    global state, human_tracker

    try:
        with state.frame_lock:
            if state.current_frame is None:
                return jsonify({"status": "error", "message": "没有可用的帧数据"})

            # 解码帧
            nparr = np.frombuffer(state.current_frame, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                return jsonify({"status": "error", "message": "无法解码帧"})

            # 进行人体检测
            detections = human_tracker.detect_humans(frame)

            # 绘制检测结果
            test_frame = frame.copy()
            for i, (x, y, w, h) in enumerate(detections):
                cv2.rectangle(test_frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                cv2.putText(test_frame, f"Person {i + 1}", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # 保存测试图像
            test_filename = f"human_test_{int(time.time())}.jpg"
            cv2.imwrite(test_filename, test_frame)

            return jsonify({
                "status": "success",
                "message": f"检测到 {len(detections)} 个人体",
                "detections": detections,
                "image_saved": test_filename
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/human_tracking/status')
def get_human_tracking_status():
    """获取人体跟踪状态"""
    from auth import get_selected_robot_id
    from robot_context import get_robot_runtime_copy

    robot_id = get_selected_robot_id()
    rt = get_robot_runtime_copy(robot_id) if robot_id else {}
    stats = human_tracker.get_stats()

    return jsonify({
        "robot_id": robot_id,
        "tracking_enabled": rt.get('human_tracking_enabled', False),
        "tracking_active": rt.get('human_tracking_active', False),
        "stats": stats,
        "current_target": rt.get('current_human_target'),
        "detected_count": rt.get('humans_detected', 0),
        "tracking_count": rt.get('humans_tracking', 0),
        "mqtt_connected": hasattr(human_tracker, 'mqtt_manager') and human_tracker.mqtt_manager is not None,
        "mqtt_manager_type": type(human_tracker.mqtt_manager).__name__ if hasattr(human_tracker, 'mqtt_manager') else "None",
        "control_history": human_tracker.control_history[-10:] if hasattr(human_tracker, 'control_history') else []
    })


@app.route('/api/human_tracking/control_params', methods=['POST'])
def update_control_params():
    """更新人体跟踪控制参数"""
    try:
        data = request.get_json()

        center_threshold = data.get('center_threshold')
        min_area = data.get('min_area')
        max_area = data.get('max_area')

        # 更新控制参数
        human_tracker.update_control_params(
            center_threshold=center_threshold,
            min_area=min_area,
            max_area=max_area
        )

        return jsonify({
            "status": "success",
            "message": "控制参数已更新",
            "params": {
                "center_threshold": human_tracker.center_threshold,
                "min_area_ratio": human_tracker.min_area_ratio,
                "max_area_ratio": human_tracker.max_area_ratio
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"更新参数失败: {str(e)}"
        })


@app.route('/api/human_tracking/send_command/<command>')
def send_direct_command(command):
    """直接发送控制指令"""
    from auth import get_selected_robot_id
    robot_id = get_selected_robot_id()
    if not robot_id:
        return jsonify({"status": "error", "message": "请先选择要控制的机器人"})
    try:
        if command in ['forward', 'backward', 'left', 'right', 'stop']:
            human_tracker._send_control_command(command, robot_id=robot_id)
            return jsonify({
                "status": "success",
                "message": f"已发送指令: {command}"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "无效指令"
            })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"发送指令失败: {str(e)}"
        })


@app.route('/api/human_tracking/history')
def get_control_history():
    """获取控制指令历史"""
    try:
        history = human_tracker.control_history if hasattr(human_tracker, 'control_history') else []

        # 格式化时间
        for item in history:
            item['time_str'] = time.strftime('%H:%M:%S', time.localtime(item['time']))

        return jsonify({
            "status": "success",
            "history": history[-20:],  # 返回最近20条
            "count": len(history)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"获取历史失败: {str(e)}"
        })


@app.route('/human_tracking')
def human_tracking_page():
    """人体跟踪控制页面"""
    return render_template('human_tracking.html')


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
    """视频流生成器 - 仅推送当前用户所选机器人的画面"""
    from auth import user_can_access_robot, get_selected_robot_id

    robot_id = get_selected_robot_id()
    if not robot_id or not user_can_access_robot(robot_id):
        def denied():
            while True:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' +
                       generate_black_frame() + b'\r\n')
                time.sleep(1)
        return Response(denied(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def generate():
        from robot_context import get_robot_runtime

        last_frame_time = 0
        frame_count = 0

        print(f"🎬 开始视频流传输 robot_id={robot_id}")

        while True:
            process_face_collection()
            rt = get_robot_runtime(robot_id)
            current_frame = get_robot_frame(robot_id)

            if current_frame is not None:
                try:
                    current_time = time.time()

                    time_since_last = current_time - last_frame_time
                    if time_since_last < CONFIG['min_frame_interval']:
                        continue

                    processed_frame = None
                    if rt.get('garbage_tracking_enabled'):
                        processed_frame = process_frame_with_garbage(current_frame, robot_id=robot_id)
                    elif rt.get('human_tracking_enabled'):
                        processed_frame = process_frame_with_humans(current_frame, robot_id=robot_id)
                    else:
                        processed_frame = current_frame

                    openmv_stats = state.openmv_stats_by_robot.get(robot_id, {}) if robot_id else {}
                    face_track_on = get_face_tracking_desired(robot_id)
                    openmv_has_faces = int(openmv_stats.get('openmv_faces_detected') or 0) > 0
                    if (
                        face_track_on
                        and not openmv_has_faces
                        and not rt.get('garbage_tracking_enabled')
                        and not rt.get('human_tracking_enabled')
                        and not state.face_collection_active
                        and not state.recognition_enabled
                    ):
                        processed_frame, track_info = apply_face_tracking_overlay(processed_frame)
                        if track_info:
                            publish_face_tracking_head(track_info, robot_id=robot_id)

                    # 处理人脸识别
                    if state.face_collection_active:
                        processed_frame = process_frame_with_faces(processed_frame)
                    elif state.recognition_enabled and frame_count % 2 == 0:
                        processed_frame = process_frame_for_display(processed_frame)

                    # 发送帧
                    yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + processed_frame + b'\r\n')

                    last_frame_time = current_time
                    frame_count += 1

                    # 更新帧率统计
                    if frame_count % 10 == 0:
                        if time_since_last > 0:
                            fps = 1.0 / time_since_last
                            state.stats['video_feed_fps'] = int(fps)

                except Exception as e:
                    logger.error(f"处理帧失败: {e}")
                    # 发送原始帧作为回退
                    yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + current_frame + b'\r\n')
            else:
                # 没有帧数据，发送黑色帧
                current_time = time.time()
                if last_frame_time == 0 or current_time - last_frame_time > 1.0:
                    black_frame = generate_black_frame()
                    yield (b'--frame\r\n'b'Content-Type: image/jpeg\r\n\r\n' + black_frame + b'\r\n')
                    last_frame_time = current_time

            time.sleep(CONFIG['video_feed_sleep'])

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/save_rubbish_photo', methods=['POST'])
def save_rubbish_photo():
    """保存 OpenMV 当前原始帧到 rubbish_photo 文件夹，用于垃圾检测训练数据采集"""
    try:
        os.makedirs(RUBBISH_PHOTO_DIR, exist_ok=True)

        robot_id = session.get('selected_robot_id')
        raw_frame = get_robot_raw_frame(robot_id)

        if raw_frame is None:
            with state.frame_lock:
                raw_frame = state.last_raw_frame or state.current_frame

        if raw_frame is None:
            return jsonify({
                'status': 'error',
                'message': '当前没有视频帧，请确认 OpenMV 已开启并正在推流',
            }), 400

        img = cv2.imdecode(np.frombuffer(raw_frame, np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            return jsonify({'status': 'error', 'message': '无法解码当前视频帧'}), 400

        if len(img.shape) == 2 or (len(img.shape) == 3 and img.shape[2] == 1):
            color_mode = 'grayscale'
        else:
            color_mode = 'color'

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        filename = f'rubbish_{timestamp}.jpg'
        filepath = os.path.join(RUBBISH_PHOTO_DIR, filename)

        with open(filepath, 'wb') as f:
            f.write(raw_frame)

        total_saved = sum(
            1 for name in os.listdir(RUBBISH_PHOTO_DIR)
            if name.lower().endswith(('.jpg', '.jpeg', '.png'))
        )

        return jsonify({
            'status': 'success',
            'message': f'已保存截图: {filename}',
            'filename': filename,
            'folder': RUBBISH_PHOTO_DIR,
            'color_mode': color_mode,
            'width': int(img.shape[1]),
            'height': int(img.shape[0]),
            'total_saved': total_saved,
            'training_hint': (
                '已保存 OpenMV 原始画面。训练时请统一使用同类图像；'
                '若 OpenMV 为灰度推流，训练集也应以灰度为主，避免灰度/彩色混用。'
            ),
        })
    except Exception as e:
        logger.error(f"保存训练截图失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def _publish_camera_control(command: str) -> bool:
    """向 OpenMV 发送 camera_control 单字符指令（与 ASRPRO/ESP32-C3 协议一致）"""
    if not mqtt_manager.is_connected:
        return False
    result = mqtt_manager.client.publish("camera_control", command, qos=1)
    return result.rc == 0


def _publish_camera_control_repeat(command: str, times: int = 3) -> bool:
    """重复发送 camera_control，提高 OpenMV 收到关闭/开启指令的概率"""
    ok = False
    for i in range(max(1, times)):
        if _publish_camera_control(command):
            ok = True
        if i + 1 < times:
            time.sleep(0.15)
    return ok


@app.route('/api/camera/open')
def open_camera():
    """Web 端直接打开 OpenMV 摄像头（开启视频流，不启用人脸追踪）"""
    from auth import get_selected_robot_id

    robot_id = get_selected_robot_id()
    if not robot_id:
        return jsonify({"status": "error", "message": "请先选择要控制的机器人"})

    if not mqtt_manager.is_connected:
        return jsonify({"status": "error", "message": "MQTT 未连接，无法打开摄像头"})

    if not _publish_camera_control_repeat("1", 2):
        return jsonify({"status": "error", "message": "打开摄像头指令发送失败"})

    state.stats['openmv_camera_active'] = True
    state.frame_cache = None
    print(f"📷 Web 已发送打开摄像头指令 (robot={robot_id})")
    return jsonify({"status": "success", "message": "摄像头已打开，视频流即将更新"})


@app.route('/api/camera/close')
def close_camera():
    """Web 端关闭 OpenMV 摄像头（画面黑屏，并停止人脸识别）"""
    from auth import get_selected_robot_id

    robot_id = get_selected_robot_id()
    if not robot_id:
        return jsonify({"status": "error", "message": "请先选择要控制的机器人"})

    if not mqtt_manager.is_connected:
        return jsonify({"status": "error", "message": "MQTT 未连接，无法关闭摄像头"})

    if not _publish_camera_control("6"):
        return jsonify({"status": "error", "message": "关闭摄像头指令发送失败"})

    if state.recognition_enabled:
        state.recognition_enabled = False
        state.stats['recognition_enabled'] = False
        state.stats['recognition_status'] = 'stopped'
        stop_background_processing()

    state.stats['openmv_camera_active'] = False
    _set_face_tracking_stats(str(robot_id), False)
    state.frame_cache = None
    print(f"📷 Web 已发送关闭摄像头指令 (robot={robot_id})")
    return jsonify({"status": "success", "message": "摄像头已关闭"})


@app.route('/api/face_tracking/<action>')
def control_face_tracking(action):
    """Web 端控制 OpenMV 人脸跟踪（头部两路舵机）"""
    from auth import get_selected_robot_id

    robot_id = get_selected_robot_id()
    if not robot_id:
        return jsonify({"status": "error", "message": "请先选择要控制的机器人"})

    if not mqtt_manager.is_connected:
        return jsonify({"status": "error", "message": "MQTT 未连接，无法控制人脸跟踪"})

    if action == 'start':
        if not _publish_camera_control_repeat("3", 2):
            return jsonify({"status": "error", "message": "开启人脸跟踪指令发送失败"})
        _set_face_tracking_stats(str(robot_id), True)
        print(f"🎯 Web 已开启 OpenMV 人脸跟踪 (robot={robot_id})")
        return jsonify({"status": "success", "message": "已开启跟踪人脸"})

    if action == 'stop':
        if not _publish_camera_control_repeat("1", 3):
            return jsonify({"status": "error", "message": "关闭人脸跟踪指令发送失败"})
        _set_face_tracking_stats(str(robot_id), False)
        print(f"⏹️ Web 已关闭 OpenMV 人脸跟踪 (robot={robot_id})")
        return jsonify({"status": "success", "message": "已关闭跟踪人脸"})

    return jsonify({"status": "error", "message": "无效操作"})


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
        state.stats['recognition_enabled'] = True
        state.stats['recognition_status'] = 'running'
        start_background_processing()
        print("🟢 人脸识别已开启 (由Web界面触发)")
        print("🔧 后台处理线程已激活")
        return jsonify({"status": "success", "message": "人脸识别已开启"})
    elif action == 'stop':
        state.recognition_enabled = False
        state.stats['recognition_enabled'] = False
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
        return jsonify(build_stats_response())

    except Exception as e:
        logger.error(f"获取统计信息错误: {e}")
        import traceback
        traceback.print_exc()
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
            'frame_size': 'N/A',
            'human_tracking_enabled': state.human_tracking_enabled,
            'human_tracking_active': state.human_tracking_active,
            'humans_detected': state.human_tracking_stats['detected_count'],
            'humans_tracking': state.human_tracking_stats['tracking_count'],
            'current_human_target': state.current_human_target,
            'last_control_command': state.human_tracking_stats.get('last_control_command')
        }
        return jsonify(default_stats)


@app.before_request
def before_request():
    state.connected_clients += 1

    auth_resp = check_request_auth()
    if auth_resp is not None:
        return auth_resp

    path = request.path
    if is_robot_control_api(path, request.method):
        guard = require_robot_for_control()
        if guard is not None:
            return guard


@app.teardown_request
def teardown_request(exception=None):
    state.connected_clients -= 1


@app.context_processor
def inject_auth_context():
    """模板中可用 current_user、selected_robot_id"""
    from flask_login import current_user as cu

    selected_robot_id = session.get('selected_robot_id')
    selected_robot_name = None
    has_bound_robots = False
    if cu.is_authenticated and auth_database:
        if cu.is_admin:
            has_bound_robots = len(auth_database.list_robots()) > 0
        else:
            has_bound_robots = len(auth_database.list_robots_for_user(cu.id)) > 0
    if selected_robot_id and auth_database:
        robot = auth_database.get_robot(selected_robot_id)
        if robot:
            selected_robot_name = robot.get('display_name')
    return {
        'selected_robot_id': selected_robot_id,
        'selected_robot_name': selected_robot_name,
        'has_bound_robots': has_bound_robots,
        'robot_control_required': has_bound_robots and not selected_robot_id,
    }


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
    os.makedirs(RUBBISH_PHOTO_DIR, exist_ok=True)
    index_path = os.path.join(_APP_DIR, 'templates', 'index.html')
    print(f"📂 应用目录: {_APP_DIR}")
    print(f"📄 首页模板: {index_path}")
    print(f"📁 截图目录: {RUBBISH_PHOTO_DIR}")
    if os.path.isfile(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            has_save_btn = 'saveRubbishPhoto' in f.read()
        print(f"🔘 保存截图按钮: {'已包含' if has_save_btn else '未找到，请检查 templates/index.html'}")
    print("🚀 应用启动，初始化后台处理线程")
    print("🔄 初始化MQTT映射...")
    update_mqtt_mapping()

    # 设置MQTT管理器到人体跟踪器 - 确保使用正确的MQTT管理器
    if not hasattr(human_tracker, 'mqtt_manager') or human_tracker.mqtt_manager is None:
        human_tracker.set_mqtt_manager(mqtt_manager)
        print("✅ MQTT管理器已设置到人体跟踪器")
    else:
        print("ℹ️ 人体跟踪器已设置MQTT管理器")

    if not hasattr(garbage_tracker, 'mqtt_manager') or garbage_tracker.mqtt_manager is None:
        garbage_tracker.set_mqtt_manager(mqtt_manager)
        print("✅ MQTT管理器已设置到垃圾跟踪器")

    # 如果人体跟踪已启用，确保其状态正确
    if state.human_tracking_enabled:
        human_tracker.enable_tracking()
        print("🎯 恢复人体跟踪状态")

    if state.recognition_enabled:
        start_background_processing()



@atexit.register
def cleanup():
    """应用关闭时执行"""
    print("🛑 应用关闭，停止后台处理线程")
    stop_background_processing()


if __name__ == '__main__':
    print("=" * 50)
    print("🚀 启动基于face_recognition的人脸识别服务器 (优化版本)")
    print("🤖 人体跟踪功能已集成")
    print("=" * 50)
    print(f"📊 视频流优化配置:")
    print(f"   - 显示缩放因子: {CONFIG['display_scale_factor']}")
    print(f"   - JPEG质量: {CONFIG['jpeg_quality']}%")
    print(f"   - 视频流休眠: {CONFIG['video_feed_sleep']}秒")
    print(f"   - 最大显示尺寸: {CONFIG['max_display_width']}x{CONFIG['max_display_height']}")
    print(f"🤖 人体跟踪配置:")
    print(f"   - 检测间隔: {CONFIG['human_detection_interval']}帧")
    print(f"   - 最小置信度: {CONFIG['min_human_confidence']}")
    print(f"   - 控制指令间隔: {CONFIG['control_interval']}秒")
    print("=" * 50)

    initialize_app()

    mqtt_ok = mqtt_manager.connect()
    if not mqtt_ok:
        logger.error("MQTT 连接失败，网页仍会启动，后台将继续重试 MQTT")

        def retry_mqtt_loop():
            while not mqtt_manager.is_connected:
                time.sleep(5)
                try:
                    mqtt_manager.connect()
                except Exception:
                    pass

        threading.Thread(target=retry_mqtt_loop, daemon=True, name='mqtt-retry').start()

    local_ip = get_local_ip()
    print(f"🌐 服务器访问地址:")
    print(f"   客户登录: http://localhost:5000/login")
    print(f"   管理后台: http://localhost:5000/admin/login")
    print(f"   http://{local_ip}:5000/login")
    if not mqtt_ok:
        print("   ⚠️ MQTT 尚未连接，机器人功能可能暂不可用")
    print("=" * 50)

    def open_browser_when_ready():
        import socket
        for _ in range(120):
            try:
                with socket.create_connection(('127.0.0.1', 5000), timeout=1):
                    pass
                webbrowser.open('http://127.0.0.1:5000/login')
                return
            except OSError:
                time.sleep(1)

    if not os.environ.get('NO_AUTO_BROWSER'):
        threading.Thread(target=open_browser_when_ready, daemon=True, name='open-browser').start()

    from werkzeug.serving import WSGIRequestHandler

    WSGIRequestHandler.protocol_version = "HTTP/1.1"

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
