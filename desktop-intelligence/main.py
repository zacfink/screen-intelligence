import json
import os
import sys
from pathlib import Path

# Every path in the agent is relative to the repo root, so run from there wherever it was launched.
os.chdir(Path(__file__).resolve().parent.parent)

from screenshots.takeScreenshot import takeScreenshot
from screenshots.encodeScreenshot.encodeScreenshot import encodeImage
from initialProcessing.gptImageDescription.imageDescription import (
    imageDescriptionProcessing,
)
from initialProcessing.reasonSteps.reasonSteps import reasonSteps
from usersInput.usersInput import getUsersInput
from processSteps import completeSteps

RUNTIME_DIRS = [
    "desktop-intelligence/screenshots/takenScreenshots/before",
    "desktop-intelligence/screenshots/takenScreenshots/after",
    "desktop-intelligence/screenshots/takenScreenshots/searchForText",
    "desktop-intelligence/actionProcessing/loggedNotes",
    "desktop-intelligence/actions/allActions/actionTracking/trackedActions",
]
TRACKED = "desktop-intelligence/actions/allActions/actionTracking/trackedActions/actions.json"


def main():
    usersInput = " ".join(sys.argv[1:]) or getUsersInput()
    print("User Input: ", usersInput)
    for d in RUNTIME_DIRS:
        os.makedirs(d, exist_ok=True)
    with open(TRACKED, "w") as f:
        f.write("[]")  # the step log is per run, so retry_last_action never replays an old run
    with open("desktop-intelligence/actions/actionList/actionList.json", "r") as f:
        actionList = json.loads(f.read())
    print("Action list gotten successfully!")
    takeScreenshot()
    print("Screenshot taken successfully!")
    base64Data = encodeImage(
        "desktop-intelligence/screenshots/takenScreenshots/screen.png"
    )
    print("Screenshot encoded successfully!")
    imageDescription = imageDescriptionProcessing(base64Data)
    print("Image description formed successfully!")
    stepList = reasonSteps(imageDescription, usersInput, actionList)
    print("Step list formed successfully!")
    completeSteps(stepList, usersInput, actionList)


if __name__ == "__main__":
    main()
