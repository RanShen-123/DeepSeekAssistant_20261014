"""选中状态的生成图片回归，无真实桌面操作。"""
import unittest
import cv2
import numpy as np
from vision.selection_state import option_selected, selected_letter_image
from vision.controls import classify_boolean_symbol


def option_image(selected, symbol="true"):
    image = np.full((90, 90, 3), 255, dtype=np.uint8)
    cv2.circle(image, (45, 45), 27, (255, 110, 60) if selected else (160, 160, 160), -1 if selected else 1)
    color = (255, 255, 255) if selected else (160, 160, 160)
    if symbol == "true":
        cv2.polylines(image, [np.array([[34, 45], [42, 53], [56, 37]])], False, color, 2)
    elif symbol == "false":
        cv2.line(image, (37, 37), (53, 53), color, 2)
        cv2.line(image, (37, 53), (53, 37), color, 2)
    else:
        cv2.putText(image, symbol, (34, 54), cv2.FONT_HERSHEY_SIMPLEX, .8, color, 2)
    return image, [18, 18, 55, 55]


class SelectionTests(unittest.TestCase):
    def test_blue_and_unselected_for_letters_and_symbols(self):
        for symbol in ("A", "B", "C", "D", "true", "false"):
            for selected in (True, False):
                with self.subTest(symbol=symbol, selected=selected):
                    image, box = option_image(selected, symbol)
                    state, evidence = option_selected(image, box)
                    self.assertIs(state, selected)
                    self.assertIn("占比", evidence)

    def test_unknown_style_does_not_become_unselected(self):
        image = np.full((90, 90, 3), (60, 60, 60), dtype=np.uint8)
        self.assertIsNone(option_selected(image, [18, 18, 55, 55])[0])

    def test_selected_symbols_keep_actual_meaning(self):
        for symbol in ("true", "false"):
            for selected in (True, False):
                with self.subTest(symbol=symbol, selected=selected):
                    image, box = option_image(selected, symbol)
                    self.assertEqual(classify_boolean_symbol(image, box)[0], symbol)

    def test_letter_conversion_preserves_source(self):
        image, box = option_image(True, "A")
        original = image.copy()
        converted = selected_letter_image(image, box)
        np.testing.assert_array_equal(image, original)
        x, y, w, h = box
        gray = cv2.cvtColor(converted[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
        self.assertGreater(np.count_nonzero(gray == 0), 10)
        self.assertGreater(np.count_nonzero(gray == 255), gray.size*.5)
