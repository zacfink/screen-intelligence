import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def alterStepsReason(
    userGoal,
    result,
    mouseX,
    mouseY,
    previousSteps,
    currentStep,
    remainingSteps,
    actionList,
):
    client = OpenAI()

    response = client.responses.create(
        model="o3-mini",
        input=[
            {
                "role": "user",
                "content": f"""
                You are an AI automation planner. 
                Your job is to corrent an error on the screen determined by the result of a vison AI model.
                You will replace the current steps with a new list of steps as a result of a step not working properly
                You are to follow structured list of actions for a macOS assistant to follow.

                You will receive:
                - The user's initial goal
                - The result of the vision AI model
                - The mouse x and y positions
                - The previously done steps
                - The current step that the vision AI model analyzed with before and after pictures.
                - The remaining steps to be replaced.
                - A list of allowed actions (including their tags, arguments, and descriptions)

                You must return a JSON array where each action follows this format:

                {{
                "tag": "action_tag",
                "args": [/* values matching required parameters */],
                "description": "Natural language description of what the step does, including purpose and spatial or UI context.",
                "undo_tag": "optional_tag_to_reverse_action_or_null",
                "conditions": ["list of required conditions that must be true before this action runs"],
                "requires_confirmation": true_or_false,
                "visible_effect": "what should visibly change if the action succeeds"
                }}

                Use only actions from the provided list. Do not invent new tags or functions. Use realistic values for all args.
                Avoid explanations — just return the raw JSON array.

                ---

                USER GOAL:
                {userGoal}

                RESULT OF VISION AI MODEL:
                {result}

                MOUSE X:
                {mouseX}

                MOUSE Y:
                {mouseY}

                PREVIOUSLY RUN STEPS:
                {previousSteps}

                CURRENTLY RAN STEP:
                {currentStep}

                REMAINING LIST OF STEPS:
                {remainingSteps}

                LIST OF ACTIONS:
                {actionList}

                ---

                Now return the JSON array of steps only:
                """,
            }
        ],
    )

    cleaned = re.sub(r"```json|```", "", response.output_text).strip()
    print(cleaned)
    return cleaned
