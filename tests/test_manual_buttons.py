"""提交/翻题的模拟测试，只使用假鼠标与假观察结果。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from vision.manual_buttons import button_once, matching_button


def observation(submitted=False, next_enabled=True, signature="q1", can_submit=True):
    report = {"question_signature": signature,
              "screen_region": {"x": -1000, "y": 100, "width": 800, "height": 600},
              "page_state": {"submitted": submitted, "can_submit": can_submit,
                             "next_enabled": next_enabled},
              "controls": [{"id": name, "kind": "button", "label": label,
                            "confidence": .99, "enabled": enabled, "center": [x, 550],
                            "screen_center": [-1000+x, 650], "bbox": [x-30, 530, 60, 40]}
                           for name, label, enabled, x in
                           (("submit", "已提交" if submitted else "提交", not submitted and can_submit, 400),
                            ("next", "下一题", next_enabled, 700))]}
    return SimpleNamespace(report=report)


class ManualButtonTests(unittest.TestCase):
    def run_action(self, action, before, after):
        click = Mock()
        result = button_once(before.report, action, Mock(side_effect=[before, after, after, after]),
                             click, lambda: False, lambda: False)
        self.assertEqual(click.call_count, 1)
        return result.report["manual_action"]

    def test_submit_verified_without_next_click(self):
        result = self.run_action("submit", observation(), observation(submitted=True))
        self.assertTrue(result["verified"])
        self.assertEqual(result["action"], "submit")

    def test_submit_failure_does_not_retry(self):
        self.assertFalse(self.run_action("submit", observation(), observation())["verified"])

    def test_auto_advance_does_not_send_extra_next(self):
        result = self.run_action("submit", observation(), observation(signature="q2"))
        self.assertTrue(result["question_changed"])
        self.assertFalse(result["verified"])

    def test_next_verifies_changed_question(self):
        result = self.run_action("next", observation(submitted=True), observation(signature="q2"))
        self.assertTrue(result["verified"])

    def test_disabled_or_unknown_states_block(self):
        for action, report in (("submit", observation(can_submit=False).report),
                               ("submit", observation(submitted=True).report),
                               ("next", observation(submitted=True, next_enabled=False).report),
                               ("next", observation(submitted=None).report)):
            with self.subTest(action=action, state=report["page_state"]):
                with self.assertRaises(ValueError):
                    matching_button(report, action)

    def test_stop_does_not_click(self):
        click = Mock()
        with self.assertRaises(RuntimeError):
            button_once(observation().report, "submit", Mock(), click, lambda: True, lambda: False)
        click.assert_not_called()
