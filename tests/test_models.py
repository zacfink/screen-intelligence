import unittest

from pydantic import ValidationError

from screen_intelligence.models import Plan, StepCheck

STEP = """{"tag": "move_mouse", "args": [120, 45.5], "description": "Move to the address bar",
           "undo_tag": null, "conditions": ["Safari is open"], "requires_confirmation": false,
           "visible_effect": "cursor over the address bar"}"""


class Models(unittest.TestCase):
    def test_plan_parses_and_keeps_number_args_as_numbers(self):
        plan = Plan.model_validate_json(f'{{"steps": [{STEP}]}}')
        self.assertEqual(plan.steps[0].args, [120, 45.5])
        self.assertIsInstance(plan.steps[0].args[0], int)  # pyautogui.moveTo needs numbers, not "120"

    def test_step_missing_a_field_is_rejected(self):
        with self.assertRaises(ValidationError):
            Plan.model_validate_json('{"steps": [{"tag": "left_click", "args": []}]}')

    def test_check_needs_a_real_boolean(self):
        # the old code had to handle the model answering "false" as a string
        self.assertFalse(StepCheck.model_validate_json(
            '{"action_completed": false, "issue": "no window", "current_screen_state": "desktop"}').action_completed)
        with self.assertRaises(ValidationError):
            StepCheck.model_validate_json('{"action_completed": "maybe", "issue": null, "current_screen_state": ""}')


if __name__ == "__main__":
    unittest.main()
