"""Tesseract is faked; these test the clustering and the maths, not the OCR."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from screen_intelligence import ocr
from screen_intelligence.ocr import best_match


def hit(left, top, width=40, height=20, conf=90, text="Submit"):
    return [str(left), str(top), str(width), str(height), str(conf), text]


class BestMatch(unittest.TestCase):
    def test_no_hits(self):
        self.assertIsNone(best_match([]))

    def test_one_hit_is_its_own_box(self):
        self.assertEqual(best_match([hit(10, 20)]), [10, 20, 40, 20])

    def test_same_word_found_twice_in_one_place(self):
        # the three Tesseract modes often find the same word at the same spot
        self.assertEqual(best_match([hit(10, 20), hit(10, 20, conf=50)]), [10, 20, 40, 20])

    def test_picks_the_most_confident_cluster(self):
        weak = [hit(0, 0, conf=30), hit(30, 5, conf=40)]
        strong = [hit(500, 500, conf=90), hit(530, 505, conf=80)]
        left, top, _, _, conf = best_match(weak + strong)
        self.assertEqual((left, top, conf), (515.0, 502.5, 85.0))  # averages of the strong pair

    def test_hits_far_apart_are_not_a_cluster(self):
        self.assertIsNone(best_match([hit(0, 0), hit(900, 900)]))

    def test_tesseract_header_row_is_not_a_match(self):
        self.assertIsNone(best_match([["left", "top", "width", "height", "conf", "text"], hit(10, 20)]))


class FindText(unittest.TestCase):
    def test_returns_the_centre_in_screen_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.png"
            cv2.imwrite(str(path), np.zeros((100, 200, 3), np.uint8))  # a 200x100 screenshot, 400x200 after the 2x resize
            row = "\t".join(["5", "1", "1", "1", "1", "1"] + hit(100, 40, width=40, height=20))
            with patch.object(ocr.pytesseract, "image_to_data", return_value=f"header\n{row}"), \
                 patch.object(ocr.pyautogui, "size", return_value=(200, 100)):
                # box centre (120, 50) in the 2x image is (60, 25) on a 200x100 screen
                self.assertEqual(ocr.find_text(path, "Submit"), (60, 25))

    def test_text_not_on_screen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.png"
            cv2.imwrite(str(path), np.zeros((100, 200, 3), np.uint8))
            with patch.object(ocr.pytesseract, "image_to_data", return_value="header\n"):
                self.assertIsNone(ocr.find_text(path, "Submit"))


if __name__ == "__main__":
    unittest.main()
