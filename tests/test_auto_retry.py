"""用户显式恢复提交的纯模拟回归，不调用业务 API 或真实鼠标。"""
import copy
import os
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from tests.test_auto_flow import FakePage


class AutoRetryTests(unittest.TestCase):
    def test_recovery_button_targets_only_last_locked_question(self):
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow
        from ui.controller import AssistantController
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        controller = AssistantController(window)
        controller.submit_attempts.update({"1", "unrelated"})
        controller.worker = SimpleNamespace(
            recent_observations=[{"report": {"question_signature": "1", "page_state": {"submitted": False}}},
                                 {"report": {"question_signature": None, "page_blocker": "安全核验"}}],
            deleteLater=Mock())
        controller._auto_finished()
        try:
            self.assertEqual(controller.retry_target, "1")
            self.assertTrue(window.retry_button.isEnabled())
            controller._start_auto = Mock()
            window.retry_button.click()
            controller._start_auto.assert_called_once_with(retry_signature="1")
            self.assertEqual(controller.submit_attempts, {"1", "unrelated"})
        finally:
            controller.escape_timer.stop()
            window.close()
            app.processEvents()

    def flow(self, page, attempts, signature="1"):
        flow = page.flow(attempts)
        flow.retry_signature = signature
        return flow

    def test_explicit_retry_clears_only_confirmed_pending_record(self):
        page = FakePage(total=1)
        page.selected = True
        attempts = {"1", "unrelated"}
        flow = self.flow(page, attempts)
        flow.run()
        self.assertEqual(sum(x == 400 for x, _ in page.clicks), 1)
        self.assertEqual(page.requests, 1)
        self.assertIsNone(flow.retry_signature)
        self.assertEqual(attempts, {"unrelated"})
        self.assertEqual(flow.confirmed_submissions, {"1"})

    def test_failed_retry_does_not_unlock_normal_start(self):
        page = FakePage(total=1, accept_submit=False)
        page.selected = True
        attempts = {"1"}
        with self.assertRaises(ValueError):
            self.flow(page, attempts).run()
        with self.assertRaises(ValueError):
            page.flow(attempts).run()
        self.assertEqual(sum(x == 400 for x, _ in page.clicks), 1)

    def test_changed_question_blocks_retry(self):
        page = FakePage()
        page.selected = True
        with self.assertRaisesRegex(ValueError, "不一致"):
            self.flow(page, {"other"}, "other").run()
        self.assertEqual(page.clicks, [])

    def test_verification_blocker_blocks_retry(self):
        page = FakePage()
        page.selected = True
        current = page.observe()
        current.report["page_blocker"] = "页面要求手动完成安全核验"
        with self.assertRaisesRegex(ValueError, "安全核验"):
            self.flow(page, {"1"}).prepare_retry(current)
        self.assertEqual(page.clicks, [])

    def test_already_submitted_does_not_resubmit(self):
        page = FakePage(total=1)
        page.selected, page.submitted = True, True
        self.flow(page, {"1"}).run()
        self.assertEqual(page.clicks, [])
        self.assertEqual(page.requests, 0)

    def test_unselected_cannot_recover_submission(self):
        page = FakePage(total=1)
        with self.assertRaises(ValueError):
            self.flow(page, {"1"}).run()
        self.assertEqual(page.clicks, [])

    @unittest.skipUnless(os.environ.get("VISION_RETRY_DEBUG_DIR"), "未提供提交锁故障样例")
    def test_real_locked_page_replay(self):
        from PIL import Image
        from vision.control_reader import ControlReader
        from vision.screen_session import analyze_capture
        from core.auto_flow import AutoFlow
        folder = Path(os.environ["VISION_RETRY_DEBUG_DIR"])
        region = json.loads((folder/"failure.json").read_text(encoding="utf-8"))["screen_region"]
        with Image.open(folder/"01_original.png") as image:
            current = analyze_capture(image.convert("RGB"), region, ControlReader())
        signature = current.report["question_signature"]
        attempts = {signature}
        click = Mock()
        flow = AutoFlow(lambda: current, Mock(), click, lambda: False, lambda: False,
                        Mock(), Mock(), attempts, retry_signature=signature)
        self.assertIs(flow.prepare_retry(current), current)
        self.assertIn(signature, attempts)
        # 仅一次恢复检查不发送点击；完整流程仍须经过 AI 答案和选中验证。
        click.assert_not_called()

    def test_unknown_state_or_changed_second_observation_does_not_unlock(self):
        page = FakePage()
        page.selected = True
        current = page.observe()
        changed = copy.deepcopy(current)
        changed.report["question_signature"] = "other"
        attempts = {"1"}
        flow = self.flow(page, attempts)
        flow.observe = lambda: changed
        with self.assertRaises(ValueError):
            flow.prepare_retry(current)
        self.assertEqual(attempts, {"1"})
