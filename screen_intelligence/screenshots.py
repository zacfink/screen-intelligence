import base64
import subprocess

import pyautogui
from PIL import ImageDraw


def capture(path):
    subprocess.run(["screencapture", "-C", str(path)])


def capture_with_cursor(path):
    """Screenshot with a red dot where the mouse is, so the vision model can see the cursor."""
    image = pyautogui.screenshot()
    x, y = pyautogui.position()
    ImageDraw.Draw(image).ellipse((x - 10, y - 10, x + 10, y + 10), fill="red", outline="black")
    image.save(path)


def encode(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
