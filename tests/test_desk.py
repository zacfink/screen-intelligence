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
        self.pyautogui.position.return_value = (0, 0)  # glide reads where the mouse starts

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
                patch.object(self.desk, "window_at", return_value=None), patch.object(self.desk, "around", return_value=same):
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
                patch.object(self.desk, "window_at", return_value=None), patch.object(self.desk, "around", return_value=before):
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

    def click_with(self, draw):
        """Click at (640, 400) on a 1280x800-point retina screen; draw(image, poll) paints each screenshot after it."""
        from unittest.mock import patch

        from PIL import Image, ImageDraw

        shots = []

        def screenshot():
            image = Image.new("RGB", (2560, 1600), "white")
            if shots:  # the first shot is the one from before the click
                draw(ImageDraw.Draw(image), len(shots))
            shots.append(image)
            return image

        self.pyautogui.screenshot.side_effect = screenshot
        self.pyautogui.size.return_value = (1280, 800)
        with patch.object(self.desk, "window_at", return_value=None), patch.object(self.desk, "CHANGE_WAIT", 0.2):
            return self.desk.click(640, 400, "left")

    def test_a_checkbox_tick_at_the_click_counts_though_the_window_barely_changes(self):
        def tick(d, poll):  # a 14-point checkbox gets its check mark (screenshot pixels, 2 per point)
            d.line((1270, 800, 1278, 810, 1292, 788), fill="black", width=4)

        from PIL import Image, ImageDraw

        plain, ticked = Image.new("RGB", (2560, 1600), "white"), Image.new("RGB", (2560, 1600), "white")
        tick(ImageDraw.Draw(ticked), 1)
        self.pyautogui.size.return_value = (1280, 800)
        self.assertFalse(self.desk.changed(self.desk.frame(None, plain), self.desk.frame(None, ticked)))  # the old check missed it
        self.assertTrue(self.click_with(tick))

    def test_a_text_caret_appearing_at_the_click_is_not_a_change(self):
        self.assertFalse(self.click_with(lambda d, poll: d.rectangle((1281, 784, 1282, 816), fill="black")))

    def test_a_spinner_by_the_click_is_not_a_change(self):
        def spin(d, poll):  # a small blob that moves round every poll and never settles
            x, y = [(1290, 790), (1302, 790), (1302, 802), (1290, 802)][poll % 4]
            d.rectangle((x, y, x + 10, y + 10), fill="black")

        self.assertFalse(self.click_with(spin))

    def test_moving_the_mouse_yourself_stops_the_batch_after_the_current_step(self):
        # read before and after each step; you grab the mouse after step 2 finishes
        self.pyautogui.position.side_effect = [(100, 100)] * 4 + [(400, 250)]
        with self.assertRaises(SystemExit) as stop:
            self.desk.do("run", ["key tab; key tab; key tab"])
        self.assertIn("before step 3 of 3", str(stop.exception.code))
        self.assertIn("you moved the mouse", str(stop.exception.code))
        self.assertEqual(self.pyautogui.hotkey.call_count, 2)  # steps 1 and 2 finished, step 3 never started


class Map(unittest.TestCase):
    def test_mouse_map_keeps_ui_numbers_and_skips_plain_text_and_unlabelled(self):
        from screen_intelligence.desk import KEYS, moves

        found = [{"role": "text", "text": "Welcome"}, {"role": "button", "text": "Add Shortcut"},
                 {"role": "button", "text": ""}, {"role": "link", "text": "Help"}]
        m = moves("Shortcuts", "Claude Speak", found)
        self.assertEqual(m["mouse"], {"#2": "button Add Shortcut", "#4": "link Help"})
        self.assertIs(m["keyboard"], KEYS)
        self.assertNotIn("cmd+q", KEYS.values())  # nothing destructive in the keyboard map


class Batch(unittest.TestCase):
    def test_type_keeps_shell_quotes_and_brackets(self):
        from screen_intelligence.desk import steps

        self.assertEqual(steps("type cd ~/x && claude 'Remove the tab (the button)'; key return"),
                         [["type", "cd ~/x && claude 'Remove the tab (the button)'"], ["key", "return"]])
        self.assertEqual(steps('type --keys "September"'), [["type", "--keys", "September"]])


