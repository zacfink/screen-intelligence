import pyautogui


def getMousePos():
    currentMouseX, currentMouseY = pyautogui.position()
    return currentMouseX, currentMouseY
