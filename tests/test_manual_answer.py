"""只注入假截图和假鼠标，不操作真实桌面。"""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from vision.manual_answer import normalize_answer, choose_once


def observation(selected=False, signature="same", submitted=False):
    return SimpleNamespace(report={
        "question_signature": signature, "question_type": "single",
        "page_state": {"submitted": submitted},
        "screen_region": {"x": -1000, "y": 200, "width": 800, "height": 600},
        "controls": [{"kind": "choice_option", "label": label, "confidence": .99,
                      "selected": selected if label == "B" else False,
                      "center": [100, 100+index*60], "screen_center": [-900, 300+index*60]}
                     for index, label in enumerate("ABCD")]})


class ManualAnswerTests(unittest.TestCase):
    def test_answer_adapter(self):
        self.assertEqual(normalize_answer("ｂ"), "B")
        self.assertEqual(normalize_answer("正确"), "true")
        self.assertEqual(normalize_answer("×"), "false")
        with self.assertRaises(ValueError):
            normalize_answer("A或者B")

    def test_one_click_and_verify(self):
        before, after = observation(), observation(True)
        click = Mock()
        result = choose_once(copy.deepcopy(before.report), "B", Mock(side_effect=[before, after]),
                             click, lambda: False, lambda: False)
        self.assertEqual(click.call_count, 1)
        self.assertEqual(click.call_args.args[:2], (-900, 360))
        self.assertTrue(result.report["manual_click"]["verified"])

    def test_already_selected_does_not_click(self):
        before = observation(True)
        click = Mock()
        choose_once(before.report, "B", lambda: before, click, lambda: False, lambda: False)
        click.assert_not_called()

    def test_change_or_submitted_blocks_click(self):
        baseline = observation().report
        for fresh in (observation(signature="different"), observation(submitted=True)):
            click = Mock()
            with self.assertRaises(ValueError):
                choose_once(baseline, "B", lambda: fresh, click, lambda: False, lambda: False)
            click.assert_not_called()

    def test_stop_blocks_click(self):
        click = Mock()
        with self.assertRaises(RuntimeError):
            choose_once(observation().report, "B", Mock(), click, lambda: True, lambda: False)
        click.assert_not_called()

    def test_failed_verification_does_not_retry(self):
        before = observation()
        click = Mock()
        result = choose_once(before.report, "B", Mock(side_effect=[before, observation()]),
                             click, lambda: False, lambda: False)
        self.assertFalse(result.report["manual_click"]["verified"])
        self.assertTrue(result.report["manual_click"]["same_question"])
        self.assertFalse(result.report["manual_click"]["selection_confirmed"])
        self.assertEqual(click.call_count, 1)
