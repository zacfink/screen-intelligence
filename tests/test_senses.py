import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from screen_intelligence import desk_senses


class Roam(unittest.TestCase):
    def test_risky_labels_and_settings_never_reach_the_menu(self):
        found = [{"role": "button", "text": "Send", "x": 100, "y": 200},
                 {"role": "link", "text": "News", "x": 100, "y": 300},
                 {"role": "button", "text": "Delete draft", "x": 100, "y": 400},
                 {"role": "checkbox", "text": "Dark mode", "x": 100, "y": 500},
                 {"role": "tab", "text": "Photos", "x": 100, "y": 50}]  # in the browser chrome
        on_screen, elements, moves = desk_senses.roam_moves(found, 1000, 800, "Safari")
        self.assertEqual([e["text"] for e in on_screen], ["News"])
        self.assertEqual(list(elements), ["#1"])
        self.assertIn("click", moves)
        self.assertNotIn("switch Safari", moves)
        self.assertIn("switch Finder", moves)

    def test_memory_round_trips_and_keeps_only_the_last_lines(self):
        with tempfile.TemporaryDirectory() as d, patch.object(desk_senses, "MEMORY", Path(d) / "m.jsonl"):
            self.assertEqual(desk_senses.recall(), ["nothing yet"])
            for i in range(5):
                desk_senses.remember("roam", f"Window {i}", f"clicked {i}")
            lines = desk_senses.recall(2)
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[-1].endswith("in 'Window 4': clicked 4"))
            self.assertEqual(json.loads((Path(d) / "m.jsonl").read_text().splitlines()[0])["mode"], "roam")


if __name__ == "__main__":
    unittest.main()
