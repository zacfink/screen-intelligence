import pyautogui


class Mouse:

    def getMousePosition(self):
        currentMouseX, currentMouseY = pyautogui.position()
        return currentMouseX, currentMouseY

    def moveMouse(self, x, y):
        pyautogui.moveTo(x, y, 0.2, pyautogui.easeInQuad)
        return f"Mouse moved to {x}, {y}"

    def leftClick(self):
        pyautogui.click(button="left")
        return f"Left clicked"

    def rightClick(self):
        pyautogui.click(button="right")
        return f"Right clicked"

    def doubleClick(self):
        pyautogui.click(interval=0.25)
        return f"Double clicked"

    def scroll(self, direction, amount):
        if direction.lower() == "up":
            pyautogui.scroll(amount)
            return f"Scrolled up"
        if direction.lower() == "down":
            pyautogui.scroll(amount * -1)
            return f"Scrolled down"
        if direction.lower() == "right":
            pyautogui.hscroll(amount)
            return f"Scrolled right"
        if direction.lower() == "left":
            pyautogui.hscroll(amount * -1)
            return f"Scrolled left"
