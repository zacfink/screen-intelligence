import re
import pyautogui
import os
from PIL import Image
import pytesseract
import time
from .searchScreenText.searchScreenText import getScreenText


class AlernativeActions:

    def wait(self, seconds):
        time.sleep(seconds)
        return f"Waited for {seconds} seconds"

    def openApplication(self, app):
        os.system(f"open -a {app}")
        return f"Opened {app}"

    def closeApplication(self, app):
        os.system(f"close -a {app}")
        return f"Closed {app}"

    def switchWindow(self, app):
        os.system(f"open -a {app}")
        return f"Showing {app}"

    def screenshot(self, label):
        pyautogui.screenshot(label)
        return f"Screenshot '{label}' taken"

    def logNote(self, path, note):
        with open(path, "a") as f:
            f.write(note + "\n")
        return f"Note '{note}' logged"

    def confirmAction(self, question):
        confirmation = pyautogui.confirm(
            text=question, title="Confirm Action", buttons=["Yes", "No"]
        )
        return f"Confirmation reponse: {confirmation}"

    def searchScreenText(self, query):
        screenshot_path = f"desktop-intelligence/screenshots/takenScreenshots/searchForText/searchFor{query}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(screenshot_path)
        textX, textY = getScreenText(screenshot_path, query)
        return textX, textY

    def moveAndClickText(self, text):
        textX, textY = self.searchScreenText(text)
        pyautogui.moveTo(textX, textY, 1, pyautogui.easeInQuad)
        pyautogui.click()

    def exitSquence(self):
        return False

    def retryLastAction(self):
        return "Retry"
