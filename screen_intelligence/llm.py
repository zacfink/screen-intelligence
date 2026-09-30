"""The four model calls: describe the screen, plan steps, check a step worked, replan after a failure."""
from dotenv import load_dotenv
from openai import OpenAI

from .models import Plan, Step, StepCheck

load_dotenv()

STEP_RULES = """Each step's fields:
- tag: an action tag from the list
- args: values matching that action's parameters
- description: what the step does, including purpose and spatial or UI context
- undo_tag: a tag that would reverse the step, or null
- conditions: what must be true before this step runs
- requires_confirmation: true if the user should approve it first
- visible_effect: what should visibly change if the step succeeds

Use only actions from the provided list. Do not invent new tags or functions. Use realistic values for all args."""


def dump(steps):
    return "[" + ",\n".join(s.model_dump_json(indent=2) for s in steps) + "]"


def image(b64):
    return {"type": "input_image", "image_url": f"data:image/png;base64,{b64}"}


def describe_screen(screenshot_b64):
    prompt = (
        "You are an assistant helping an AI agent understand a macOS screenshot. "
        "Describe what is visible in the image in as much detail as possible. "
        "Use spatial references (top-left, bottom-right, center, etc.). "
        "Clearly identify:\n\n"
        "1. The currently open application (e.g., Safari, Terminal, VS Code, etc.)\n"
        "2. Layout and location of UI panels (e.g., file explorer on the left, tabs at top, terminal at bottom)\n"
        "3. Any code, visible text, or labels within the UI (copy important text snippets if readable)\n"
        "4. Any visible menus, tabs, buttons, input fields, icons, or other interactive elements\n"
        "5. The position of the mouse cursor (if visible)\n\n"
        "Be extremely descriptive. Format your response as a bullet-point breakdown so the AI can reason based on the visual state of the computer."
    )
    response = OpenAI().responses.create(
        model="gpt-4o",
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}, image(screenshot_b64)]}],
    )
    return response.output_text


def plan_steps(screen_description, goal, action_list) -> list[Step]:
    prompt = f"""You are an AI automation planner. Your job is to create a structured list of actions for a macOS assistant to follow.

You will receive:
- The user's goal
- A description of the current screen
- A list of allowed actions (including their tags, arguments, and descriptions)

{STEP_RULES}

---

USER GOAL:
{goal}

SCREEN DESCRIPTION:
{screen_description}

AVAILABLE ACTIONS:
{action_list}

---"""
    response = OpenAI().responses.parse(model="o3-mini", input=[{"role": "user", "content": prompt}], text_format=Plan)
    return response.output_parsed.steps


def check_step(before_b64, after_b64, visible_effect, conditions, mouse_x, mouse_y) -> StepCheck:
    prompt = (
        "You are an assistant that compares two screenshots of a macOS computer.\n\n"
        "The first image is BEFORE an automation step. The second image is AFTER the step.\n\n"
        f'The expected visible change was: "{visible_effect}".\n'
        f"The expected condition after for the next steps to happen is: {conditions}\n\n"
        f"The mouse was moved to: x={mouse_x}, y={mouse_y}. The mouse cursor may appear as a small red circle at this position, or as a macOS pointer icon.\n\n"
        "Your task is to analyze the difference between the two screenshots and determine if the action was successful.\n\n"
        "Set action_completed to whether the expected change happened, and issue to what is missing or unchanged (null if it worked). "
        "In current_screen_state, accurately describe what the AFTER screenshot shows. If the step failed, a reasoning model uses this "
        "to fix the next steps, so make it very in-depth: describe the entire screen, not only what changed."
    )
    response = OpenAI().responses.parse(
        model="gpt-4o",
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}, image(before_b64), image(after_b64)]}],
        text_format=StepCheck,
    )
    return response.output_parsed


def replan(goal, check: StepCheck, mouse_x, mouse_y, done_steps: list[Step], failed_step: Step, remaining_steps: list[Step], action_list) -> list[Step]:
    prompt = f"""You are an AI automation planner.
Your job is to correct an error on the screen determined by the result of a vision AI model.
You will replace the current steps with a new list of steps as a result of a step not working properly.
You are to follow structured list of actions for a macOS assistant to follow.

You will receive:
- The user's initial goal
- The result of the vision AI model
- The mouse x and y positions
- The previously done steps
- The current step that the vision AI model analyzed with before and after pictures.
- The remaining steps to be replaced.
- A list of allowed actions (including their tags, arguments, and descriptions)

{STEP_RULES}

---

USER GOAL:
{goal}

RESULT OF VISION AI MODEL:
{check.model_dump_json(indent=2)}

MOUSE X:
{mouse_x}

MOUSE Y:
{mouse_y}

PREVIOUSLY RUN STEPS:
{dump(done_steps)}

CURRENTLY RAN STEP:
{failed_step.model_dump_json(indent=2)}

REMAINING LIST OF STEPS:
{dump(remaining_steps)}

LIST OF ACTIONS:
{action_list}

---"""
    response = OpenAI().responses.parse(model="o3-mini", input=[{"role": "user", "content": prompt}], text_format=Plan)
    return response.output_parsed.steps
