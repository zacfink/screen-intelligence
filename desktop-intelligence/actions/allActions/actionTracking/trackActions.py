import json
import os


def appendStepToJson(step):
    with open(
        "desktop-intelligence/actions/allActions/actionTracking/trackedActions/actions.json",
    ) as feedsjson:
        feeds = json.load(feedsjson)
    feeds.append(json.dumps(step))
    print(feeds)
    with open(
        "desktop-intelligence/actions/allActions/actionTracking/trackedActions/actions.json",
        "w",
    ) as f:
        f.write(json.dumps(feeds, indent=5))


def getLastStep():
    with open(
        "desktop-intelligence/actions/allActions/actionTracking/trackedActions/actions.json",
        "r",
    ) as f:
        allSteps = json.load(f)
        if not allSteps:
            return None
        else:
            return allSteps[-1]
