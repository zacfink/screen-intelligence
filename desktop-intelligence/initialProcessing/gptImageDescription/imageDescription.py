from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def imageDescriptionProcessing(base64_image):
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
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{base64_image}",
                    },
                ],
            }
        ],
    )

    return response.output_text
