"""判分角标与真实提交故障回放；鼠标仅使用 Mock。"""
import json
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import Mock
import cv2
import numpy as np
from PIL import Image
from vision.controls import options
from vision.screen_session import analyze_capture
from vision.manual_buttons import button_once


class NoOCR:
    def read_crop(self, *args, **kwargs):
        return []


class SubmittedPageTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("VISION_SELECTION_DEBUG_DIR"), "未提供选中后标识变化的诊断样例")
    def test_real_selected_cross_does_not_change_identity(self):
        from vision.control_reader import ControlReader
        from vision.manual_answer import choose_once
        from vision.manual_buttons import matching_button
        folder = Path(os.environ["VISION_SELECTION_DEBUG_DIR"])
        region = json.loads((folder/"failure.json").read_text(encoding="utf-8"))["screen_region"]
        reader = ControlReader()
        observations = []
        for name in ("03_original.png", "04_original.png"):
            with Image.open(folder/name) as image:
                observations.append(analyze_capture(image.convert("RGB"), region, reader))
        before, after = observations
        self.assertEqual(before.report["question_signature"], after.report["question_signature"])
        self.assertEqual([c["text"] for c in after.report["question_identity"]["options"]], ["", ""])
        click = Mock()
        result = choose_once(before.report, "false", Mock(side_effect=[before, after]),
                             click, lambda: False, lambda: False)
        self.assertTrue(result.report["manual_click"]["verified"])
        self.assertEqual(click.call_count, 1)
        self.assertEqual(matching_button(after.report, "submit")["id"], "submit")

    @unittest.skipUnless(os.environ.get("VISION_HOVER_DEBUG_DIR"), "未提供蓝色下一题诊断样例")
    def test_real_dark_and_hover_next_both_available(self):
        from vision.control_reader import ControlReader
        from vision.manual_buttons import matching_button
        folder = Path(os.environ["VISION_HOVER_DEBUG_DIR"])
        reader = ControlReader()
        observations = []
        for path in sorted(folder.glob("*_original.png")):
            with Image.open(path) as image:
                report = reader.read(image)
            observations.append(report)
            self.assertIs(report["page_state"]["submitted"], True)
            self.assertIs(report["page_state"]["next_enabled"], True)
            self.assertIs(report["page_state"]["all_completed"], False)
            self.assertEqual(matching_button(report, "next")["id"], "next")
        self.assertGreaterEqual(len(observations), 2)
        self.assertTrue(any("蓝色" in str(r["page_state"]["evidence"]) for r in observations))

    def test_red_and_green_badges_do_not_erase_boolean_options(self):
        for badge in ((70, 70, 255), (100, 190, 0)):
            with self.subTest(badge=badge):
                bgr = np.full((700, 1000, 3), 255, dtype=np.uint8)
                cv2.circle(bgr, (200, 200), 26, (255, 110, 60), -1)
                cv2.polylines(bgr, [np.array([[190, 200], [197, 207], [212, 192]])], False, (255, 255, 255), 2)
                cv2.circle(bgr, (217, 182), 13, badge, -1)
                cv2.circle(bgr, (280, 200), 26, (160, 160, 160), 1)
                cv2.line(bgr, (272, 192), (288, 208), (160, 160, 160), 2)
                cv2.line(bgr, (272, 208), (288, 192), (160, 160, 160), 2)
                found = options(bgr, [], NoOCR(), "boolean", -1)
                self.assertEqual([c.label for c in found], ["true", "false"])
                self.assertEqual([c.selected for c in found], [True, False])

    @unittest.skipUnless(os.environ.get("VISION_SUBMIT_DEBUG_DIR"), "未提供真实提交诊断样例")
    def test_real_submission_and_next_conditions_replay(self):
        from vision.control_reader import ControlReader
        folder = Path(os.environ["VISION_SUBMIT_DEBUG_DIR"])
        region = json.loads((folder/"failure.json").read_text(encoding="utf-8"))["screen_region"]
        reader = ControlReader()
        observations = []
        for path in sorted(folder.glob("*_original.png")):
            with Image.open(path) as image:
                observations.append(analyze_capture(image.convert("RGB"), region, reader))
        before, after = observations[:2]
        self.assertIsNotNone(before.report["question_signature"])
        self.assertTrue(all(o.report["question_signature"] == before.report["question_signature"] for o in observations))
        self.assertTrue(all(o.report["page_state"]["submitted"] for o in observations[1:]))
        self.assertTrue(all(o.report["page_state"]["next_enabled"] for o in observations[1:]))
        click = Mock()
        result = button_once(before.report, "submit", Mock(side_effect=[before, after]),
                             click, lambda: False, lambda: False)
        self.assertTrue(result.report["manual_action"]["verified"])
        self.assertEqual(click.call_count, 1)
        # 此时满足自动流程继续下一题的条件；不需要重发提交。
        from vision.manual_buttons import matching_button
        self.assertEqual(matching_button(after.report, "next")["label"], "下一题")
        switched = copy.copy(after)
        switched.report = copy.deepcopy(after.report)
        switched.report["question_signature"] = "simulated_next_question"
        next_click = Mock()
        next_result = button_once(after.report, "next", Mock(side_effect=[after, switched]),
                                  next_click, lambda: False, lambda: False)
        self.assertTrue(next_result.report["manual_action"]["verified"])
        self.assertEqual(next_click.call_count, 1)

    @unittest.skipUnless(os.environ.get("VISION_BLOCKED_SAMPLE"), "未提供安全核验样例")
    def test_security_check_is_reported_for_manual_handling(self):
        from vision.control_reader import ControlReader
        with Image.open(os.environ["VISION_BLOCKED_SAMPLE"]) as image:
            report = ControlReader().read(image)
        self.assertIsNotNone(report["page_blocker"])
