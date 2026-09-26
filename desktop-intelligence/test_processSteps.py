"""Run from the repo root: python -m unittest discover desktop-intelligence
No model calls and nothing touches the real mouse or keyboard: the action objects are mocks."""

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import processSteps
from processSteps import StopRun, completeSteps, executeAction, parsePlan

ACTIONS = json.loads((Path(__file__).parent / "actions/actionList/actionList.json").read_text())
ARGS = {"x: int": 5, "y: int": 5, "direction: string": "down", "amount: int": 1}


class ExecuteAction(unittest.TestCase):
    def test_every_listed_action_is_wired_up(self):
        for action in ACTIONS:
            tag = action["tag"]
            with self.subTest(tag=tag):
                # spec= makes a misspelled method (the old exitSquence) fail instead of passing silently
                altAct = Mock(spec=processSteps.AlernativeActions)
                kb, m = Mock(spec=processSteps.Keyboard), Mock(spec=processSteps.Mouse)
                args = [ARGS.get(a, "Safari") for a in action["args"]]
                if tag == "exit_sequence":
                    self.assertRaises(StopRun, executeAction, tag, args, altAct, kb, m)
                    continue
                with patch.object(processSteps, "getLastStep", return_value={"tag": "left_click", "args": []}):
                    executeAction(tag, args, altAct, kb, m)
                self.assertTrue(altAct.method_calls or kb.method_calls or m.method_calls, f"{tag} did nothing")

    def test_unknown_action_stops(self):
        self.assertRaises(StopRun, executeAction, "format_disk", [], Mock(), Mock(), Mock())

    def test_retry_replays_the_last_step_with_its_args(self):
        m = Mock()
        with patch.object(processSteps, "getLastStep", return_value={"tag": "move_mouse", "args": [3, 4]}):
            executeAction("retry_last_action", [], Mock(), Mock(), m)
        m.moveMouse.assert_called_once_with(3, 4)


class CompleteSteps(unittest.TestCase):
    PLAN = '```json\n[{"tag": "left_click", "args": []}]\n```'

    def test_parse_plan_strips_code_fences(self):
        self.assertEqual(parsePlan(self.PLAN), [{"tag": "left_click", "args": []}])

    def test_replanning_is_capped(self):
        with patch.object(processSteps, "translateTag", return_value=[{"tag": "left_click"}]) as t:
            completeSteps(self.PLAN, "goal", ACTIONS)
        self.assertEqual(t.call_count, processSteps.MAX_REPLANS + 1)

    def test_declining_a_step_stops_the_run(self):
        altAct = Mock()
        altAct.confirmAction.return_value = "No"
        with patch.object(processSteps, "AlernativeActions", return_value=altAct), \
             patch.object(processSteps, "beforeScreenshot"), \
             patch.object(processSteps, "executeAction") as run:
            completeSteps('[{"tag": "left_click", "requires_confirmation": true}, {"tag": "left_click"}]', "goal", ACTIONS)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
