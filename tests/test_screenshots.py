import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from screen_intelligence import screenshots


class Screenshots(unittest.TestCase):
    def test_encode_round_trips(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.png"
            path.write_bytes(b"\x89PNG fake")
            self.assertEqual(base64.b64decode(screenshots.encode(path)), b"\x89PNG fake")

    def test_cursor_is_drawn_as_a_red_dot(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(screenshots.pyautogui, "screenshot", return_value=Image.new("RGB", (100, 100), "white")), \
             patch.object(screenshots.pyautogui, "position", return_value=(50, 50)):
            path = Path(folder) / "a.png"
            screenshots.capture_with_cursor(path)
            image = Image.open(path)
            self.assertEqual(image.getpixel((50, 50)), (255, 0, 0))
            self.assertEqual(image.getpixel((5, 5)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
