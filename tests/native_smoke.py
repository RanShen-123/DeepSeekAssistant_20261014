"""短暂显示纯色测试窗口，验证实际 Windows 截图和选区，结束自动关闭。"""
import sys
import ctypes
import tempfile
from pathlib import Path
from PyQt6.QtCore import QRect, QPoint, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtTest import QTest
from PIL import Image
from core.screenshot import capture_region
from ui.selector import physical_screen_bounds, map_region, RegionSelector


def main() -> int:
    if sys.platform == "win32":
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    screen = app.primaryScreen()
    geometry = screen.geometry()
    window = QWidget()
    window.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    window.setStyleSheet("background-color: rgb(213, 19, 177);")
    window.setGeometry(geometry.x() + 40, geometry.y() + 40, 320, 200)
    window.show()
    selector = RegionSelector()
    selected, cancelled, failures = [], [], []
    selector.selected.connect(selected.append)
    selector.cancelled.connect(lambda: cancelled.append(True))

    def check():
        try:
            physical = physical_screen_bounds(screen)
            local = QRect(window.x() - geometry.x(), window.y() - geometry.y(),
                          window.width(), window.height())
            region = map_region(local, geometry, physical)
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
                path = capture_region(region, Path(folder))
                with Image.open(path) as image:
                    assert image.size == (region["width"], region["height"])
                    pixel = image.getpixel((image.width // 2, image.height // 2))
                    assert all(abs(a - b) < 10 for a, b in zip(pixel, (213, 19, 177))), pixel
            window.hide()
            selector.start()
            app.processEvents()
            overlay = selector.overlays[0]
            QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(50, 80))
            QTest.mouseMove(overlay, QPoint(250, 180))
            QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(250, 180))
            assert len(selected) == 1 and selected[0]["width"] >= 190
            assert not selector.overlays
            selector.start()
            app.processEvents()
            QTest.keyClick(selector.overlays[0], Qt.Key.Key_Escape)
            assert cancelled == [True] and not selector.overlays
            print("Native screenshot pixels, monitor mapping, selection and cancel: PASS")
        except Exception as exc:
            failures.append(str(exc))
            print("Native smoke check failed:", str(exc))
        finally:
            selector.cleanup()
            window.close()
            app.quit()

    QTimer.singleShot(700, check)
    app.exec()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
