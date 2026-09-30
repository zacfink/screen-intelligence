"""pyautogui, subprocess and time are mocks, so nothing moves, types or opens for real."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from screen_intelligence import actions
from screen_intelligence.actions import ACTION_LIST, StopRun, execute_action

SAMPLE_ARGS = {"x: int": 5, "y: int": 5, "direction: string": "down", "amount: int": 1, "seconds: float": 0}


class Actions(unittest.TestCase):
    def setUp(self):
        self.mocks = {}
        for name in ["pyautogui", "subprocess", "time", "find_text"]:
            patcher = patch.object(actions, name)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, file in [("STEP_LOG", "steps.json"), ("NOTES", "notes.txt"), ("RUNTIME", "")]:
            patcher = patch.object(actions, name, Path(folder.name) / file)
            patcher.start()
            self.addCleanup(patcher.stop)
        actions.STEP_LOG.write_text("[]")

    def anything_happened(self):
        return any(m.mock_calls for m in self.mocks.values()) or actions.NOTES.exists()

    def test_every_listed_action_does_something(self):
        actions.log_step({"tag": "left_click", "args": []})  # for retry_last_action
        for action in ACTION_LIST:
            tag = action["tag"]
            if tag == "exit_sequence":
                continue
            with self.subTest(tag=tag):
                for m in self.mocks.values():
                    m.reset_mock()
                execute_action(tag, [SAMPLE_ARGS.get(a, "Safari") for a in action["args"]])
                self.assertTrue(self.anything_happened(), f"{tag} did nothing")

    def test_exit_and_unknown_actions_stop_the_run(self):
        self.assertRaises(StopRun, execute_action, "exit_sequence", [])
        self.assertRaises(StopRun, execute_action, "format_disk", [])

    def test_app_names_are_never_run_through_a_shell(self):
        execute_action("open_application", ["Safari; rm -rf ~"])
        self.mocks["subprocess"].run.assert_called_once_with(["open", "-a", "Safari; rm -rf ~"])

    def test_scroll_down_and_left_are_negative(self):
        execute_action("scroll", ["down", 3])
        execute_action("scroll", ["left", 2])
        self.mocks["pyautogui"].scroll.assert_called_once_with(-3)
        self.mocks["pyautogui"].hscroll.assert_called_once_with(-2)

    def test_retry_replays_the_last_step_with_its_args(self):
        actions.log_step({"tag": "move_mouse", "args": [3, 4]})
        execute_action("retry_last_action", [])
        self.assertEqual(self.mocks["pyautogui"].moveTo.call_args.args[:2], (3, 4))

    def test_retry_with_nothing_logged_does_nothing(self):
        execute_action("retry_last_action", [])
        self.assertFalse(self.anything_happened())

    def test_text_not_found_on_screen_is_not_clicked(self):
        self.mocks["find_text"].return_value = None
        execute_action("move_and_click_text", ["Submit"])
        self.mocks["pyautogui"].click.assert_not_called()

    def test_text_found_on_screen_is_clicked(self):
        self.mocks["find_text"].return_value = (100, 200)
        execute_action("move_and_click_text", ["Submit"])
        self.assertEqual(self.mocks["pyautogui"].moveTo.call_args.args[:2], (100, 200))
        self.mocks["pyautogui"].click.assert_called_once()


if __name__ == "__main__":
    unittest.main()
