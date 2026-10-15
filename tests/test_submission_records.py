"""提交记录分离、新一轮范围与故障图片验证；无真实 API/鼠标。"""
import json
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from tests.test_auto_flow import FakePage


class SubmissionRecordTests(unittest.TestCase):
    def test_confirmed_success_removes_pending_lock(self):
        page = FakePage(total=1)
        pending, confirmed = set(), set()
        flow = page.flow(pending)
        flow.confirmed_submissions = confirmed
        flow.run()
        self.assertEqual(pending, set())
        self.assertEqual(confirmed, {"1"})

    def test_success_record_does_not_block_unanswered_same_content(self):
        pending, confirmed = set(), set()
        for _ in range(2):
            page = FakePage(total=1)
            flow = page.flow(pending)
            flow.confirmed_submissions = confirmed
            flow.run()
            self.assertEqual(page.requests, 1)
            self.assertEqual(sum(x == 400 for x, _ in page.clicks), 1)
        self.assertFalse(pending)
        self.assertEqual(confirmed, {"1"})

    def test_observed_submitted_reconciles_pending_without_resubmission(self):
        page = FakePage(total=1)
        page.selected, page.submitted = True, True
        pending = {"1", "other"}
        flow = page.flow(pending)
        flow.run()
        self.assertEqual(pending, {"other"})
        self.assertEqual(flow.confirmed_submissions, {"1"})
        self.assertEqual(page.clicks, [])

    def test_unconfirmed_remains_locked(self):
        page = FakePage(total=1, accept_submit=False)
        pending = set()
        flow = page.flow(pending)
        with self.assertRaises(ValueError):
            flow.run()
        self.assertEqual(pending, {"1"})
        self.assertFalse(flow.confirmed_submissions)
        with self.assertRaises(ValueError):
            page.flow(pending).run()
        self.assertEqual(sum(x == 400 for x, _ in page.clicks), 1)

    def test_new_round_clears_records_but_normal_start_keeps_them(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QObject, pyqtSignal
        from ui.main_window import MainWindow
        from ui.controller import AssistantController
        app = QApplication.instance() or QApplication([])

        class IdleWorker(QObject):
            progress = pyqtSignal(object)
            answer_ready = pyqtSignal(object)
            visibility_requested = pyqtSignal(bool, object)
            ended = pyqtSignal(str)
            finished = pyqtSignal()

            def start(self):
                pass

        store = SimpleNamespace(load=lambda: {"api_key": "test_only", "screen_region":
                    {"x": 0, "y": 0, "width": 100, "height": 100}})
        window = MainWindow()
        controller = AssistantController(window, store)
        controller.submit_attempts.add("pending")
        controller.confirmed_submissions.add("confirmed")
        controller.retry_target = "pending"
        old_session = controller.session_id
        try:
            with patch("ui.controller.AutoAnswerWorker", return_value=IdleWorker()) as factory, \
                    patch("ui.controller.QTimer.singleShot"):
                controller.start_auto()
                self.assertEqual(controller.submit_attempts, {"pending"})
                self.assertEqual(controller.confirmed_submissions, {"confirmed"})
                self.assertEqual(controller.session_id, old_session)
                controller.worker = None
                window.set_auto_running(False)
                window.new_round_button.click()
                self.assertEqual(controller.submit_attempts, set())
                self.assertEqual(controller.confirmed_submissions, set())
                self.assertIsNone(controller.retry_target)
                self.assertNotEqual(controller.session_id, old_session)
                self.assertEqual(factory.call_args.kwargs["session_id"], controller.session_id)
        finally:
            controller.escape_timer.stop()
            controller.worker = None
            window.set_auto_running(False)
            window.close()
            app.processEvents()

    @unittest.skipUnless(os.environ.get("VISION_RECORD_DEBUG_DIR"), "未提供成功后翻题的故障样例")
    def test_real_previous_success_clears_only_its_pending_record(self):
        folder = Path(os.environ["VISION_RECORD_DEBUG_DIR"])
        previous = json.loads((folder/"02_report.json").read_text(encoding="utf-8"))
        current = json.loads((folder/"04_report.json").read_text(encoding="utf-8"))
        self.assertIs(previous["page_state"]["submitted"], True)
        self.assertIs(current["page_state"]["submitted"], False)
        self.assertTrue(all(not c["selected"] for c in current["controls"] if c["kind"].endswith("option")))
        pending = {previous["question_signature"]}
        flow = FakePage().flow(pending)
        flow.mark_confirmed(previous["question_signature"])
        self.assertNotIn(current["question_signature"], pending)
        self.assertFalse(pending)
