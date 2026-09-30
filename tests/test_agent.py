"""No model calls and nothing touches the real mouse: the model, screenshots and actions are patched."""
import unittest
from unittest.mock import patch

from screen_intelligence import agent
from screen_intelligence.models import StepCheck
from tests.helpers import step

CLICK = step()
CHECKED = step(conditions=["Safari is open"], visible_effect="a Safari window")
WORKED = StepCheck(action_completed=True, issue=None, current_screen_state="Safari")
FAILED = StepCheck(action_completed=False, issue="nothing opened", current_screen_state="desktop")


class RunStep(unittest.TestCase):
    """run_step with the screen and mouse patched out; only the model's verdict changes."""

    def setUp(self):
        for name in ["capture_with_cursor", "execute_action", "log_step", "encode", "time"]:
            patcher = patch.object(agent, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(agent.pyautogui, "position", return_value=(10, 20))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_step_without_conditions_skips_the_check(self):
        with patch.object(agent.llm, "check_step") as check:
            self.assertIsNone(agent.run_step(CLICK, [CLICK], 0, "goal"))
        check.assert_not_called()

    def test_step_that_worked_keeps_the_plan(self):
        with patch.object(agent.llm, "check_step", return_value=WORKED), \
             patch.object(agent.llm, "replan") as replan:
            self.assertIsNone(agent.run_step(CHECKED, [CHECKED], 0, "goal"))
        replan.assert_not_called()

    def test_failed_step_asks_for_a_new_plan(self):
        done, later = step(tag="wait"), step(tag="type_text")
        plan = [done, CHECKED, later]
        with patch.object(agent.llm, "check_step", return_value=FAILED), \
             patch.object(agent.llm, "replan", return_value=[CLICK]) as replan:
            self.assertEqual(agent.run_step(CHECKED, plan, 1, "goal"), [CLICK])
        # the replanner sees what already ran, the step that failed and what was still to come
        replan.assert_called_once_with("goal", FAILED, 10, 20, [done], CHECKED, [later], agent.ACTION_LIST)

    def test_model_error_carries_on_instead_of_crashing(self):
        with patch.object(agent.llm, "check_step", side_effect=RuntimeError("API down")):
            self.assertIsNone(agent.run_step(CHECKED, [CHECKED], 0, "goal"))


class RunPlan(unittest.TestCase):
    def test_runs_every_step_in_order(self):
        plan = [step(tag="wait"), step(tag="left_click")]
        with patch.object(agent, "run_step", return_value=None) as run_step:
            agent.run_plan(plan, "goal")
        self.assertEqual([c.args[2] for c in run_step.call_args_list], [0, 1])

    def test_new_plan_starts_from_its_first_step(self):
        new = [step(tag="press_key", args=["enter"])]
        with patch.object(agent, "run_step", side_effect=[None, new, None]) as run_step:
            agent.run_plan([CLICK, CLICK], "goal")
        self.assertEqual(run_step.call_args_list[-1].args[:3], (new[0], new, 0))

    def test_replanning_is_capped(self):
        with patch.object(agent, "run_step", return_value=[CLICK]) as run_step:
            agent.run_plan([CLICK], "goal")
        self.assertEqual(run_step.call_count, agent.MAX_REPLANS + 1)

    def test_declining_a_step_stops_the_run(self):
        with patch.object(agent, "confirm", return_value="No"), \
             patch.object(agent, "capture_with_cursor"), \
             patch.object(agent, "execute_action") as execute:
            agent.run_plan([step(requires_confirmation=True), CLICK], "goal")
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
