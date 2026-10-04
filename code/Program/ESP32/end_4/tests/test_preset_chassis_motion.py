import re
import unittest
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "end_4" / "end_4.ino"


class PresetChassisMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_four_mqtt_topics_are_declared_and_subscribed(self):
        for topic in ("left_90", "right_90", "forward_1m", "retreat_1m"):
            with self.subTest(topic=topic):
                self.assertRegex(
                    self.source,
                    rf'const char \*{topic}_topic\s*=\s*"{topic}";',
                )
                self.assertRegex(
                    self.source,
                    rf'client\.subscribe\([^;]*{topic}_topic[^;]*\);',
                )

    def test_mqtt_topics_map_to_the_expected_shared_motion_commands(self):
        expected = {
            "left_90": "c",
            "right_90": "d",
            "forward_1m": "a",
            "retreat_1m": "b",
        }
        for topic, command in expected.items():
            with self.subTest(topic=topic):
                self.assertRegex(
                    self.source,
                    re.compile(
                        rf'topicStr\s*==[^\n]*{topic}_topic.*?'
                        rf'requestPresetMotion\(\s*\'{command}\'\s*\)',
                        re.DOTALL,
                    ),
                )

    def test_voice_commands_use_the_same_preset_motion_entrypoint(self):
        for command in "abcd":
            with self.subTest(command=command):
                self.assertRegex(
                    self.source,
                    rf'requestPresetMotion\(\s*\'{command}\'\s*\)',
                )

    def test_translation_and_turning_have_independent_calibration_times(self):
        self.assertRegex(
            self.source,
            r'PRESET_TRANSLATE_1M_DURATION_MS\s*=\s*1500',
        )
        self.assertRegex(
            self.source,
            r'PRESET_TURN_90_DURATION_MS\s*=\s*650',
        )

    def test_directional_obstacle_checks_cover_front_rear_and_turn_sides(self):
        checks = (
            "frontDistance",
            "frontLeftDistance",
            "frontRightDistance",
            "backDistance",
            "rearLeftDistance",
            "rearRightDistance",
        )
        for distance in checks:
            with self.subTest(distance=distance):
                self.assertIn(distance, self.source)

    def test_motion_waits_for_a_fresh_ultrasonic_frame(self):
        self.assertRegex(
            self.source,
            re.compile(
                r'presetMotionPending.*?lastUltrasonicFrameMs.*?'
                r'startPresetMotionNow',
                re.DOTALL,
            ),
        )

    def test_release_payloads_are_rejected(self):
        for payload in ("0", "false", "off"):
            with self.subTest(payload=payload):
                self.assertRegex(
                    self.source,
                    rf'normalized\s*!=\s*"{payload}"',
                )


if __name__ == "__main__":
    unittest.main()
