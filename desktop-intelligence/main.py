import json
from screenshots.takeScreenshot import takeScreenshot
from screenshots.encodeScreenshot.encodeScreenshot import encodeImage
from initialProcessing.gptImageDescription.imageDescription import (
    imageDescriptionProcessing,
)
from initialProcessing.reasonSteps.reasonSteps import reasonSteps
from usersInput.usersInput import getUsersInput
from processSteps import completeSteps


def main():
    # usersInput = getUsersInput()
    usersInput = "Go onto Safari and open the Amazon Neo hedged stock."
    print("User Input: ", usersInput)
    with open("desktop-intelligence/actions/actionList/actionList.json", "r") as f:
        actionList = json.loads(f.read())
    print("Action list gotten successfully!")
    takeScreenshot()
    print("Screenshot taken successfully!")
    base64Data = encodeImage(
        "desktop-intelligence/screenshots/takenScreenshots/screen.png"
    )
    print("Screenshot encoded successfully!")
    # print(base64Data)
    imageDescription = imageDescriptionProcessing(base64Data)
    print("Image description formed successfully!")
    stepList = reasonSteps(imageDescription, usersInput, actionList)
    print("Step list formed successfully!")
    completeSteps(stepList, usersInput, actionList)


main()
