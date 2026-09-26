import pyautogui
import subprocess
import time
from .searchScreenText.searchScreenText import getScreenText


class AlernativeActions:

    def wait(self, seconds):
        time.sleep(seconds)
        return f"Waited for {seconds} seconds"

    # App names come from the model, so they go to `open` as an argument, never through a shell.
    def openApplication(self, app):
        subprocess.run(["open", "-a", app])
        return f"Opened {app}"

    def closeApplication(self, app):
        subprocess.run(["osascript", "-e", "on run {a}", "-e", "tell application a to quit", "-e", "end run", app])
        return f"Closed {app}"

    def switchWindow(self, app):
        subprocess.run(["open", "-a", app])
        return f"Showing {app}"

    def screenshot(self, label):
        name = "".join(c for c in label if c.isalnum() or c in " -_") or "screenshot"
        pyautogui.screenshot(f"desktop-intelligence/screenshots/takenScreenshots/{name}.png")
        return f"Screenshot '{label}' taken"

    def logNote(self, path, note):
        with open(path, "a") as f:
            f.write(note + "\n")
        return f"Note '{note}' logged"

    def confirmAction(self, question):
        return pyautogui.confirm(text=question, title="Confirm Action", buttons=["Yes", "No"])

    def searchScreenText(self, query):
        screenshot_path = "desktop-intelligence/screenshots/takenScreenshots/searchForText/search.png"
        pyautogui.screenshot().save(screenshot_path)
        return getScreenText(screenshot_path, query)

    def moveAndClickText(self, text):
        found = self.searchScreenText(text)
        if found is None:
            # clicking (0, 0) would hit the Apple menu and trip pyautogui's fail-safe; the after-check replans instead
            print(f"Couldn't find {text!r} on screen; not clicking.")
            return
        pyautogui.moveTo(found[0], found[1], 1, pyautogui.easeInQuad)
        pyautogui.click()
