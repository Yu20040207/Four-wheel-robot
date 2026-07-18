"""
垃圾检测与跟踪模块
使用 garbage.pt YOLO 模型识别垃圾，PID 连续调速对准并触发捡垃圾流程
底盘协议: V025L08 = 前进0.25+左平移0.08, V000R05 = 仅右平移0.05, B020N00 = 后退0.20, S = 停止
"""

import cv2
import numpy as np
import time
import threading
import json
import os
import sys
import math


def _get_app_base_dir():
    """项目根目录（兼容开发环境与 PyInstaller 打包 exe）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resolve_garbage_model_path(configured_path=None):
    """将模型路径解析为绝对路径，避免因工作目录不同加载到错误文件"""
    if not configured_path:
        return os.path.join(_get_app_base_dir(), 'garbage.pt')
    if os.path.isabs(configured_path):
        return configured_path
    return os.path.join(_get_app_base_dir(), configured_path)


def _get_model_path():
    return resolve_garbage_model_path('garbage.pt')


def format_velocity_command(move_x, move_y, turn_min=0.028, forward_min=0.012):
    """
    将 PID 输出转为底盘速度指令 (7 字符)
    move_x: 前进为正, move_y: 左平移为正 (L=正, R=负)
    """
    if abs(move_y) < turn_min:
        move_y = 0.0
    if abs(move_x) < forward_min:
        move_x = 0.0

    if abs(move_x) < forward_min and abs(move_y) < turn_min:
        return 'S'

    if move_x >= forward_min:
        xi = min(999, int(round(move_x * 100)))
        if abs(move_y) >= turn_min:
            yi = min(99, int(round(abs(move_y) * 100)))
            lat = 'L' if move_y > 0 else 'R'
            return f'V{xi:03d}{lat}{yi:02d}'
        return f'V{xi:03d}N00'

    if move_x <= -forward_min:
        xi = min(999, int(round(abs(move_x) * 100)))
        return f'B{xi:03d}N00'

    yi = min(99, int(round(abs(move_y) * 100)))
    lat = 'L' if move_y > 0 else 'R'
    return f'V000{lat}{yi:02d}'


class _GarbageVelocityController:
    """
    横向对准：死区 + 滞回锁定 + 非线性小偏差增益 + 振荡抑制
    纵向接近：仅当横向已对准 (|error| < align_gate) 时才允许前进
    """

    def __init__(self, config):
        self.y_kp = config.get('garbage_vel_y_kp', 0.28)
        self.y_kd = config.get('garbage_vel_y_kd', 0.06)
        self.y_ki = config.get('garbage_vel_y_ki', 0.006)
        self.y_max = config.get('garbage_vel_y_max', 0.07)
        self.y_integral_limit = config.get('garbage_vel_y_integral_limit', 0.08)

        self.x_kp = config.get('garbage_vel_x_kp', 1.2)
        self.x_ki = config.get('garbage_vel_x_ki', 0.035)
        self.x_kd = config.get('garbage_vel_x_kd', 0.04)
        self.x_max = config.get('garbage_vel_x_max', 0.26)
        self.x_integral_limit = config.get('garbage_vel_x_integral_limit', 0.18)

        self.offset_smooth = config.get('garbage_offset_smooth', 0.16)
        self.deadzone = config.get('garbage_center_deadzone', 0.055)
        self.turn_release = config.get('garbage_turn_release', 0.10)
        self.forward_abort = config.get('garbage_forward_abort', 0.15)
        self.large_offset = config.get('garbage_large_offset', 0.08)
        self.edge_offset = config.get('garbage_edge_offset', 0.22)
        self.offset_snap = config.get('garbage_offset_snap', 0.12)
        self.align_gate = config.get('garbage_align_gate', 0.07)
        self.min_area = config.get('garbage_min_area_ratio', 0.06)
        self.max_area = config.get('garbage_max_area_ratio', 0.30)
        self.aligned_area = config.get('garbage_aligned_area_ratio', 0.10)
        self.turn_min_cmd = config.get('garbage_turn_min_cmd', 0.028)
        self.forward_min_cmd = config.get('garbage_forward_min_cmd', 0.012)
        self._output_smooth = config.get('garbage_vel_output_smooth', 0.32)
        self._settle_frames = config.get('garbage_turn_settle_frames', 4)
        # 垃圾在左(raw<0) → move_y>0 → L；在右(raw>0) → move_y<0 → R
        self.turn_sign = float(config.get('garbage_turn_sign', 1))
        self.forward_y_scale = config.get('garbage_forward_y_scale', 0.45)

        self._smooth_offset = None
        self._y_integral = 0.0
        self._x_integral = 0.0
        self._last_y_error = 0.0
        self._last_x_error = 0.0
        self._last_move_x = 0.0
        self._last_move_y = 0.0
        self._turn_locked = False
        self._settled_streak = 0
        self._last_error_sign = 0
        self._sign_flip_count = 0
        self._oscillation_cooldown = 0.0
        self._approach_frozen = False
        self._approach_active = False
        self._raw_offset_history = []

    def reset(self):
        self._smooth_offset = None
        self._y_integral = 0.0
        self._x_integral = 0.0
        self._last_y_error = 0.0
        self._last_x_error = 0.0
        self._last_move_x = 0.0
        self._last_move_y = 0.0
        self._turn_locked = False
        self._settled_streak = 0
        self._last_error_sign = 0
        self._sign_flip_count = 0
        self._oscillation_cooldown = 0.0
        self._approach_frozen = False
        self._approach_active = False
        self._raw_offset_history = []

    def _nonlinear_gain(self, error):
        """小偏差时增益按 error^2 衰减，减少来回微调"""
        ae = abs(error)
        if ae <= self.deadzone:
            return 0.0
        norm = min(1.0, (ae - self.deadzone) / max(self.turn_release - self.deadzone, 0.01))
        return norm * norm

    def _track_oscillation(self, error, raw_error, now):
        # 仅在中等偏差内统计抖动；大偏差是真实偏转不是振荡
        if abs(raw_error) > self.large_offset:
            self._sign_flip_count = 0
            return False

        sign = 1 if error > 0.005 else (-1 if error < -0.005 else 0)
        if sign != 0 and self._last_error_sign != 0 and sign != self._last_error_sign:
            self._sign_flip_count += 1
            if self._sign_flip_count >= 3:
                self._oscillation_cooldown = now + 0.45
                self._y_integral = 0.0
                self._sign_flip_count = 0
        if sign != 0:
            self._last_error_sign = sign
        return now < self._oscillation_cooldown

    def _large_offset_gain(self, raw_error):
        ae = abs(raw_error)
        if ae <= self.large_offset:
            return 0.0
        span = max(self.edge_offset - self.large_offset, 0.05)
        norm = min(1.0, (ae - self.large_offset) / span)
        return 0.55 + 0.45 * norm

    def _track_runaway(self, raw_error, move_y):
        """已停用：易把正确修正误判为跑飞。保留接口避免后续误加。"""
        return move_y

    def update(self, offset_x, area_ratio, dt, now=None, offset_x_raw=None):
        now = now or time.time()
        offset_x_raw = offset_x if offset_x_raw is None else offset_x_raw

        if self._smooth_offset is None:
            self._smooth_offset = offset_x
        elif abs(offset_x_raw - self._smooth_offset) > self.offset_snap:
            # 检测框突然偏到一侧时，立即同步平滑值，避免仍按旧中心控制
            self._smooth_offset = offset_x_raw
        else:
            a = self.offset_smooth
            self._smooth_offset = a * offset_x + (1.0 - a) * self._smooth_offset

        error_y = self._smooth_offset
        raw_abs = abs(offset_x_raw)
        large_misalign = raw_abs > self.large_offset
        edge_misalign = raw_abs > self.edge_offset
        move_y = 0.0
        move_x = 0.0

        if large_misalign:
            self._turn_locked = False
            self._approach_frozen = False
            self._approach_active = False
            self._settled_streak = 0
            self._oscillation_cooldown = 0.0

        oscillating = self._track_oscillation(error_y, offset_x_raw, now)

        # 进入/退出「可前进」状态：|raw| 在 align_gate 内连续稳定即可，不必死区完全为零
        if raw_abs <= self.align_gate:
            self._settled_streak += 1
            if self._settled_streak >= self._settle_frames:
                self._turn_locked = True
                self._approach_active = True
        elif raw_abs > self.turn_release:
            self._settled_streak = 0
            self._turn_locked = False
            self._approach_active = False
        else:
            self._settled_streak = 0

        in_approach = self._approach_active and raw_abs <= self.turn_release

        # --- 横向控制 ---
        if edge_misalign:
            gain = self._large_offset_gain(offset_x_raw)
            move_y = max(
                -self.y_max,
                min(self.y_max, -(self.y_kp * 1.35 * offset_x_raw * max(gain, 0.8))),
            )
            self._y_integral = 0.0
        elif large_misalign and not in_approach:
            gain = self._large_offset_gain(offset_x_raw)
            control_err = offset_x_raw
            d_y = 0.0
            if dt > 0:
                d_y = (control_err - self._last_y_error) / dt
            self._last_y_error = control_err
            raw_y = -(self.y_kp * control_err * max(gain, 0.7) + self.y_kd * d_y * 0.5)
            move_y = max(-self.y_max, min(self.y_max, raw_y))
        elif oscillating:
            move_y = 0.0
            self._y_integral = 0.0
        elif in_approach:
            # 前进阶段：边走边用较小增益修正横向，保持目标居中
            control_err = offset_x_raw
            y_cap = self.y_max * self.forward_y_scale
            if abs(control_err) <= self.deadzone:
                move_y = 0.0
                self._y_integral *= 0.7
            else:
                d_y = 0.0
                if dt > 0:
                    d_y = (control_err - self._last_y_error) / dt
                self._last_y_error = control_err
                gain = max(0.35, self._nonlinear_gain(control_err))
                raw_y = -(self.y_kp * control_err * gain * self.forward_y_scale + self.y_kd * d_y * 0.35)
                move_y = max(-y_cap, min(y_cap, raw_y))
        elif self._turn_locked:
            move_y = 0.0
            self._y_integral *= 0.7
        else:
            control_err = offset_x_raw if raw_abs > self.deadzone else error_y
            gain = self._nonlinear_gain(control_err)
            d_y = 0.0
            if dt > 0:
                d_y = (control_err - self._last_y_error) / dt
            self._last_y_error = control_err

            i_term = 0.0
            if abs(control_err) > self.turn_release and dt > 0:
                self._y_integral += control_err * dt
                self._y_integral = max(
                    -self.y_integral_limit,
                    min(self.y_integral_limit, self._y_integral),
                )
                i_term = self.y_ki * self._y_integral

            raw_y = -(self.y_kp * control_err * gain + i_term + self.y_kd * d_y * gain)
            move_y = max(-self.y_max, min(self.y_max, raw_y))

        move_y *= self.turn_sign

        lateral_ok = raw_abs <= self.turn_release

        # --- 纵向：进入 approach 后持续前进直到够近 ---
        if in_approach and not oscillating and lateral_ok:
            if area_ratio < self.aligned_area:
                error_x = self.aligned_area - area_ratio
                if dt > 0:
                    self._x_integral += error_x * dt
                    self._x_integral = max(0.0, min(self.x_integral_limit, self._x_integral))
                    d_x = (error_x - self._last_x_error) / dt if dt > 0 else 0.0
                else:
                    d_x = 0.0
                self._last_x_error = error_x
                raw_x = self.x_kp * error_x + self.x_ki * self._x_integral + self.x_kd * d_x
                move_x = max(0.0, min(self.x_max, raw_x))
            elif area_ratio > self.max_area:
                error_x = area_ratio - self.max_area
                self._x_integral = 0.0
                self._last_x_error = error_x
                raw_x = self.x_kp * error_x
                move_x = -max(0.0, min(self.x_max * 0.5, raw_x))
            else:
                self._x_integral *= 0.9
                self._last_x_error = 0.0
        else:
            self._x_integral *= 0.85
            move_x = 0.0

        # 未进入 approach：大偏差只转不进；approach 内允许 VxxxLyy 边走边修
        if not in_approach:
            if abs(move_y) >= self.turn_min_cmd:
                move_x = 0.0
            elif large_misalign or edge_misalign:
                move_x = 0.0

        beta = self._output_smooth
        # 停止转向时清零历史，避免平滑把旧转向“拖尾”成左右抖
        if abs(move_y) < 1e-9:
            self._last_move_y = 0.0
        else:
            move_y = beta * move_y + (1.0 - beta) * self._last_move_y
            self._last_move_y = move_y
        move_x = beta * move_x + (1.0 - beta) * self._last_move_x
        self._last_move_x = move_x

        # 已对准但尚未够近时，保证有最小前进速度
        if (
            in_approach
            and area_ratio < self.aligned_area
            and lateral_ok
            and move_x < self.forward_min_cmd
        ):
            move_x = self.forward_min_cmd

        cmd = format_velocity_command(
            move_x, move_y, self.turn_min_cmd, self.forward_min_cmd,
        )
        count_aligned = (
            cmd == 'S'
            and in_approach
            and raw_abs <= self.align_gate
            and area_ratio >= self.aligned_area
        )
        meta = {
            'smooth_offset': round(error_y, 3),
            'raw_offset': round(offset_x_raw, 3),
            'move_x': round(move_x, 3),
            'move_y': round(move_y, 3),
            'turn_locked': self._turn_locked,
            'approach_active': in_approach,
            'approach_frozen': self._approach_frozen,
            'oscillating': oscillating,
            'large_misalign': large_misalign,
            'area_ratio': round(area_ratio, 3),
        }
        return cmd, count_aligned, meta


class GarbageTracker:
    """垃圾检测跟踪器 - 避障模式下对准垃圾并触发捡取"""

    def __init__(self, config=None):
        self.config = config or {}

        self.model_path = resolve_garbage_model_path(self.config.get('garbage_model_path'))
        self.confidence_threshold = self.config.get('garbage_confidence_threshold', 0.45)
        self.center_threshold = self.config.get('garbage_center_threshold', 0.12)
        self.min_area_ratio = self.config.get('garbage_min_area_ratio', 0.06)
        self.max_area_ratio = self.config.get('garbage_max_area_ratio', 0.30)
        self.aligned_area_ratio = self.config.get('garbage_aligned_area_ratio', 0.10)
        self.control_interval = self.config.get('garbage_control_interval', 0.15)
        self.detection_interval = self.config.get('garbage_detection_interval', 2)
        self.aligned_frames_required = self.config.get('garbage_aligned_frames', 6)
        self.target_pickup_distance_cm = self.config.get('garbage_target_distance_cm', 25)
        self.head_tilt_interval = self.config.get('garbage_head_interval', 0.4)
        self.tilt_down_threshold = self.config.get('garbage_tilt_threshold', 0.55)

        self.target_center_weight = self.config.get('garbage_target_center_weight', 0.45)
        self.target_conf_weight = self.config.get('garbage_target_conf_weight', 0.30)
        self.target_area_weight = self.config.get('garbage_target_area_weight', 0.25)
        self.target_lock_iou_threshold = self.config.get('garbage_target_lock_iou', 0.25)
        self.target_lock_bonus = self.config.get('garbage_target_lock_bonus', 0.35)
        self.target_lock_lost_max = self.config.get('garbage_target_lock_lost_max', 8)

        self.tracking_enabled = False
        self.locked_target_bbox = None
        self.lock_lost_frames = 0
        self.tracking_active = False
        self.pickup_in_progress = False
        self.current_target = None
        self.detections = []
        self.frame_count = 0
        self.aligned_frame_count = 0
        self.lock = threading.Lock()
        self.mqtt_manager = None
        self.last_command_time = 0
        self.last_head_time = 0
        self.last_pickup_trigger_time = 0
        self.pickup_cooldown = 8.0
        self._mode_enabled = False
        self._vel_controller = _GarbageVelocityController(self.config)
        self._last_control_calc_time = 0.0
        self._smooth_control_cx = None
        self._last_sent_cmd = 'S'

        self.stats = {
            'detected_count': 0,
            'tracking_count': 0,
            'fps': 0,
            'detection_time': 0,
            'last_control_command': None,
            'last_control_time': 0,
            'last_detection_time': 0,
            'total_frames': 0,
            'processing_time': 0,
            'model_loaded': False,
            'model_path': None,
            'model_mtime': None,
            'model_classes': [],
            'pickup_triggered': False,
            'move_x': 0.0,
            'move_y': 0.0,
        }

        self.control_history = []
        self.max_history_size = 20
        self._frame_times = []
        self._max_frame_times = 30

        self.model = None
        self._load_model()

    def _update_model_stats(self):
        self.stats['model_path'] = self.model_path
        self.stats['model_mtime'] = None
        self.stats['model_classes'] = []
        if self.model_path and os.path.exists(self.model_path):
            self.stats['model_mtime'] = os.path.getmtime(self.model_path)
        if self.model is not None and hasattr(self.model, 'names') and self.model.names:
            self.stats['model_classes'] = [str(v) for v in self.model.names.values()]

    def _load_model(self):
        self.model = None
        self.stats['model_loaded'] = False
        try:
            if not os.path.exists(self.model_path):
                print(f"⚠️ 垃圾模型未找到: {self.model_path}")
                self._update_model_stats()
                return
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            self.stats['model_loaded'] = True
            self._update_model_stats()
            mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.stats['model_mtime']))
            classes = self.stats['model_classes']
            print(f"✅ 垃圾检测模型已加载: {self.model_path}")
            print(f"   文件修改时间: {mtime_str}")
            print(f"   检测类别({len(classes)}): {', '.join(classes) if classes else '未知'}")
        except ImportError:
            print("⚠️ 未安装 ultralytics，请执行: pip install ultralytics")
            self._update_model_stats()
        except Exception as e:
            print(f"❌ 加载垃圾模型失败: {e}")
            self._update_model_stats()

    def reload_model(self):
        with self.lock:
            print(f"🔄 重新加载垃圾模型: {self.model_path}")
            self._load_model()
            return self.stats['model_loaded']

    def set_mqtt_manager(self, mqtt_manager):
        self.mqtt_manager = mqtt_manager

    def enable_tracking(self, publish_mode=False, robot_id=None):
        if not robot_id:
            return False
        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)
        with self.lock:
            if self.tracking_enabled and self._mode_enabled and rt.get('garbage_tracking_enabled'):
                return False
            self.tracking_enabled = True
            self.tracking_active = True
            self.pickup_in_progress = False
            self.aligned_frame_count = 0
            self._mode_enabled = True
            self._vel_controller.reset()
            self._last_sent_cmd = 'S'
            self._smooth_control_cx = None
            self._active_robot_id = robot_id
            rt['garbage_tracking_enabled'] = True
            rt['garbage_tracking_active'] = True
            rt['garbage_pickup_in_progress'] = False
        print(f"🗑️ 垃圾跟踪已启用 robot_id={robot_id}")
        if publish_mode:
            self._publish_mode(True, robot_id=robot_id)
        return True

    def disable_tracking(self, publish_mode=False, robot_id=None):
        if not robot_id:
            robot_id = getattr(self, '_active_robot_id', None)
        if not robot_id:
            return False
        from robot_context import get_robot_runtime, reset_robot_garbage
        try:
            self._send_chassis_command('S', force=True, robot_id=robot_id)
            with self.lock:
                self.tracking_enabled = False
                self.tracking_active = False
                self.pickup_in_progress = False
                self.current_target = None
                self.detections = []
                self.aligned_frame_count = 0
                self._mode_enabled = False
                self.locked_target_bbox = None
                self.lock_lost_frames = 0
                self._vel_controller.reset()
                self._last_sent_cmd = 'S'
                self._smooth_control_cx = None
                if getattr(self, '_active_robot_id', None) == robot_id:
                    self._active_robot_id = None
            reset_robot_garbage(robot_id)
            print(f"🗑️ 垃圾跟踪已禁用 robot_id={robot_id}")
            if publish_mode:
                self._publish_mode(False, robot_id=robot_id)
            return True
        except Exception as e:
            print(f"❌ 禁用垃圾跟踪失败: {e}")
            return False

    def _publish_mode(self, enabled, robot_id=None):
        if not robot_id or not self.mqtt_manager or not self.mqtt_manager.is_connected:
            return
        payload = json.dumps({
            "enabled": enabled,
            "timestamp": time.time(),
            "target_distance_cm": self.target_pickup_distance_cm,
            "source": "server",
        })
        self.mqtt_manager.publish_to_robot(
            'cmd/garbage_pickup/mode', payload, qos=1, robot_id=robot_id
        )

    def detect_garbage(self, frame):
        if frame is None or self.model is None:
            return []

        start_time = time.time()
        try:
            results = self.model(frame, conf=self.confidence_threshold, verbose=False)
            detections = []
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    cls_name = result.names.get(cls_id, 'garbage')
                    x, y = int(x1), int(y1)
                    w, h = int(x2 - x1), int(y2 - y1)
                    if w > 10 and h > 10:
                        detections.append((x, y, w, h, conf, cls_name))

            self.stats['detection_time'] = (time.time() - start_time) * 1000
            self.stats['detected_count'] = len(detections)
            self.stats['last_detection_time'] = time.time()
            return detections
        except Exception as e:
            print(f"❌ 垃圾检测错误: {e}")
            return []

    def _send_chassis_command(self, command, force=False, robot_id=None):
        """发送底盘速度指令 (V/B/S 格式)"""
        if not robot_id:
            return
        if not self.mqtt_manager or not self.mqtt_manager.is_connected:
            return
        current_time = time.time()
        if not force and current_time - self.last_command_time < 0.08:
            return
        if not force and command == self._last_sent_cmd and command != 'S':
            if current_time - self.last_command_time < self.control_interval:
                return
        self.last_command_time = current_time
        self._last_sent_cmd = command
        try:
            if self.mqtt_manager.publish_to_robot(
                'cmd/garbage_tracking/command', command, qos=0, robot_id=robot_id
            ):
                self.stats['last_control_command'] = command
                self.stats['last_control_time'] = current_time
                self.control_history.append({'command': command, 'time': current_time})
                if len(self.control_history) > self.max_history_size:
                    self.control_history.pop(0)
        except Exception as e:
            print(f"❌ 发送垃圾底盘指令失败: {e}")

    def _send_head_command(self, action, robot_id=None):
        if not robot_id:
            return
        if not self.mqtt_manager or not self.mqtt_manager.is_connected:
            return
        current_time = time.time()
        if current_time - self.last_head_time < self.head_tilt_interval:
            return
        self.last_head_time = current_time
        try:
            payload = json.dumps({"action": action, "timestamp": current_time})
            self.mqtt_manager.publish_to_robot(
                'cmd/garbage_tracking/head', payload, qos=0, robot_id=robot_id
            )
        except Exception as e:
            print(f"❌ 发送头部指令失败: {e}")

    def _trigger_pickup_sequence(self, robot_id=None):
        if not robot_id:
            return
        if not self.mqtt_manager or not self.mqtt_manager.is_connected:
            return
        current_time = time.time()
        if current_time - self.last_pickup_trigger_time < self.pickup_cooldown:
            return
        self.last_pickup_trigger_time = current_time
        self.pickup_in_progress = True
        self.stats['pickup_triggered'] = True
        payload = json.dumps({
            "phase": "aligned",
            "target_distance_cm": self.target_pickup_distance_cm,
            "timestamp": current_time,
        })
        self.mqtt_manager.publish_to_robot(
            'cmd/garbage_pickup/sequence', payload, qos=1, robot_id=robot_id
        )
        self._send_chassis_command('S', force=True, robot_id=robot_id)
        print(f"🗑️ 已触发捡垃圾流程，目标距离={self.target_pickup_distance_cm}cm")

    def _calculate_command(self, target, frame_width, frame_height, now=None, dt=None):
        if not target:
            return 'S'

        center_y = target['center'][1]
        x, y, w, h = target['bbox']
        area_ratio = (w * h) / (frame_width * frame_height)

        raw_cx = target['center'][0]
        if self._smooth_control_cx is None:
            self._smooth_control_cx = float(raw_cx)
        else:
            offset_x_raw_pre = (raw_cx - frame_width / 2) / (frame_width / 2)
            snap = self.config.get('garbage_offset_snap', 0.12)
            large = self.config.get('garbage_large_offset', 0.08)
            if abs(offset_x_raw_pre) > large:
                alpha = 0.55
            elif abs(offset_x_raw_pre - (
                (self._smooth_control_cx - frame_width / 2) / (frame_width / 2)
            )) > snap:
                alpha = 0.45
            else:
                alpha = self.config.get('garbage_control_cx_smooth', 0.15)
            self._smooth_control_cx = alpha * raw_cx + (1.0 - alpha) * self._smooth_control_cx
        offset_x = (self._smooth_control_cx - frame_width / 2) / (frame_width / 2)
        offset_x_raw = (raw_cx - frame_width / 2) / (frame_width / 2)

        norm_y = center_y / frame_height
        if norm_y > self.tilt_down_threshold:
            self._send_head_command("tilt_down")
        elif norm_y < 0.35:
            self._send_head_command("tilt_up")

        now = now or time.time()
        dt = dt if dt is not None else 0.0
        cmd, count_aligned, meta = self._vel_controller.update(
            offset_x, area_ratio, dt, now, offset_x_raw,
        )
        if count_aligned:
            self.aligned_frame_count += 1
        else:
            self.aligned_frame_count = 0

        self.stats['last_offset_x'] = meta['smooth_offset']
        self.stats['last_offset_raw'] = meta.get('raw_offset')
        self.stats['last_area_ratio'] = round(area_ratio, 3)
        self.stats['move_x'] = meta['move_x']
        self.stats['move_y'] = meta['move_y']
        self.stats['turn_locked'] = meta.get('turn_locked', False)
        self.stats['approach_active'] = meta.get('approach_active', False)
        self.stats['approach_frozen'] = meta.get('approach_frozen', False)
        self.stats['large_misalign'] = meta.get('large_misalign', False)
        self.stats['area_ratio'] = meta.get('area_ratio', 0)
        return cmd

    @staticmethod
    def _compute_iou(box_a, box_b):
        ax, ay, aw, ah = box_a
        bx, by, bw, bh = box_b
        ax2, ay2 = ax + aw, ay + ah
        bx2, by2 = bx + bw, by + bh

        inter_x1 = max(ax, bx)
        inter_y1 = max(ay, by)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h
        if inter_area <= 0:
            return 0.0

        union_area = aw * ah + bw * bh - inter_area
        if union_area <= 0:
            return 0.0
        return inter_area / union_area

    def _score_target(self, target, frame_width, frame_height):
        tx, ty = target['center']
        area_ratio = target['area'] / (frame_width * frame_height)
        cx_frame = frame_width / 2
        cy_frame = frame_height / 2

        dx = (tx - cx_frame) / max(cx_frame, 1)
        dy = (ty - cy_frame) / max(cy_frame, 1)
        dist = math.sqrt(dx * dx + dy * dy)
        center_score = max(0.0, 1.0 - dist / 1.2)

        conf_score = float(target.get('confidence', 0))

        if area_ratio < self.min_area_ratio:
            area_score = (area_ratio / max(self.min_area_ratio, 1e-6)) * 0.5
        elif area_ratio > self.max_area_ratio:
            area_score = 0.3
        else:
            area_score = 1.0

        score = (
            self.target_center_weight * center_score
            + self.target_conf_weight * conf_score
            + self.target_area_weight * area_score
        )
        target['center_score'] = round(center_score, 3)
        target['area_ratio'] = round(area_ratio, 4)
        target['track_score'] = round(score, 3)
        return score

    def _select_target(self, tracked, frame_width, frame_height):
        if not tracked:
            self.locked_target_bbox = None
            self.lock_lost_frames = 0
            return None

        best = None
        best_score = -1.0
        best_iou = 0.0

        for target in tracked:
            score = self._score_target(target, frame_width, frame_height)
            if self.locked_target_bbox is not None:
                iou = self._compute_iou(target['bbox'], self.locked_target_bbox)
                target['lock_iou'] = round(iou, 3)
                if iou >= self.target_lock_iou_threshold:
                    score += self.target_lock_bonus * iou
            else:
                target['lock_iou'] = 0.0

            if score > best_score:
                best_score = score
                best = target
                best_iou = target.get('lock_iou', 0.0)

        if best is None:
            return None

        if self.locked_target_bbox is not None and best_iou >= self.target_lock_iou_threshold:
            self.lock_lost_frames = 0
        elif self.locked_target_bbox is not None:
            self.lock_lost_frames += 1
            if self.lock_lost_frames >= self.target_lock_lost_max:
                self.locked_target_bbox = None
                self.lock_lost_frames = 0

        self.locked_target_bbox = best['bbox']
        best['track_score'] = round(best_score, 3)
        best['is_locked'] = True
        return best

    def _draw(self, frame, detections):
        if frame is None:
            return frame
        height, width = frame.shape[:2]
        center_x = width // 2
        align_gate = self.config.get('garbage_align_gate', 0.08)
        gate = max(int(align_gate * width / 2), int(width * 0.03))
        cv2.rectangle(frame, (center_x - gate, 0), (center_x + gate, height), (0, 200, 0), 1)
        cv2.line(frame, (center_x, 0), (center_x, height), (0, 255, 255), 1)

        for i, det in enumerate(detections):
            x, y, w, h, conf, cls_name = det
            is_target = self.current_target and self.current_target.get('index') == i
            color = (0, 255, 0) if is_target else (0, 140, 255)
            thickness = 2 if is_target else 1
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)
            label = f"{cls_name} {conf:.2f}"
            if is_target and self.current_target:
                label = f"TARGET {label} s={self.current_target.get('track_score', 0):.2f}"
            cv2.putText(frame, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        status = "GARBAGE: ON" if self.tracking_active else "GARBAGE: OFF"
        cv2.putText(frame, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if self.tracking_active else (0, 0, 255), 2)
        if self.stats['last_control_command']:
            tags = []
            if self.stats.get('turn_locked'):
                tags.append('LOCK')
            if self.stats.get('approach_active'):
                tags.append('FWD')
            if self.stats.get('large_misalign'):
                tags.append('BIG')
            lock_tag = (' ' + ' '.join(tags)) if tags else ''
            area_pct = int((self.stats.get('area_ratio') or 0) * 100)
            cv2.putText(frame, f"CMD: {self.stats['last_control_command']}{lock_tag} area:{area_pct}%",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)
        raw_off = self.stats.get('last_offset_raw', 0) or 0
        want = 'L' if raw_off < -0.03 else ('R' if raw_off > 0.03 else '-')
        cv2.putText(frame,
                    f"X:{self.stats.get('move_x', 0):+.2f} Y:{self.stats.get('move_y', 0):+.2f} "
                    f"raw:{raw_off:+.2f} want:{want}",
                    (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 255), 1)
        if self.pickup_in_progress:
            cv2.putText(frame, "PICKUP...", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return frame

    def process_frame(self, frame, robot_id=None):
        if frame is None:
            return frame, {'detections': [], 'current_target': None, 'stats': self.stats.copy()}

        from robot_context import get_robot_runtime
        rt = get_robot_runtime(robot_id)
        if not robot_id or not rt.get('garbage_tracking_enabled'):
            return frame, {'detections': [], 'current_target': None, 'stats': self.stats.copy()}

        self._active_robot_id = robot_id
        start_time = time.time()
        output = frame.copy()
        self.frame_count += 1
        self.stats['total_frames'] = self.frame_count

        if self.frame_count % self.detection_interval == 0:
            self.detections = self.detect_garbage(frame)

        tracked = []
        for i, det in enumerate(self.detections):
            x, y, w, h, conf, cls_name = det
            tracked.append({
                'index': i,
                'bbox': (x, y, w, h),
                'center': (x + w // 2, y + h // 2),
                'confidence': conf,
                'class_name': cls_name,
                'area': w * h,
            })

        if tracked:
            h, w = frame.shape[:2]
            self.current_target = self._select_target(tracked, w, h)
            self.stats['tracking_count'] = len(tracked)
            self.stats['multi_target'] = len(tracked) > 1
            if self.current_target:
                self.stats['target_class'] = self.current_target.get('class_name')
                self.stats['target_score'] = self.current_target.get('track_score')
        else:
            self.current_target = None
            self.aligned_frame_count = 0
            self.stats['tracking_count'] = 0
            self.stats['multi_target'] = False
            self.stats['target_class'] = None
            self.stats['target_score'] = None

        output = self._draw(output, self.detections)

        current_time = time.time()
        if self.tracking_active and not self.pickup_in_progress:
            last_ctrl = self.stats.get('last_control_time', 0) or 0
            if current_time - last_ctrl >= self.control_interval:
                if self.current_target:
                    h, w = frame.shape[:2]
                    dt = current_time - self._last_control_calc_time if self._last_control_calc_time > 0 else 0.0
                    self._last_control_calc_time = current_time
                    cmd = self._calculate_command(self.current_target, w, h, current_time, dt)
                    self._send_chassis_command(cmd, robot_id=robot_id)
                    rt['last_control_command'] = cmd
                    if cmd == 'S' and self.aligned_frame_count >= self.aligned_frames_required:
                        self._trigger_pickup_sequence(robot_id=robot_id)
                        rt['garbage_pickup_in_progress'] = True
                elif self._last_sent_cmd != 'S':
                    self._send_chassis_command('S', force=True, robot_id=robot_id)

        self._frame_times.append(current_time)
        if len(self._frame_times) > self._max_frame_times:
            self._frame_times.pop(0)
        if len(self._frame_times) > 1:
            dt_fps = self._frame_times[-1] - self._frame_times[0]
            if dt_fps > 0:
                self.stats['fps'] = (len(self._frame_times) - 1) / dt_fps

        self.stats['processing_time'] = (time.time() - start_time) * 1000
        return output, {
            'detections': self.detections,
            'current_target': self.current_target,
            'stats': self.stats.copy(),
            'aligned_frames': self.aligned_frame_count,
        }

    def on_pickup_complete(self):
        self.pickup_in_progress = False
        self.aligned_frame_count = 0
        self.stats['pickup_triggered'] = False
        self.locked_target_bbox = None
        self.lock_lost_frames = 0
        print("✅ 垃圾捡取流程完成，恢复跟踪")

    def get_stats(self):
        return self.stats.copy()

    def reset(self):
        with self.lock:
            self.current_target = None
            self.detections = []
            self.frame_count = 0
            self.aligned_frame_count = 0
            self.pickup_in_progress = False
            self.locked_target_bbox = None
            self.lock_lost_frames = 0
            self._vel_controller.reset()
            self._last_sent_cmd = 'S'
            self._smooth_control_cx = None
        print("🔄 垃圾跟踪器已重置")


_garbage_tracker_instance = None


def get_garbage_tracker(config=None):
    global _garbage_tracker_instance
    if _garbage_tracker_instance is None:
        _garbage_tracker_instance = GarbageTracker(config)
    return _garbage_tracker_instance
