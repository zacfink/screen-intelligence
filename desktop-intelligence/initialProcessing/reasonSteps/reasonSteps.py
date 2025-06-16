from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def reasonSteps(imageDescription, userGoal, actionList):
    client = OpenAI()

    response = client.responses.create(
        model="o3-mini",
        input=[
            {
                "role": "user",
                "content": f"""
                You are an AI automation planner. Your job is to create a structured list of actions for a macOS assistant to follow.

                You will receive:
                - The user's goal
                - A description of the current screen
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

                SCREEN DESCRIPTION:
                {imageDescription}

                AVAILABLE ACTIONS:
                {actionList}

                ---

                Now return the JSON array of steps only:
                """,
            }
        ],
    )

    return response.output_text
