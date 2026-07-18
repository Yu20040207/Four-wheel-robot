"""
人体跟踪模块 - 完整控制版本
用于检测和跟踪视频中的人体，并生成控制指令
"""

import cv2
import numpy as np
import time
import threading
import json
import math


class HumanTracker:
    """人体跟踪器类 - 完整控制版本"""

    def __init__(self, config=None):
        # 配置参数
        self.config = config or {}

        # 人体检测器 - 使用HOG特征+SVM检测器
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        # 跟踪状态
        self.tracking_enabled = False
        self.tracking_active = False
        self.current_target = None  # 当前跟踪的目标
        self.tracked_persons = []   # 所有被跟踪的人体

        # 线程锁
        self.lock = threading.Lock()

        # 帧处理相关
        self.frame_count = 0
        self.detection_interval = 3  # 每3帧检测一次

        # 统计信息
        self.stats = {
            'detected_count': 0,
            'tracking_count': 0,
            'fps': 0,
            'detection_time': 0,
            'last_control_command': None,
            'last_control_time': 0,
            'last_detection_time': 0,
            'total_frames': 0,
            'processing_time': 0
        }

        # 控制参数
        self.control_interval = 0.3  # 控制指令发送间隔（秒）
        self.last_command_time = 0

        # 控制阈值
        self.center_threshold = 0.15  # 中心区域阈值（图像宽度的15%）
        self.min_area_ratio = 0.05    # 最小面积比例（前进）
        self.max_area_ratio = 0.25    # 最大面积比例（后退）
        self.min_target_width = 40    # 最小目标宽度
        self.min_target_height = 80   # 最小目标高度

        # 消息队列用于发送跟踪指令
        self.mqtt_manager = None

        # 指令历史
        self.control_history = []
        self.max_history_size = 20

        # 帧率计算
        self._last_fps_time = time.time()
        self._frame_times = []
        self._max_frame_times = 30

        print("✅ 人体跟踪器初始化完成 - 完整控制版")
        print(f"   控制参数: 中心阈值={self.center_threshold}, 最小面积={self.min_area_ratio}, 最大面积={self.max_area_ratio}")

    def set_mqtt_manager(self, mqtt_manager):
        """设置MQTT管理器"""
        self.mqtt_manager = mqtt_manager
        if self.mqtt_manager and hasattr(self.mqtt_manager, 'client'):
            print("🔗 MQTT管理器已连接到人体跟踪器")
        else:
            print("⚠️ MQTT管理器连接异常")

    def enable_tracking(self, robot_id=None):
        """启用人体跟踪"""
        if not robot_id:
            return False
        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)
        with self.lock:
            self.tracking_enabled = True
            self.tracking_active = True
            self._active_robot_id = robot_id
            rt['human_tracking_enabled'] = True
            rt['human_tracking_active'] = True
        print(f"🎯 人体跟踪已启用 robot_id={robot_id}")
        if self.mqtt_manager:
            self._send_status_update("tracking_enabled", robot_id=robot_id)
        return True

    def disable_tracking(self, robot_id=None):
        """禁用人体跟踪 - 确保完全停止"""
        if not robot_id:
            robot_id = getattr(self, '_active_robot_id', None)
        if not robot_id:
            return False
        from robot_context import reset_robot_human
        print(f"🔴 开始禁用人体跟踪 robot_id={robot_id}...")
        try:
            self._send_control_command("stop", robot_id=robot_id)
            with self.lock:
                self.tracking_enabled = False
                self.tracking_active = False
                self.current_target = None
                self.tracked_persons = []
                self.stats = {
                    'detected_count': 0,
                    'tracking_count': 0,
                    'fps': 0,
                    'detection_time': 0,
                    'last_control_command': None,
                    'last_control_time': 0,
                    'last_detection_time': 0,
                    'total_frames': 0,
                    'processing_time': 0
                }
                self.control_history = []
                self._frame_times = []
                if getattr(self, '_active_robot_id', None) == robot_id:
                    self._active_robot_id = None
            reset_robot_human(robot_id)
            print(f"✅ 人体跟踪已完全禁用 robot_id={robot_id}")
            if self.mqtt_manager:
                self._send_status_update("tracking_disabled", robot_id=robot_id)
            return True
        except Exception as e:
            print(f"❌ 禁用人体跟踪失败: {e}")
            return False

    def start_tracking(self, robot_id=None):
        """开始跟踪"""
        if not robot_id:
            robot_id = getattr(self, '_active_robot_id', None)
        if not robot_id:
            return False
        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)
        with self.lock:
            self.tracking_enabled = True
            self.tracking_active = True
            self._active_robot_id = robot_id
            rt['human_tracking_enabled'] = True
            rt['human_tracking_active'] = True
        print(f"▶️ 开始人体跟踪 robot_id={robot_id}")
        if self.mqtt_manager:
            self._send_status_update("tracking_started", robot_id=robot_id)
        return True

    def stop_tracking(self, robot_id=None):
        """停止跟踪"""
        if not robot_id:
            robot_id = getattr(self, '_active_robot_id', None)
        if not robot_id:
            return False
        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)
        with self.lock:
            self.tracking_active = False
            rt['human_tracking_active'] = False
        self._send_control_command("stop", robot_id=robot_id)
        print(f"⏹️ 停止人体跟踪 robot_id={robot_id}")
        if self.mqtt_manager:
            self._send_status_update("tracking_stopped", robot_id=robot_id)
        return True

    def enable_detection_only(self, robot_id=None):
        """仅开启检测，不跟踪"""
        if not robot_id:
            return False
        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)
        with self.lock:
            self.tracking_enabled = True
            self.tracking_active = False
            self._active_robot_id = robot_id
            rt['human_tracking_enabled'] = True
            rt['human_tracking_active'] = False
        print(f"👤 人体检测已开启 robot_id={robot_id}")
        return True

    def detect_humans(self, frame):
        """
        检测人体
        返回: 检测到的人体边界框列表 (x, y, w, h)
        """
        if frame is None:
            return []

        start_time = time.time()

        try:
            # 调整图像大小以提高检测速度
            height, width = frame.shape[:2]

            # 确保图像不为空
            if height == 0 or width == 0:
                return []

            # 如果图像太大，调整大小
            if width > 800 or height > 600:
                scale_factor = 0.5
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                resized_frame = cv2.resize(frame, (new_width, new_height))
            else:
                resized_frame = frame
                scale_factor = 1.0

            # 转换为灰度图像以提高检测速度
            gray_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2GRAY)

            # 使用HOG检测人体
            rects, weights = self.hog.detectMultiScale(
                gray_frame,
                winStride=(4, 4),
                padding=(8, 8),
                scale=1.05
            )

            # 过滤检测结果
            filtered_rects = []
            for i, (x, y, w, h) in enumerate(rects):
                if weights[i] > 0.3:  # 置信度阈值
                    # 调整边界框大小
                    padding = 0.05
                    x = max(0, int(x + w * padding))
                    y = max(0, int(y + h * padding))
                    w = int(w * (1 - 2 * padding))
                    h = int(h * (1 - 2 * padding))

                    # 过滤掉太小的人体
                    if w < self.min_target_width or h < self.min_target_height:
                        continue

                    # 将坐标缩放到原始图像尺寸
                    x = int(x / scale_factor)
                    y = int(y / scale_factor)
                    w = int(w / scale_factor)
                    h = int(h / scale_factor)

                    filtered_rects.append((x, y, w, h))

            # 更新统计信息
            detection_time = (time.time() - start_time) * 1000
            self.stats['detection_time'] = detection_time
            self.stats['detected_count'] = len(filtered_rects)
            self.stats['last_detection_time'] = time.time()

            if filtered_rects and len(filtered_rects) > 0:
                print(f"✅ 检测到 {len(filtered_rects)} 个人体，耗时: {detection_time:.1f}ms")

            return filtered_rects

        except Exception as e:
            print(f"❌ 人体检测错误: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _send_status_update(self, status, robot_id=None):
        """发送状态更新到MQTT"""
        if not self.mqtt_manager or not robot_id:
            return

        try:
            message = json.dumps({
                "status": status,
                "timestamp": time.time(),
                "stats": self.stats
            })
            self.mqtt_manager.publish_to_robot(
                'cmd/human_tracking/status', message, qos=1, robot_id=robot_id
            )
        except Exception as e:
            print(f"❌ 发送状态更新失败: {e}")

    def _send_control_command(self, command, robot_id=None):
        """发送控制指令到MQTT"""
        if not robot_id:
            return
        if not self.mqtt_manager:
            print(f"⚠️ MQTT管理器未设置，无法发送指令: {command}")
            return

        try:
            message = command
            current_time = time.time()

            if current_time - self.last_command_time < 0.2:
                return

            self.last_command_time = current_time
            print(f"📤 发送人体跟踪指令 robot_id={robot_id}: {command}")

            if self.mqtt_manager.publish_to_robot(
                'cmd/human_tracking/command', message, qos=1, robot_id=robot_id
            ):
                self.stats['last_control_command'] = command
                self.stats['last_control_time'] = current_time
                self.control_history.append({
                    'command': command,
                    'time': current_time,
                    'message': message,
                })
                if len(self.control_history) > self.max_history_size:
                    self.control_history.pop(0)
                print(f"✅ 指令发送成功到ESP32: {command}")
            else:
                print("❌ 指令发送失败")

        except Exception as e:
            print(f"❌ 发送控制指令异常: {e}")



    def _calculate_control_command(self, target, frame_width, frame_height):
        """
        根据目标位置计算控制指令
        返回：控制指令（forward, backward, left, right, stop）
        """
        if not target:
            return "stop"

        x, y, w, h = target['bbox']
        center_x, center_y = target['center']

        # 计算目标面积
        target_area = w * h
        frame_area = frame_width * frame_height
        area_ratio = target_area / frame_area

        # 计算目标中心相对于图像中心的偏移（归一化到[-0.5, 0.5]）
        offset_x = (center_x - frame_width / 2) / (frame_width / 2)  # -1到1

        # 计算指令
        command = "stop"

        # 1. 检查目标是否太小（需要前进）
        if area_ratio < self.min_area_ratio:
            command = "forward"
            print(f"🎯 目标太小 ({area_ratio:.3f})，需要前进")

        # 2. 检查目标是否太大（需要后退）
        elif area_ratio > self.max_area_ratio:
            command = "backward"
            print(f"🎯 目标太大 ({area_ratio:.3f})，需要后退")

        # 3. 检查水平偏移（需要转向）
        elif abs(offset_x) > self.center_threshold:
            if offset_x < 0:
                command = "left"
                print(f"🎯 目标偏左 ({offset_x:.3f})，需要左转")
            else:
                command = "right"
                print(f"🎯 目标偏右 ({offset_x:.3f})，需要右转")

        # 4. 目标在中心且大小合适
        else:
            command = "stop"
            print(f"🎯 目标合适，停止")

        # 打印调试信息
        print(f"📊 目标信息: 中心({center_x},{center_y}), 大小({w}x{h}), 面积比{area_ratio:.3f}, 偏移{offset_x:.3f}")
        print(f"📤 发送指令: {command}")

        return command

    def _draw_detections(self, frame, detections):
        """在帧上绘制检测结果"""
        if frame is None:
            return frame

        height, width = frame.shape[:2]

        # 绘制中心区域线
        center_x = width // 2
        center_y = height // 2
        center_width = int(width * self.center_threshold)

        # 绘制中心区域
        left_boundary = center_x - center_width
        right_boundary = center_x + center_width

        # 绘制中心区域矩形
        cv2.rectangle(frame, (left_boundary, 0), (right_boundary, height), (0, 255, 0), 1)

        # 绘制中心十字线
        cv2.line(frame, (center_x, 0), (center_x, height), (0, 255, 255), 1)
        cv2.line(frame, (0, center_y), (width, center_y), (0, 255, 255), 1)

        # 绘制所有检测到的人体
        for i, (x, y, w, h) in enumerate(detections):
            # 计算目标中心
            target_center_x = x + w // 2
            target_center_y = y + h // 2

            # 判断是否在中心区域
            is_in_center = left_boundary <= target_center_x <= right_boundary

            # 设置颜色
            if is_in_center:
                color = (0, 255, 0)  # 绿色：在中心区域
            else:
                color = (0, 165, 255)  # 橙色：不在中心区域

            thickness = 2

            # 绘制边界框
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)

            # 绘制中心点
            cv2.circle(frame, (target_center_x, target_center_y), 5, color, -1)

            # 绘制从图像中心到目标中心的线
            cv2.line(frame, (center_x, center_y), (target_center_x, target_center_y), color, 1)

            # 绘制标签
            label = f"P{i + 1}"
            cv2.putText(frame, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # 绘制检测状态
        if detections:
            status_text = f"Detected: {len(detections)}"
            cv2.putText(frame, status_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        return frame

    def _draw_tracking(self, frame, tracked_persons):
        """在帧上绘制跟踪结果"""
        if frame is None:
            return frame

        height, width = frame.shape[:2]

        # 绘制所有被跟踪的人体
        for person in tracked_persons:
            x, y, w, h = person['bbox']
            person_id = person['id']
            center_x, center_y = person['center']

            # 判断是否是当前跟踪目标
            is_current_target = self.current_target and person['id'] == self.current_target['id']

            # 设置颜色和线宽
            if is_current_target:
                color = (0, 255, 0)  # 绿色：当前跟踪目标
                thickness = 3
            else:
                color = (0, 165, 255)  # 橙色：其他被跟踪的人体
                thickness = 2

            # 绘制边界框
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)

            # 绘制ID标签
            label = f"T{person_id}"
            cv2.putText(frame, label, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 绘制中心点
            cv2.circle(frame, (center_x, center_y), 5, color, -1)

        # 绘制跟踪状态
        if self.tracking_active:
            status_text = "TRACKING: ON"
            status_color = (0, 255, 0)
        else:
            status_text = "TRACKING: OFF"
            status_color = (0, 0, 255)

        cv2.putText(frame, status_text, (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)

        # 绘制控制参数信息
        params_text = f"Center: ±{self.center_threshold:.2f}"
        cv2.putText(frame, params_text, (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        area_text = f"Area: {self.min_area_ratio:.2f}-{self.max_area_ratio:.2f}"
        cv2.putText(frame, area_text, (10, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 绘制最后发送的指令
        if self.stats['last_control_command']:
            command_text = f"CMD: {self.stats['last_control_command'].upper()}"
            command_color = {
                'forward': (0, 255, 0),  # 绿色
                'backward': (0, 0, 255),  # 红色
                'left': (255, 255, 0),  # 青色
                'right': (255, 165, 0),  # 橙色
                'stop': (255, 255, 255)  # 白色
            }.get(self.stats['last_control_command'], (255, 255, 255))

            cv2.putText(frame, command_text, (10, 130),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, command_color, 2)

        return frame

    def process_frame(self, frame, robot_id=None):
        """
        处理一帧图像，检测并跟踪人体
        返回: (处理后的帧, 跟踪信息)
        """
        if frame is None:
            return frame, {
                'tracked_persons': [],
                'detections': [],
                'current_target': None,
                'stats': self.stats.copy()
            }

        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)
        if not robot_id or not rt.get('human_tracking_enabled'):
            return frame, {
                'tracked_persons': [],
                'detections': [],
                'current_target': None,
                'stats': self.stats.copy()
            }

        self._active_robot_id = robot_id
        tracking_active = rt.get('human_tracking_active', False)

        # 记录处理开始时间
        start_time = time.time()

        # 创建输出帧的副本
        output_frame = frame.copy()

        # 更新帧计数
        self.frame_count += 1
        self.stats['total_frames'] = self.frame_count

        # 每detection_interval帧进行一次检测
        detections = []
        if self.frame_count % self.detection_interval == 0:
            detections = self.detect_humans(frame)

        # 如果有检测结果，更新跟踪
        tracked_persons = []
        if detections:
            # 简单的跟踪逻辑：直接使用检测结果
            for i, (x, y, w, h) in enumerate(detections):
                tracked_persons.append({
                    'id': i + 1,
                    'bbox': (x, y, w, h),
                    'center': (x + w // 2, y + h // 2),
                    'age': 1,
                    'area': w * h
                })

            self.tracked_persons = tracked_persons
            self.stats['tracking_count'] = len(tracked_persons)

            # 如果没有当前跟踪目标，选择最大的目标
            if not self.current_target and tracked_persons:
                max_area = 0
                selected_person = None

                for person in tracked_persons:
                    area = person['area']
                    if area > max_area:
                        max_area = area
                        selected_person = person

                if selected_person:
                    self.current_target = selected_person
        else:
            # 如果没有检测到人体，清空目标
            if self.current_target:
                self.current_target = None

        # 在图像上绘制结果
        output_frame = self._draw_detections(output_frame, detections)

        # 如果正在跟踪，绘制跟踪结果
        if self.tracked_persons:
            output_frame = self._draw_tracking(output_frame, self.tracked_persons)

        # 计算FPS
        current_time = time.time()
        self._frame_times.append(current_time)

        # 保留最近30帧的时间
        if len(self._frame_times) > self._max_frame_times:
            self._frame_times.pop(0)

        # 计算平均帧率
        if len(self._frame_times) > 1:
            time_diff = self._frame_times[-1] - self._frame_times[0]
            if time_diff > 0:
                self.stats['fps'] = (len(self._frame_times) - 1) / time_diff

        # 生成控制指令
        current_time = time.time()

        if tracking_active:
            # 检查发送间隔
            if current_time - self.stats['last_control_time'] >= self.control_interval:
                if self.current_target:
                    height, width = frame.shape[:2]
                    command = self._calculate_control_command(self.current_target, width, height)
                    self._send_control_command(command, robot_id=robot_id)
                    rt['last_control_command'] = command
                else:
                    if self.stats['last_control_command'] != "stop":
                        self._send_control_command("stop", robot_id=robot_id)
                        rt['last_control_command'] = 'stop'

        # 更新处理时间
        self.stats['processing_time'] = (time.time() - start_time) * 1000

        return output_frame, {
            'tracked_persons': self.tracked_persons,
            'detections': detections,
            'current_target': self.current_target,
            'stats': self.stats.copy()
        }

    def get_stats(self):
        """获取统计信息"""
        return self.stats.copy()

    def update_control_params(self, center_threshold=None, min_area=None, max_area=None):
        """更新控制参数"""
        if center_threshold is not None:
            self.center_threshold = center_threshold
        if min_area is not None:
            self.min_area_ratio = min_area
        if max_area is not None:
            self.max_area_ratio = max_area

        print(f"🔄 更新控制参数: 中心阈值={self.center_threshold}, 最小面积={self.min_area_ratio}, 最大面积={self.max_area_ratio}")

    def reset(self):
        """重置跟踪器"""
        with self.lock:
            self.current_target = None
            self.tracked_persons = []
            self.frame_count = 0
            self.control_history = []
            self._frame_times = []
            self.stats = {
                'detected_count': 0,
                'tracking_count': 0,
                'fps': 0,
                'detection_time': 0,
                'last_control_command': None,
                'last_control_time': 0,
                'last_detection_time': 0,
                'total_frames': 0,
                'processing_time': 0
            }
        print("🔄 人体跟踪器已重置")


# 全局人体跟踪器实例
_human_tracker_instance = None


def get_human_tracker(config=None):
    """获取全局人体跟踪器实例"""
    global _human_tracker_instance
    if _human_tracker_instance is None:
        _human_tracker_instance = HumanTracker(config)
    return _human_tracker_instance
