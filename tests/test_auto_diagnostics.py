"""失败快照落盘与取消行为，无真实 API、截图或鼠标。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from core.auto_worker import AutoAnswerWorker


class AutoDiagnosticsTests(unittest.TestCase):
    def test_failure_saves_observations_without_config_key(self):
        worker = AutoAnswerWorker({"screen_region": {"x": 0, "y": 0, "width": 30, "height": 30},
                                   "api_key": "test_secret_never_write"}, set())
        messages = []
        worker.ended.connect(messages.append)
        worker.recent_observations.append({"image": Image.new("RGB", (30, 30)),
                                           "report": {"question_signature": "test"}})
        with tempfile.TemporaryDirectory() as directory:
            with patch("core.auto_worker.PROJECT_DIR", Path(directory)), patch.object(worker, "cancelled", return_value=False):
                worker.report_failure("测试暂停")
            folder, = (Path(directory)/"outputs").iterdir()
            self.assertTrue((folder/"01_original.png").exists())
            self.assertEqual(json.loads((folder/"01_report.json").read_text(encoding="utf-8"))["question_signature"], "test")
            self.assertNotIn("test_secret_never_write", (folder/"failure.json").read_text(encoding="utf-8"))
            self.assertIn(str(folder), messages[0])

    def test_cancel_does_not_create_debug_files(self):
        worker = AutoAnswerWorker({"screen_region": {"x": 0, "y": 0, "width": 30, "height": 30}}, set())
        with tempfile.TemporaryDirectory() as directory:
            with patch("core.auto_worker.PROJECT_DIR", Path(directory)), patch.object(worker, "cancelled", return_value=True):
                worker.report_failure("已停止")
            self.assertEqual(list(Path(directory).iterdir()), [])
