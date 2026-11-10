import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from screen_intelligence import desk_moves


class MoveBrain(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for p in (patch.object(desk_moves, "LONG", Path(d.name) / "brain.json"), patch.dict(desk_moves._short, clear=True),
                  patch.object(desk_moves, "place", lambda app: app), patch.object(desk_moves.desk, "do"),
                  patch.object(desk_moves.desk, "click", return_value=True)):
            p.start()
            self.addCleanup(p.stop)
        self.found = [{"role": "combo", "text": "Search Wikipedia", "x": 400, "y": 120}]

    def test_same_step_in_other_words_is_one_key(self):
        self.assertEqual(desk_moves.key("Safari", "Click the Wikipedia search field."),
                         desk_moves.key("Safari", "click wikipedia search field"))

    def test_a_learnt_click_replays_in_a_later_run_by_its_label(self):
        k = desk_moves.key("Safari", "click the search field")
        desk_moves.learn(k, ("click", "combo", "Search Wikipedia"))
        desk_moves._short.clear()  # a new run: only long-term memory left
        moved = [{**self.found[0], "x": 900}]  # the layout moved; the label didn't
        self.assertIn("long-term", desk_moves.replay(k, "Any page", moved, 1440, 900))
        desk_moves.desk.click.assert_called_with(900, 120, "left")

    def test_points_are_short_term_and_only_in_the_same_window(self):
        k = desk_moves.key("Safari", "click the star")
        desk_moves.learn(k, ("point", 0.5, 0.5, "Page A"))
        self.assertIn("short-term", desk_moves.replay(k, "Page A", [], 1000, 800))
        self.assertIsNone(desk_moves.replay(k, "Page B", [], 1000, 800))
        desk_moves._short.clear()
        self.assertIsNone(desk_moves.replay(k, "Page A", [], 1000, 800))

    def test_a_move_that_keeps_missing_is_forgotten(self):
        k = desk_moves.key("Safari", "click the search field")
        desk_moves.learn(k, ("click", "combo", "Search Wikipedia"))
        self.assertIsNone(desk_moves.replay(k, "x", [], 1000, 800))  # element gone: miss
        self.assertIsNone(desk_moves.recall(k, "x"))  # missed as often as it worked: Jev decides again

    def test_return_and_risky_labels_are_never_replayed_without_permission(self):
        k = desk_moves.key("Safari", "press enter to search")
        desk_moves.learn(k, ("key", "return"))
        self.assertIsNone(desk_moves.replay(k, "x", [], 1000, 800))
        self.assertIn("pressed return", desk_moves.replay(k, "x", [], 1000, 800, allow_risky=True))
        k = desk_moves.key("Safari", "click send")
        desk_moves.learn(k, ("click", "button", "Send"))
        self.assertIsNone(desk_moves.replay(k, "x", [{"role": "button", "text": "Send", "x": 1, "y": 1}], 1000, 800))


if __name__ == "__main__":
    unittest.main()
