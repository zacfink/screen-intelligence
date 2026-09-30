"""No model calls and nothing touches the real mouse: the model, screenshots and actions are patched."""
import unittest
from unittest.mock import patch

from screen_intelligence import agent
from screen_intelligence.actions import StopRun

CLICK = {"tag": "left_click", "args": []}


class RunPlan(unittest.TestCase):
    def test_replanning_is_capped(self):
        with patch.object(agent, "run_step", return_value=[CLICK]) as run_step:
            agent.run_plan([CLICK], "goal")
        self.assertEqual(run_step.call_count, agent.MAX_REPLANS + 1)

    def test_declining_a_step_stops_the_run(self):
        with patch.object(agent, "confirm", return_value="No"), \
             patch.object(agent, "capture_with_cursor"), \
             patch.object(agent, "execute_action") as execute:
            agent.run_plan([{**CLICK, "requires_confirmation": True}, CLICK], "goal")
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
