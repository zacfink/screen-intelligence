import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def compareImages(
    base64ImageBefore, base64ImageAfter, visibleChange, condition, mouseX, mouseY
):
    client = OpenAI()

    response = client.responses.create(
        model="gpt-4o",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are an assistant that compares two screenshots of a macOS computer.\n\n"
                            "The first image is BEFORE an automation step. The second image is AFTER the step.\n\n"
                            f'The expected visible change was: "{visibleChange}".\n'
                            f"The expected condition after for the next steps to happen is: {condition}\n\n"
                            f"The mouse was moved to: x={mouseX}, y={mouseY}. The mouse cursor may appear as a small red circle at this position, or as a macOS pointer icon.\n\n"
                            "Your task is to analyze the difference between the two screenshots and determine if the action was successful.\n\n"
                            "Return ONLY a valid JSON object in one of the following formats:\n\n"
                            "If the expected change occurred:\n"
                            '{\n  "action_completed": true,\n  "steps_needed": false,\n  "issue": null,\n  "current_screen_state": "Describe what the AFTER screenshot now shows."\n}\n\n'
                            "If the change did not occur:\n"
                            '{\n  "action_completed": false,\n  "steps_needed": true,\n  "issue": "Explain what is missing or unchanged based on the visible change.",\n  "current_screen_state": "Accurately describe what the AFTER screenshot still looks like. This will be used for a reasoning model to get the fix the next steps. Make this very indepth. Do not only explain what has happened, describe the entire screen."\n}\n\n'
                            "Do not include any commentary or explanation. Just output the JSON block only."
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{base64ImageBefore}",
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{base64ImageAfter}",
                    },
                ],
            }
        ],
    )

    cleaned = re.sub(r"```json|```", "", response.output_text).strip()
    print("compared images ran")
    return cleaned