class Find(unittest.TestCase):
    def test_close_up_box_maps_back_to_the_full_screenshot(self):
        from unittest.mock import patch

        from PIL import Image

        from screen_intelligence import desk

        # pass 1 puts it in the middle of a 3600x2338 screen; pass 2 says it's the top-left quarter of the close-up
        answers = iter([{"box": {"left": .45, "right": .55, "top": .45, "bottom": .55}, "confidence": .9, "visible": 1},
                        {"box": {"left": 0, "right": .5, "top": 0, "bottom": .5}, "confidence": .95, "visible": 1}])
        with patch.object(desk, "jev", lambda *a: next(answers)):
            (l, t, r, b), a = desk.find_box(Image.new("RGB", (3600, 2338)), "x")
        # pass 1 box is 360x234, so the crop is 576x560 (0.8 of the box each side, at least 280) around (1800, 1169)
        self.assertEqual((round(l), round(t), round(r), round(b)), (1512, 889, 1800, 1169))
        self.assertEqual(a["confidence"], .95)


class Do(unittest.TestCase):
    def test_task_splits_into_ordered_steps(self):
        from screen_intelligence.desk_do import plan

        self.assertEqual(plan("Click Save, then Share; then the star."), ["Click Save", "Share", "the star"])

    def test_a_timid_stuck_gives_way_to_the_best_real_move(self):
        from screen_intelligence.desk_do import pick

        self.assertEqual(pick({"choice": "stuck", "probabilities": {"stuck": .4, "click_point": .35}}), "click_point")
        self.assertEqual(pick({"choice": "stuck", "probabilities": {"stuck": .7, "click_point": .2}}), "stuck")

    def test_quoted_text_is_typeable_and_never_split(self):
        from screen_intelligence.desk_do import plan, quoted

        self.assertEqual(plan('Click search, then type "rain; then sun" then press return'),
                         ["Click search", 'type "rain; then sun"', "press return"])
        self.assertEqual(quoted('type "weather in Kingston" but don\'t'), ["weather in Kingston"])

    def test_plain_type_and_press_steps_skip_jev(self):
        from unittest.mock import patch

        from screen_intelligence import desk, desk_do

        with patch.object(desk, "natural_type") as typed, patch.object(desk, "do") as do:
            self.assertEqual(desk_do.direct('type "hi there"'), "typed 'hi there'")
            self.assertEqual(desk_do.direct("press return"), "pressed return")
            self.assertIsNone(desk_do.direct("click the Save button"))
        typed.assert_called_once_with("hi there")
        do.assert_called_once_with("key", ["return"])


class Memory(unittest.TestCase):
    def test_a_find_is_reused_only_while_its_window_looks_the_same(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from PIL import Image, ImageDraw

        from screen_intelligence import desk

        screen = Image.new("RGB", (640, 400))
        window = {"X": 100, "Y": 50, "Width": 300, "Height": 300, "id": 7}
        with tempfile.TemporaryDirectory() as tmp, patch.object(desk, "MEMORY", Path(tmp) / "m.json"), \
                patch.object(desk, "pyautogui") as gui, patch.object(desk, "window_at", return_value=window), \
                patch.object(desk, "front_pid", return_value=42) as pid:
            gui.size.return_value = (640, 400)
            gui.screenshot.return_value = screen
            desk.remember("Save", [200, 100], [1, 2, 3, 4], {"confidence": .9, "visible": .9}, 1.0, screen)
            self.assertEqual(desk.recall("Save")["box"], [1, 2, 3, 4])
            self.assertIsNone(desk.recall("Send"))  # a different target is never a hit
            pid.return_value = 43  # another app came to the front
            self.assertIsNone(desk.recall("Save"))
            pid.return_value = 42
            scrolled = screen.copy()
            ImageDraw.Draw(scrolled).rectangle((150, 100, 300, 200), fill="white")  # inside the window
            gui.screenshot.return_value = scrolled
            self.assertIsNone(desk.recall("Save"))
            gui.screenshot.return_value = screen
            with patch.object(desk.time, "time", return_value=desk.time.time() + desk.MEMORY_TTL):
                self.assertIsNone(desk.recall("Save"))  # too old
            self.assertFalse(desk.MEMORY.exists())  # and cleared, not kept
            desk.remember("Save", [200, 100], [1, 2, 3, 4], {"confidence": .9, "visible": .9}, 1.0, screen)
            desk.do("wait", ["0"])  # a look keeps it
            self.assertIsNotNone(desk.recall("Save"))
            desk.do("key", ["tab"])  # any act forgets it
            self.assertFalse(desk.MEMORY.exists())
