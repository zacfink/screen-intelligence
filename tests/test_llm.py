"""OpenAI is faked: these check what gets sent and that the parsed reply comes back, not the model."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from screen_intelligence import llm
from screen_intelligence.models import Plan, StepCheck
from tests.helpers import step


def fake_openai(output_parsed=None, output_text=""):
    client = MagicMock()
    reply = SimpleNamespace(output_parsed=output_parsed, output_text=output_text)
    client.responses.parse.return_value = client.responses.create.return_value = reply
    return patch.object(llm, "OpenAI", return_value=client), client


def sent_text(call):
    """The prompt text from a faked responses call, whether plain or with images."""
    content = call.kwargs["input"][0]["content"]
    return content if isinstance(content, str) else content[0]["text"]


class Llm(unittest.TestCase):
    def test_describe_screen_sends_the_screenshot_and_returns_text(self):
        patcher, client = fake_openai(output_text="Safari is open")
        with patcher:
            self.assertEqual(llm.describe_screen("QUJD"), "Safari is open")
        content = client.responses.create.call_args.kwargs["input"][0]["content"]
        self.assertEqual(content[1]["image_url"], "data:image/png;base64,QUJD")

    def test_plan_steps_asks_for_a_plan_and_returns_its_steps(self):
        steps = [step()]
        patcher, client = fake_openai(Plan(steps=steps))
        with patcher:
            self.assertEqual(llm.plan_steps("a desktop", "open Safari", [{"tag": "left_click"}]), steps)
        call = client.responses.parse.call_args
        self.assertIs(call.kwargs["text_format"], Plan)
        self.assertIn("open Safari", sent_text(call))
        self.assertIn("a desktop", sent_text(call))

    def test_check_step_sends_before_then_after(self):
        check = StepCheck(action_completed=True, issue=None, current_screen_state="Safari")
        patcher, client = fake_openai(check)
        with patcher:
            self.assertIs(llm.check_step("QkVG", "QUZU", "a window opens", ["Safari open"], 1, 2), check)
        call = client.responses.parse.call_args
        self.assertIs(call.kwargs["text_format"], StepCheck)
        images = [c["image_url"] for c in call.kwargs["input"][0]["content"][1:]]
        self.assertEqual(images, ["data:image/png;base64,QkVG", "data:image/png;base64,QUZU"])

    def test_replan_shows_the_model_what_failed(self):
        failed = step(tag="open_application", args=["Safari"])
        check = StepCheck(action_completed=False, issue="Safari never opened", current_screen_state="desktop")
        patcher, client = fake_openai(Plan(steps=[step()]))
        with patcher:
            llm.replan("goal", check, 1, 2, [], failed, [step(tag="wait")], [])
        prompt = sent_text(client.responses.parse.call_args)
        self.assertIn("Safari never opened", prompt)
        self.assertIn('"open_application"', prompt)
        self.assertIn('"wait"', prompt)


if __name__ == "__main__":
    unittest.main()
