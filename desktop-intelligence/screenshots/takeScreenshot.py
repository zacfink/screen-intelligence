import os
import pyautogui
from PIL import ImageDraw


def takeScreenshot():
    os.system(
        "screencapture -C desktop-intelligence/screenshots/takenScreenshots/screen.png"
    )


def screenshotWithCursor(path):
    screenshot = pyautogui.screenshot()
    x, y = pyautogui.position()
    draw = ImageDraw.Draw(screenshot)
    draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="red", outline="black")
    screenshot.save(path)
