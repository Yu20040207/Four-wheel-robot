import math
import unittest

from line_follow_model import LineFollowController


class LineFollowControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = LineFollowController()

    def feed_stable(self, sensor_byte, samples=3):
        command = None
        for _ in range(samples):
            command = self.controller.update(sensor_byte)
        return command

    def test_centered_line_drives_forward_without_lateral_motion(self):
        command = self.feed_stable(0x18)

        self.assertGreater(command.move_x, 0.0)
        self.assertEqual(command.move_y, 0.0)
        self.assertAlmostEqual(command.move_z, 0.0, places=4)

    def test_small_offset_uses_smaller_turn_than_large_offset(self):
        near = self.feed_stable(0x10)
        self.controller.reset()
        far = self.feed_stable(0x80)

        self.assertGreater(near.move_z, 0.0)
        self.assertGreater(far.move_z, near.move_z)
        self.assertLess(far.move_x, near.move_x)

    def test_opposite_offsets_are_symmetric(self):
        left = self.feed_stable(0x80)
        self.controller.reset()
        right = self.feed_stable(0x01)

        self.assertAlmostEqual(left.move_x, right.move_x, places=4)
        self.assertAlmostEqual(left.move_z, -right.move_z, places=4)
        self.assertEqual(left.move_y, 0.0)
        self.assertEqual(right.move_y, 0.0)

    def test_one_sample_glitch_does_not_reverse_turn_direction(self):
        self.feed_stable(0x40)
        before = self.controller.update(0x40)
        glitch = self.controller.update(0x02)

        self.assertGreater(before.move_z, 0.0)
        self.assertGreaterEqual(glitch.move_z, 0.0)

    def test_turn_output_changes_by_no_more_than_slew_limit(self):
        self.feed_stable(0x80)
        previous = self.controller.command

        for sensor_byte in (0x01, 0x01, 0x01, 0x01):
            current = self.controller.update(sensor_byte)
            self.assertLessEqual(
                abs(current.move_z - previous.move_z),
                self.controller.turn_slew_limit + 1e-6,
            )
            previous = current

    def test_short_line_loss_searches_in_last_known_direction(self):
        self.feed_stable(0x40)
        lost = self.feed_stable(0x00)

        self.assertGreater(lost.move_z, 0.0)
        self.assertGreater(lost.move_x, 0.0)

    def test_prolonged_line_loss_stops(self):
        self.feed_stable(0x40)

        command = None
        for _ in range(self.controller.lost_search_samples + 5):
            command = self.controller.update(0x00)

        self.assertEqual(command.move_x, 0.0)
        self.assertEqual(command.move_y, 0.0)
        self.assertEqual(command.move_z, 0.0)

    def test_all_sensors_active_stops_immediately(self):
        self.feed_stable(0x40)
        command = self.feed_stable(0xFF)

        self.assertEqual(command.move_x, 0.0)
        self.assertEqual(command.move_y, 0.0)
        self.assertEqual(command.move_z, 0.0)

    def test_all_sensor_combinations_are_finite_and_bounded(self):
        for sensor_byte in range(256):
            self.controller.reset()
            command = self.feed_stable(sensor_byte)

            self.assertTrue(math.isfinite(command.move_x), sensor_byte)
            self.assertTrue(math.isfinite(command.move_y), sensor_byte)
            self.assertTrue(math.isfinite(command.move_z), sensor_byte)
            self.assertGreaterEqual(command.move_x, 0.0, sensor_byte)
            self.assertLessEqual(command.move_x, self.controller.forward_speed, sensor_byte)
            self.assertEqual(command.move_y, 0.0, sensor_byte)
            self.assertLessEqual(abs(command.move_z), self.controller.max_turn, sensor_byte)


if __name__ == "__main__":
    unittest.main()
