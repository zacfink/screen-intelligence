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
    def setUp(self):
        from unittest.mock import patch

        from screen_intelligence import desk

        self.desk = desk
        for target in (patch.object(desk, "pyautogui"), patch.object(desk.time, "sleep"), patch.object(desk, "subprocess")):
            self.addCleanup(target.stop)
            setattr(self, target.attribute, target.start())

    def test_batch_splits_on_semicolons_but_not_inside_quotes_or_on_element_numbers(self):
        self.assertEqual(self.desk.steps('click #78; type "a; b"; key tab'), [["click", "#78"], ["type", "a; b"], ["key", "tab"]])

    def test_type_pastes_and_restores_the_clipboard(self):
        self.subprocess.run.return_value.stdout = b"old"
        self.desk.do("run", ['key tab; type "https://x.ca"; key cmd+a'])
        copies = [c.kwargs["input"] for c in self.subprocess.run.call_args_list if c.args[0] == ["pbcopy"]]
        self.assertEqual(copies, [b"https://x.ca", b"old"])
        self.assertEqual([c.args for c in self.pyautogui.hotkey.call_args_list], [("tab",), ("command", "v"), ("command", "a")])

    def test_type_keys_sends_real_keystrokes(self):
        self.desk.do("type", ["--keys", "September"])
        self.assertEqual(self.pyautogui.write.call_args.args[0], "September")

    def test_a_click_that_changes_nothing_stops_the_batch(self):
        from unittest.mock import patch

        from PIL import Image

        same = Image.new("L", (640, 400))
        with patch.object(self.desk, "frame", return_value=same), patch.object(self.desk, "load", return_value=1.0), \
                patch.object(self.desk, "window_at", return_value=None):
            with self.assertRaises(SystemExit) as stop:
                self.desk.do("run", ["click 10 20; type never"])
        self.assertIn("step 1 of 2", str(stop.exception.code))
        self.assertIn("changed nothing", str(stop.exception.code))
        self.pyautogui.hotkey.assert_not_called()  # the type step never ran

    def test_a_click_that_changes_the_screen_carries_on(self):
        from unittest.mock import patch

        from PIL import Image, ImageDraw

        before = Image.new("L", (640, 400))
        after = before.copy()
        ImageDraw.Draw(after).rectangle((100, 100, 140, 120), fill=255)  # a form opened
        with patch.object(self.desk, "frame", side_effect=[before, after]), patch.object(self.desk, "load", return_value=1.0), \
                patch.object(self.desk, "window_at", return_value=None):
            self.desk.do("run", ["click 10 20; key tab"])
        self.pyautogui.hotkey.assert_called_once_with("tab")

    def test_menu_bar_clock_ticking_is_not_a_change(self):
        from PIL import Image, ImageDraw

        before = Image.new("L", (640, 400))
        after = before.copy()
        ImageDraw.Draw(after).rectangle((600, 0, 630, 8), fill=255)  # inside the blanked menu-bar strip
        self.pyautogui.screenshot.side_effect = [before.convert("RGB"), after.convert("RGB")]
        self.pyautogui.size.return_value = (640, 400)
        self.assertFalse(self.desk.changed(self.desk.frame(), self.desk.frame()))

    def test_only_the_clicked_window_is_compared(self):
        from PIL import Image, ImageDraw

        before = Image.new("RGB", (640, 400))
        after = before.copy()
        ImageDraw.Draw(after).rectangle((10, 300, 60, 390), fill="white")  # the terminal's spinner, outside the window
        self.pyautogui.screenshot.side_effect = [before, after]
        self.pyautogui.size.return_value = (640, 400)
        window = {"X": 300, "Y": 50, "Width": 300, "Height": 300}
        self.assertFalse(self.desk.changed(self.desk.frame(window), self.desk.frame(window)))

    def test_moving_the_mouse_yourself_stops_the_batch_after_the_current_step(self):
        # read before and after each step; you grab the mouse after step 2 finishes
        self.pyautogui.position.side_effect = [(100, 100)] * 4 + [(400, 250)]
        with self.assertRaises(SystemExit) as stop:
            self.desk.do("run", ["key tab; key tab; key tab"])
        self.assertIn("before step 3 of 3", str(stop.exception.code))
        self.assertIn("you moved the mouse", str(stop.exception.code))
        self.assertEqual(self.pyautogui.hotkey.call_count, 2)  # steps 1 and 2 finished, step 3 never started
