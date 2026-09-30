"""Run a plan step by step: act, screenshot before and after, check it worked, replan if not."""
import json
import time

import pyautogui

from . import RUNTIME, llm
from .actions import ACTION_LIST, StopRun, confirm, execute_action, log_step
from .screenshots import capture_with_cursor, encode

MAX_REPLANS = 5  # each replan is two model calls; stop instead of looping on a step that keeps failing
BEFORE = RUNTIME / "before.png"
AFTER = RUNTIME / "after.png"


def run_step(step, plan, index, goal):
    """Runs plan[index]. Returns a replacement plan if the step didn't do what it promised, else None."""
    description = step.get("description", step["tag"])
    print(f"Step {index + 1}: {description}")

    capture_with_cursor(BEFORE)
    if step.get("requires_confirmation") and confirm(f"Proceed with: {description}?") != "Yes":
        # later steps assume this one happened, so skipping it and carrying on isn't safe
        raise StopRun(f"You declined: {description}")

    execute_action(step["tag"], step.get("args", []))
    time.sleep(0.75)
    capture_with_cursor(AFTER)
    log_step(step)

    if not step.get("conditions"):
        return None
    try:
        mouse_x, mouse_y = pyautogui.position()
        check = json.loads(llm.check_step(
            encode(BEFORE), encode(AFTER), step.get("visible_effect", ""), step["conditions"], mouse_x, mouse_y
        ))
        if check["action_completed"] and check["action_completed"] != "false":
            return None
        print("Step didn't work:", check["issue"])
        return json.loads(llm.replan(
            goal, check, mouse_x, mouse_y, plan[:index], step, plan[index + 1:], ACTION_LIST
        ))
    except Exception as e:
        print(f"Comparison failed: {e}")
        return None


def run_plan(plan, goal):
    index = replans = 0
    try:
        while index < len(plan):
            new_plan = run_step(plan[index], plan, index, goal)
            if new_plan is None:
                index += 1
                continue
            replans += 1
            if replans > MAX_REPLANS:
                raise StopRun(f"Still failing after {MAX_REPLANS} replans.")
            print("New plan:\n", json.dumps(new_plan, indent=2))
            plan, index = new_plan, 0
        print("All steps completed.")
    except StopRun as e:
        print(f"Stopped: {e}")
