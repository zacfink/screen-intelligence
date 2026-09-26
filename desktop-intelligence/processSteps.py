import re
import json
import time
import os
from actions.allActions.alternativeActions.alternativeActions import AlernativeActions
from actions.allActions.keyboard.keyboard import Keyboard
from actions.allActions.mouse.mouse import Mouse
from actions.allActions.actionTracking.trackActions import appendStepToJson, getLastStep
from screenshots.encodeScreenshot.encodeScreenshot import encodeImage
from screenshots.takeScreenshot import screenshotWithCursor
from actionProcessing.confirmationAI.compareImages.compareImages import compareImages
from actionProcessing.confirmationAI.alterStepsReason.alterStepsReason import (
    alterStepsReason,
)


MAX_REPLANS = 5  # each replan is two model calls; stop instead of looping on a step that keeps failing


class StopRun(Exception):
    pass


def parsePlan(text):
    return json.loads(re.sub(r"```json|```", "", text).strip())


def beforeScreenshot():
    screenshotWithCursor(
        "desktop-intelligence/screenshots/takenScreenshots/before/beforeScreenshot.png"
    )


def afterScreenshot():
    screenshotWithCursor(
        "desktop-intelligence/screenshots/takenScreenshots/after/afterScreenshot.png"
    )


def executeAction(tag, args, altAct, kb, m):
    match tag:
        case "move_mouse":
            m.moveMouse(args[0], args[1])
        case "left_click":
            m.leftClick()
        case "right_click":
            m.rightClick()
        case "double_click":
            m.doubleClick()
        case "scroll":
            m.scroll(args[0], args[1])
        case "type_text":
            kb.typeText(args[0])
        case "press_key":
            kb.pressKey(args[0])
        case "wait":
            altAct.wait(args[0])
        case "open_application":
            altAct.openApplication(args[0])
        case "close_application":
            altAct.closeApplication(args[0])
        case "switch_window":
            altAct.switchWindow(args[0])
        case "screenshot":
            altAct.screenshot(args[0])
        case "log_note":
            altAct.logNote(
                "desktop-intelligence/actionProcessing/loggedNotes/loggedNotes.txt",
                args[0],
            )
        case "confirm_action":
            altAct.confirmAction(args[0])
        case "search_screen_text":
            altAct.searchScreenText(args[0])
        case "move_and_click_text":
            altAct.moveAndClickText(args[0])
        case "exit_sequence":
            raise StopRun("The plan ended the run.")
        case "retry_last_action":
            stepToRetry = getLastStep()
            if stepToRetry is not None and stepToRetry["tag"] != "retry_last_action":
                executeAction(stepToRetry["tag"], stepToRetry.get("args", []), altAct, kb, m)
        case _:
            raise StopRun(f"Unknown action {tag!r}; stopping rather than guessing.")


def translateTag(step, stepList, stepCount, usersInput, actionList):
    altAct = AlernativeActions()
    kb = Keyboard()
    m = Mouse()

    tag = step["tag"]
    args = step.get("args", [])
    description = step.get("description", tag)
    visibleChange = step.get("visible_effect", "")
    requires_confirmation = step.get("requires_confirmation", False)
    conditions = step.get("conditions", [])

    print(f"Step working!: {description}")

    beforeScreenshot()
    print("Before screenshot taken successfully!")

    if requires_confirmation:
        if altAct.confirmAction(f"Proceed with: {description}?") != "Yes":
            # later steps assume this one happened, so skipping it and carrying on isn't safe
            raise StopRun(f"You declined: {description}")

    previousSteps = stepList[: stepCount - 1]

    print("Completed Steps", json.dumps(previousSteps, indent=4))
    print("Current Step", json.dumps(step, indent=4))
    remainingSteps = stepList[stepCount:]

    executeAction(tag, args, altAct, kb, m)

    time.sleep(0.75)

    afterScreenshot()
    print("After screenshot taken successfully!")

    appendStepToJson(step)
    print("Step saved successfully!")

    if conditions:
        try:
            encodedBefore = encodeImage(
                "desktop-intelligence/screenshots/takenScreenshots/before/beforeScreenshot.png"
            )
            encodedAfter = encodeImage(
                "desktop-intelligence/screenshots/takenScreenshots/after/afterScreenshot.png"
            )
            mouseX, mouseY = m.getMousePosition()
            result = json.loads(
                compareImages(
                    encodedBefore,
                    encodedAfter,
                    visibleChange,
                    conditions,
                    mouseX,
                    mouseY,
                )
            )
            print("action_completed: ", result["action_completed"])
            if result["action_completed"] == "false" or not result["action_completed"]:
                print("Condition failed:", result["issue"])
                alteredSteps = parsePlan(
                    alterStepsReason(
                        usersInput,
                        result,
                        mouseX,
                        mouseY,
                        previousSteps,
                        step,
                        remainingSteps,
                        actionList,
                    )
                )
                return alteredSteps
            return None
        except Exception as e:
            print(f"Comparison failed: {e}")
            return None
    return None


def completeSteps(stepList, usersInput, actionList):
    stepList = parsePlan(stepList)
    stepCount = 0
    replans = 0

    try:
        while stepCount < len(stepList):
            step = stepList[stepCount]
            print(f"Step {stepCount + 1} starting...")

            updatedSteps = translateTag(
                step, stepList, stepCount + 1, usersInput, actionList
            )

            if updatedSteps is not None:
                replans += 1
                if replans > MAX_REPLANS:
                    raise StopRun(f"Still failing after {MAX_REPLANS} replans.")
                print("Updated Steps: \n", json.dumps(updatedSteps, indent=2))
                stepList = updatedSteps
                stepCount = 0
                continue

            print(f"Step {stepCount + 1} completed!")
            stepCount += 1
        print("All steps completed.")
    except StopRun as e:
        print(f"Stopped: {e}")
