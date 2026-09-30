"""python -m screen_intelligence "Open Safari and search for the weather in Kingston" """
import json
import sys

from . import RUNTIME, llm
from .actions import ACTION_LIST, STEP_LOG
from .agent import run_plan
from .screenshots import capture, encode


def main():
    goal = " ".join(sys.argv[1:]) or input("What would you like to do? ")
    RUNTIME.mkdir(exist_ok=True)
    STEP_LOG.write_text("[]")  # the step log is per run, so retry_last_action never replays an old run

    screen = RUNTIME / "screen.png"
    capture(screen)
    description = llm.describe_screen(encode(screen))
    plan = json.loads(llm.plan_steps(description, goal, ACTION_LIST))
    run_plan(plan, goal)


if __name__ == "__main__":
    main()
