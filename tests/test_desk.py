import unittest

from screen_intelligence.desk import to_screen


class Desk(unittest.TestCase):
    def test_screenshot_coordinates_scale_to_the_screen(self):
        # a 2560-wide screen shot at 1280 wide: every screenshot pixel is 2 screen points
        self.assertEqual(to_screen(200, 450, 2.0), (400, 900))
        self.assertEqual(to_screen(100.4, 0, 1.125), (113, 0))


if __name__ == "__main__":
    unittest.main()


class Run(unittest.TestCase):
    def test_batch_runs_each_step_in_order_with_quoted_text_intact(self):
        from unittest.mock import patch

        from screen_intelligence import desk

        with patch.object(desk, "pyautogui") as gui, patch.object(desk.time, "sleep"):
            desk.do("run", ['key tab; type "Zac Finkelstein"; key cmd+a'])
        self.assertEqual([c[0] for c in gui.method_calls], ["hotkey", "write", "hotkey"])
        self.assertEqual(gui.write.call_args.args[0], "Zac Finkelstein")
        self.assertEqual(gui.hotkey.call_args.args, ("command", "a"))
