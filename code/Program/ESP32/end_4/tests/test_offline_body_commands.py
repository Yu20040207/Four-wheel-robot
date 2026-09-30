import re
import unittest
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "end_4" / "end_4.ino"


class OfflineBodyCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_body_reset_alias_uses_existing_reset_path(self):
        self.assertRegex(
            self.source,
            re.compile(
                r'else\s+if\s*\(data\s*==\s*"3"\s*\|\|\s*'
                r'data\s*==\s*"body_reset"\s*\)\s*\{\s*'
                r'invokeLocalMqttCommand\(button3_topic,\s*"3"\);',
                re.DOTALL,
            ),
        )

    def test_body_stand_alias_uses_existing_standup_path(self):
        self.assertRegex(
            self.source,
            re.compile(
                r'else\s+if\s*\(data\s*==\s*"4"\s*\|\|\s*'
                r'data\s*==\s*"body_stand"\s*\)\s*\{',
                re.DOTALL,
            ),
        )


if __name__ == "__main__":
    unittest.main()
