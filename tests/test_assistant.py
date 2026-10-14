"""不联网、不读取用户密钥的回归测试。"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from openai import APIConnectionError
import httpx
from PIL import Image
from core.config import ConfigStore, validate_region
from core.deepseek import analyze_image
from core.screenshot import capture_region
from ui.main_window import MainWindow
from ui.controller import AssistantController
from ui.selector import ScreenOverlay, map_region

APP = QApplication.instance() or QApplication([])


class AssistantTests(unittest.TestCase):
    def test_config_preserves_key_and_negative_coordinates(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            store = ConfigStore(Path(folder) / "config.yaml")
            store.save({"api_key": "test-placeholder", "model": "deepseek-flash"})
            region = {"x": -1000, "y": 20, "width": 500, "height": 300}
            store.set_region(region)
            loaded = store.load()
            self.assertEqual(loaded["api_key"], "test-placeholder")
            self.assertEqual(loaded["screen_region"], region)

    def test_bad_regions(self):
        for region in (None, {}, {"x": True, "y": 0, "width": 100, "height": 100},
                       {"x": 0, "y": 0, "width": 0, "height": 100}):
            with self.assertRaises(ValueError):
                validate_region(region)

    def test_scaling_and_negative_monitor_origin(self):
        mapped = map_region(QRect(20, 40, 200, 100), QRect(-1280, 0, 1280, 720),
                            (-1920, 0, 1920, 1080))
        self.assertEqual(mapped, {"x": -1890, "y": 60, "width": 300, "height": 150})

    def test_selector_drag_and_escape(self):
        screen = APP.primaryScreen()
        geo = screen.geometry()
        overlay = ScreenOverlay(screen, (0, 0, geo.width(), geo.height()))
        regions, cancelled = [], []
        overlay.selected.connect(regions.append)
        overlay.cancelled.connect(lambda: cancelled.append(True))
        overlay.show()
        from PyQt6.QtCore import QPoint
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 180))
        QTest.mouseMove(overlay, QPoint(40, 60))
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(40, 60))
        self.assertEqual(len(regions), 1)
        # Windows 离屏驱动可能在鼠标事件转换时产生一个像素的舍入差。
        self.assertLessEqual(abs(regions[0]["x"] - 40), 1)
        self.assertGreater(regions[0]["width"], 150)
        QTest.keyClick(overlay, Qt.Key.Key_Escape)
        self.assertEqual(cancelled, [True])
        overlay.blockSignals(True)
        overlay.close()

    def test_missing_region_and_key_display_error(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            store = ConfigStore(Path(folder) / "config.yaml")
            window = MainWindow()
            controller = AssistantController(window, store)
            window.recognize_button.click()
            self.assertIn("设置题目区域", window.answer_edit.toPlainText())
            store.set_region({"x": 0, "y": 0, "width": 100, "height": 100})
            window.recognize_button.click()
            self.assertIn("API Key", window.answer_edit.toPlainText())
            self.assertIsNone(controller.worker)
            window.close()

    def test_background_answer_and_ui_recovery(self):
        from PyQt6.QtCore import QEventLoop, QTimer
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            store = ConfigStore(Path(folder) / "config.yaml")
            store.save({"api_key": "test-placeholder", "screen_region": {
                "x": 0, "y": 0, "width": 100, "height": 100}})
            window = MainWindow()
            controller = AssistantController(window, store)
            with patch("core.worker.capture_region", return_value=Path(folder) / "test.png"), \
                 patch("core.worker.analyze_image", return_value="答案：5"):
                controller.recognize()
                self.assertFalse(window.recognize_button.isEnabled())
                loop = QEventLoop()
                controller.worker.finished.connect(loop.quit)
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                timer.start(3000)
                loop.exec()
                self.assertIsNone(controller.worker)
                self.assertTrue(window.recognize_button.isEnabled())
                self.assertEqual(window.answer_edit.toPlainText(), "答案：5")
                self.assertTrue(window.isVisible())
            window.close()

    def test_png_capture_and_disconnected_region(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder, patch("core.screenshot.mss.mss") as factory:
            capture = factory.return_value.__enter__.return_value
            capture.monitors = [{}, {"left": 0, "top": 0, "width": 100, "height": 100}]
            capture.grab.return_value = SimpleNamespace(size=(10, 10), rgb=b"\xff\xff\xff" * 100)
            path = capture_region({"x": 0, "y": 0, "width": 10, "height": 10}, Path(folder))
            with Image.open(path) as image:
                self.assertEqual(image.size, (10, 10))
            with self.assertRaises(ValueError):
                capture_region({"x": 90, "y": 0, "width": 20, "height": 20}, Path(folder))

    def test_image_api_payload_and_network_failure(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            path = Path(folder) / "question.png"
            Image.new("RGB", (20, 20), "white").save(path)
            config = {"api_key": "test-placeholder", "model": "deepseek-flash"}
            with patch("core.deepseek.OpenAI") as factory:
                client = factory.return_value.__enter__.return_value
                client.chat.completions.create.return_value = SimpleNamespace(choices=[
                    SimpleNamespace(message=SimpleNamespace(content="答案：5"), finish_reason="stop")])
                self.assertEqual(analyze_image(path, config), "答案：5")
                kwargs = client.chat.completions.create.call_args.kwargs
                self.assertEqual(kwargs["model"], "deepseek-flash")
                self.assertTrue(kwargs["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
                client.chat.completions.create.side_effect = APIConnectionError(
                    request=httpx.Request("POST", "https://example.invalid"))
                with self.assertRaisesRegex(RuntimeError, "无法连接"):
                    analyze_image(path, config)


if __name__ == "__main__":
    unittest.main()
