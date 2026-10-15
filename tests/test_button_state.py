"""页面状态纯模拟测试，无真实截图、鼠标和 API。"""
import unittest
import numpy as np
from vision.button_state import detect_page_state, submit_enabled, text_enabled
from vision.models import Control, TextLine


class ButtonStateTests(unittest.TestCase):
    def test_blue_hover_next_is_available_not_finished(self):
        state = self.read_state(color=(255, 110, 60))
        self.assertIs(state["next_enabled"], True)
        self.assertIs(state["all_completed"], False)
        self.assertEqual(state["suggested_action"], "next")

    def test_red_or_unknown_colored_text_stays_unknown(self):
        self.assertIsNone(self.read_state(color=(60, 60, 220))["next_enabled"])

    def test_blue_background_is_not_hover_text(self):
        image = np.full((40, 80, 3), (255, 110, 60), dtype=np.uint8)
        self.assertIsNone(text_enabled(image, [0, 0, 80, 40], allow_blue=True)[0])

    def test_blue_button_is_enabled(self):
        image = np.full((100, 200, 3), 255, dtype=np.uint8)
        image[30:80, 20:180] = (255, 110, 60)
        image[45:65, 90:95] = 255
        control = Control("submit", "button", "提交", [20, 30, 160, 50], [100, 55], .99, "模拟")
        enabled, _ = submit_enabled(image, control, TextLine("提交", .99, [80, 40, 40, 30]))
        self.assertIs(enabled, True)

    def test_gray_button_is_disabled(self):
        image = np.full((100, 200, 3), 255, dtype=np.uint8)
        image[30:80, 20:180] = 247
        image[45:65, 90:95] = 195
        control = Control("submit", "button", "提交", [20, 30, 160, 50], [100, 55], .99, "模拟")
        enabled, _ = submit_enabled(image, control, TextLine("提交", .99, [80, 40, 40, 30]))
        self.assertIs(enabled, False)

    def read_state(self, submitted_label="已提交", color=190, include_next=True):
        image = np.full((300, 500, 3), 255, dtype=np.uint8)
        image[250:267, 400:405] = color
        controls = [Control("submit", "button", submitted_label, [200, 240, 100, 40],
                            [250, 260], .99, "模拟 OCR")]
        lines = []
        if include_next:
            controls.append(Control("next", "button", "下一题", [390, 240, 80, 40],
                                    [430, 260], .99, "模拟 OCR"))
            lines.append(TextLine("下一题", .99, [395, 245, 60, 30]))
        return detect_page_state(image, lines, controls)

    def test_submitted_and_gray_next_means_finished(self):
        state = self.read_state()
        self.assertIs(state["all_completed"], True)
        self.assertEqual(state["suggested_action"], "stop")

    def test_submitted_and_dark_next_means_next(self):
        state = self.read_state(color=95)
        self.assertIs(state["next_enabled"], True)
        self.assertEqual(state["suggested_action"], "next")

    def test_gray_submit_without_submitted_text_does_not_finish(self):
        state = self.read_state(submitted_label="提交")
        self.assertIs(state["submitted"], False)
        self.assertIs(state["all_completed"], False)

    def test_missing_next_is_unknown(self):
        state = self.read_state(include_next=False)
        self.assertIsNone(state["next_enabled"])
        self.assertIsNone(state["all_completed"])
        self.assertEqual(state["suggested_action"], "pause")

    def test_uncertain_gray_is_unknown(self):
        state = self.read_state(color=145)
        self.assertIsNone(state["next_enabled"])
        self.assertEqual(state["suggested_action"], "pause")
