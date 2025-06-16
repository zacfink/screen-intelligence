import pyautogui


class Keyboard:
    def typeText(self, text):
        pyautogui.write(text, interval=0.25)
        return f"Typed {text}"

    def pressKey(self, key):
        pyautogui.press(key.lower())
        return f"Pressed {key}"
