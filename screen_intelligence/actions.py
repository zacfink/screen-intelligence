"""The fixed action vocabulary in action_list.json, carried out with pyautogui."""
import json
import subprocess
import time
from pathlib import Path

import pyautogui

from . import RUNTIME
from .ocr import find_text

ACTION_LIST = json.loads((Path(__file__).parent / "action_list.json").read_text())
STEP_LOG = RUNTIME / "steps.json"
NOTES = RUNTIME / "notes.txt"


class StopRun(Exception):
    pass


def log_step(step):
    steps = json.loads(STEP_LOG.read_text())
    steps.append(step)
    STEP_LOG.write_text(json.dumps(steps, indent=2))


def last_step():
    steps = json.loads(STEP_LOG.read_text())
    return steps[-1] if steps else None


def confirm(question):
    return pyautogui.confirm(text=question, title="Confirm Action", buttons=["Yes", "No"])


def scroll(direction, amount):
    match direction.lower():
        case "up":
            pyautogui.scroll(amount)
        case "down":
            pyautogui.scroll(-amount)
        case "right":
            pyautogui.hscroll(amount)
        case "left":
            pyautogui.hscroll(-amount)


def search_screen_text(query):
    path = RUNTIME / "search.png"
    pyautogui.screenshot().save(path)
    return find_text(path, query)


def move_and_click_text(text):
    found = search_screen_text(text)
    if found is None:
        # clicking (0, 0) would hit the Apple menu and trip pyautogui's fail-safe; the after-check replans instead
        print(f"Couldn't find {text!r} on screen; not clicking.")
        return
    pyautogui.moveTo(found[0], found[1], 1, pyautogui.easeInQuad)
    pyautogui.click()


def execute_action(tag, args):
    match tag:
        case "move_mouse":
            pyautogui.moveTo(args[0], args[1], 0.2, pyautogui.easeInQuad)
        case "left_click":
            pyautogui.click(button="left")
        case "right_click":
            pyautogui.click(button="right")
        case "double_click":
            pyautogui.doubleClick()
        case "scroll":
            scroll(args[0], args[1])
        case "type_text":
            pyautogui.write(args[0], interval=0.25)
        case "press_key":
            pyautogui.press(args[0].lower())
        case "wait":
            time.sleep(args[0])
        # App names come from the model, so they go to `open` as an argument, never through a shell.
        case "open_application" | "switch_window":
            subprocess.run(["open", "-a", args[0]])
        case "close_application":
            subprocess.run(["osascript", "-e", "on run {a}", "-e", "tell application a to quit", "-e", "end run", args[0]])
        case "screenshot":
            name = "".join(c for c in args[0] if c.isalnum() or c in " -_") or "screenshot"
            pyautogui.screenshot(RUNTIME / f"{name}.png")
        case "log_note":
            with open(NOTES, "a") as f:
                f.write(args[0] + "\n")
        case "confirm_action":
            confirm(args[0])
        case "search_screen_text":
            search_screen_text(args[0])
        case "move_and_click_text":
            move_and_click_text(args[0])
        case "exit_sequence":
            raise StopRun("The plan ended the run.")
        case "retry_last_action":
            step = last_step()
            if step is not None and step["tag"] != "retry_last_action":
                execute_action(step["tag"], step.get("args", []))
        case _:
            raise StopRun(f"Unknown action {tag!r}; stopping rather than guessing.")
