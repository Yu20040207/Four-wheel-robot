from dataclasses import dataclass


@dataclass(frozen=True)
class MotionCommand:
    move_x: float = 0.0
    move_y: float = 0.0
    move_z: float = 0.0


class LineFollowController:
    """Host-side behavioral model for the STM32 line-follow controller."""

    forward_speed = 0.42
    minimum_forward_speed = 0.16
    max_turn = 1.20
    turn_slew_limit = 0.16
    lost_search_samples = 8
    kp = 0.18
    kd = 0.10
    error_filter_alpha = 0.55
    center_deadband = 0.25
    speed_reduction_per_error = 0.035
    lost_search_speed = 0.12
    lost_search_turn = 0.35
    weights = (-7, -5, -3, -1, 1, 3, 5, 7)

    def __init__(self):
        self.reset()

    def reset(self):
        self.command = MotionCommand()
        self.history = [0, 0, 0]
        self.sample_count = 0
        self.filtered_error = 0.0
        self.last_error = 0.0
        self.last_line_error = 0.0
        self.lost_count = 0

    @staticmethod
    def _majority(a, b, c):
        return (a & b) | (a & c) | (b & c)

    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    def _slew(self, target):
        delta = self._clamp(
            target - self.command.move_z,
            -self.turn_slew_limit,
            self.turn_slew_limit,
        )
        return self.command.move_z + delta

    def _position_error(self, sensor_byte):
        active_weights = [
            weight
            for bit, weight in enumerate(self.weights)
            if sensor_byte & (1 << bit)
        ]
        if not active_weights or len(active_weights) == 8:
            return None
        return sum(active_weights) / (2.0 * len(active_weights))

    def update(self, sensor_byte):
        sensor_byte &= 0xFF
        self.history = [sensor_byte, self.history[0], self.history[1]]
        self.sample_count = min(3, self.sample_count + 1)
        stable = (
            sensor_byte
            if self.sample_count < 3
            else self._majority(*self.history)
        )

        if stable == 0xFF:
            self.lost_count = 0
            self.command = MotionCommand()
            return self.command

        error = self._position_error(stable)
        if error is None:
            self.lost_count += 1
            if self.lost_count <= self.lost_search_samples and abs(self.last_line_error) > 0.01:
                target_turn = self.lost_search_turn if self.last_line_error > 0 else -self.lost_search_turn
                self.command = MotionCommand(
                    self.lost_search_speed,
                    0.0,
                    self._slew(target_turn),
                )
            else:
                self.command = MotionCommand()
            return self.command

        self.lost_count = 0
        self.filtered_error += self.error_filter_alpha * (error - self.filtered_error)
        if abs(self.filtered_error) <= self.center_deadband:
            self.filtered_error = 0.0

        derivative = self.filtered_error - self.last_error
        self.last_error = self.filtered_error
        if abs(error) > 0.01:
            self.last_line_error = error

        target_turn = self.kp * self.filtered_error + self.kd * derivative
        target_turn = self._clamp(target_turn, -self.max_turn, self.max_turn)
        turn = self._slew(target_turn)
        speed = self.forward_speed - self.speed_reduction_per_error * abs(self.filtered_error)
        speed = self._clamp(speed, self.minimum_forward_speed, self.forward_speed)
        self.command = MotionCommand(speed, 0.0, turn)
        return self.command
