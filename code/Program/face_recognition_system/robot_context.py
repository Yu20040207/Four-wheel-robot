"""每台机器人的运行状态隔离（多用户/多机器人）"""
import copy
import threading
import time
from typing import Any, Dict, Optional

_lock = threading.Lock()
_robot_runtime: Dict[str, Dict[str, Any]] = {}


def _default_runtime() -> Dict[str, Any]:
    return {
        'garbage_tracking_enabled': False,
        'garbage_tracking_active': False,
        'garbage_pickup_in_progress': False,
        'human_tracking_enabled': False,
        'human_tracking_active': False,
        'recognition_enabled': False,
        'frames_received': 0,
        'last_frame_time': 0.0,
        'fps': 0.0,
        'latency': 0,
        'current_garbage_target': None,
        'current_human_target': None,
        'garbage_detected': 0,
        'humans_detected': 0,
        'humans_tracking': 0,
        'last_control_command': None,
        'last_heartbeat_time': 0.0,
        'heartbeat_source': None,
        'device_state': 'offline',
        'battery_voltage': None,
        'battery_percent': None,
        'battery_level': 'unknown',
        'battery_valid': False,
        'battery_updated_at': 0.0,
    }


ROBOT_ONLINE_TIMEOUT_SEC = 90.0


def get_robot_runtime(robot_id: Optional[str]) -> Dict[str, Any]:
    if not robot_id:
        return _default_runtime()
    with _lock:
        if robot_id not in _robot_runtime:
            _robot_runtime[robot_id] = _default_runtime()
        return _robot_runtime[robot_id]


def get_robot_runtime_copy(robot_id: Optional[str]) -> Dict[str, Any]:
    return copy.copy(get_robot_runtime(robot_id))


def record_robot_frame(robot_id: Optional[str], latency_ms: Optional[int] = None) -> None:
    if not robot_id:
        return
    rt = get_robot_runtime(robot_id)
    with _lock:
        rt['frames_received'] = int(rt.get('frames_received', 0)) + 1
        now = time.time()
        last_t = rt.get('_fps_last_time') or 0.0
        if last_t <= 0:
            rt['_fps_last_time'] = now
            rt['_fps_last_count'] = rt['frames_received']
        elif now - last_t >= 1.0:
            diff = rt['frames_received'] - int(rt.get('_fps_last_count', 0))
            dt = now - last_t
            rt['fps'] = round(diff / dt, 1) if dt > 0 else 0.0
            rt['_fps_last_time'] = now
            rt['_fps_last_count'] = rt['frames_received']
        rt['last_frame_time'] = now
        if latency_ms is not None:
            rt['latency'] = latency_ms


def reset_robot_garbage(robot_id: str) -> None:
    rt = get_robot_runtime(robot_id)
    with _lock:
        rt['garbage_tracking_enabled'] = False
        rt['garbage_tracking_active'] = False
        rt['garbage_pickup_in_progress'] = False
        rt['current_garbage_target'] = None
        rt['garbage_detected'] = 0


def record_robot_heartbeat(
    robot_id: Optional[str],
    source: str = 'unknown',
    state: str = 'online',
) -> None:
    if not robot_id:
        return
    rt = get_robot_runtime(robot_id)
    with _lock:
        rt['last_heartbeat_time'] = time.time()
        rt['heartbeat_source'] = source
        rt['device_state'] = state


def is_robot_online(robot_id: Optional[str], timeout: float = ROBOT_ONLINE_TIMEOUT_SEC) -> bool:
    if not robot_id:
        return False
    rt = get_robot_runtime(robot_id)
    last_hb = float(rt.get('last_heartbeat_time') or 0.0)
    last_bat = float(rt.get('battery_updated_at') or 0.0)
    last = max(last_hb, last_bat)
    if last <= 0:
        return False
    return (time.time() - last) < timeout


def reset_robot_human(robot_id: str) -> None:
    rt = get_robot_runtime(robot_id)
    with _lock:
        rt['human_tracking_enabled'] = False
        rt['human_tracking_active'] = False
        rt['current_human_target'] = None
        rt['humans_detected'] = 0
        rt['humans_tracking'] = 0


def update_robot_battery(
    robot_id: Optional[str],
    voltage: Optional[float],
    percent: Optional[int],
    level: str = 'normal',
    valid: bool = False,
) -> None:
    if not robot_id:
        return
    rt = get_robot_runtime(robot_id)
    with _lock:
        rt['battery_voltage'] = voltage
        rt['battery_percent'] = percent
        rt['battery_level'] = level or 'normal'
        rt['battery_valid'] = bool(valid)
        rt['battery_updated_at'] = time.time()
