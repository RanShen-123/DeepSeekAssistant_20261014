"""预览回归：只用内存图片及模拟截图，不读取或点击真实桌面。"""
import gc
import os
import unittest
from unittest.mock import patch

from PIL import Image
from PyQt6 import sip
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from tools.preview_screen import ImageView, ScreenPreview
from vision.screen_session import ScreenResult


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_pixel_ownership_survives_collection_resize_and_replacement(self):
        view = ImageView()
        try:
            view.resize(640, 480)
            view.show()
            for mode in ("RGB", "RGBA", "L"):
                for size in ((1200, 900), (301, 199), (1536, 864)):
                    image = Image.new(mode, size, 127)
                    view.set_image(image)
                    del image
                    gc.collect()
                    for fit in (False, True):
                        view.fit = fit
                        view.resize(530, 370)
                        view.render()
                        self.app.processEvents()
                        self.assertFalse(view.label.pixmap().isNull())
                    self.assertEqual(view.pixmap.size().width(), size[0])
                    self.assertEqual(view.pixmap.toImage().pixelColor(0, 0).red(), 127)
        finally:
            view.close()

    def test_worker_to_two_previews_with_mock_capture(self):
        window = ScreenPreview()
        image = Image.new("RGB", (800, 600), "white")
        report = {"question_type": "single", "warnings": [], "controls": [
            {"label": "A", "center": [100, 150], "screen_center": [-700, 250],
             "confidence": .99}]}
        result = ScreenResult(image, image.copy(), report)
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        try:
            window.region = {"x": -800, "y": 100, "width": 800, "height": 600}
            with patch("tools.preview_screen.capture_image", return_value=image), \
                    patch("vision.control_reader.ControlReader"), \
                    patch("tools.preview_screen.analyze_capture", return_value=result):
                window.begin_capture()
                worker = window.worker
                worker.finished.connect(loop.quit)
                timer.start(15000)
                loop.exec()
                if not sip.isdeleted(worker):
                    self.assertTrue(worker.wait(2000), "模拟后台任务未结束")
                self.app.processEvents()
            self.assertIs(window.result, result)
            self.assertFalse(window.busy)
            self.assertEqual(window.table.item(0, 2).text(), "[-700, 250]")
            self.assertTrue(window.save_button.isEnabled())
            self.assertFalse(window.marked_view.pixmap.isNull())
            self.assertFalse(window.original_view.pixmap.isNull())
        finally:
            timer.stop()
            if window.worker is not None:
                window.worker.wait(15000)
            window.busy = False
            window.close()

    @unittest.skipUnless(os.environ.get("VISION_SAMPLE_SINGLE") and os.environ.get("VISION_SAMPLE_BOOLEAN"),
                         "未提供两张本地样例图片路径")
    def test_real_ocr_sample_to_preview_without_desktop_capture(self):
        for variable, kind, labels in (
            ("VISION_SAMPLE_SINGLE", "single", ["A", "B", "C", "D"]),
            ("VISION_SAMPLE_BOOLEAN", "boolean", ["true", "false"]),
        ):
            with self.subTest(kind=kind):
                with Image.open(os.environ[variable]) as source:
                    image = source.convert("RGB")
                window = ScreenPreview()
                loop = QEventLoop()
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                try:
                    window.region = {"x": -1600, "y": 100, "width": image.width, "height": image.height}
                    with patch("tools.preview_screen.capture_image", return_value=image):
                        window.begin_capture()
                        worker = window.worker
                        worker.finished.connect(loop.quit)
                        timer.start(60000)
                        loop.exec()
                        if not sip.isdeleted(worker):
                            self.assertTrue(worker.wait(2000), "本地 OCR 未结束")
                        self.app.processEvents()
                    self.assertIsNotNone(window.result, window.status.text())
                    report = window.result.report
                    self.assertEqual(report["question_type"], kind)
                    self.assertEqual([c["label"] for c in report["controls"]
                                      if c["kind"].endswith("option")], labels)
                    self.assertEqual({c["id"] for c in report["controls"] if c["kind"] == "button"},
                                     {"previous", "submit", "next"})
                    for control in report["controls"]:
                        self.assertEqual(control["screen_center"],
                                         [-1600+control["center"][0], 100+control["center"][1]])
                    self.assertFalse(window.marked_view.pixmap.isNull())
                finally:
                    timer.stop()
                    if window.worker is not None:
                        window.worker.wait(60000)
                    window.busy = False
                    window.close()


if __name__ == "__main__":
    unittest.main()
