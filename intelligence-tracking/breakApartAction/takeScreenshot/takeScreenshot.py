import os
import pyautogui
from PIL import ImageDraw


def takeScreenshot(imgName):
    os.system(
        f"screencapture -C intelligence-tracking/breakApartActions/images/{imgName}.png"
    )


def screenshotWithCursor(path):
    screenshot = pyautogui.screenshot()
    x, y = pyautogui.position()
    draw = ImageDraw.Draw(screenshot)
    draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="red", outline="black")
    screenshot.save(path)
