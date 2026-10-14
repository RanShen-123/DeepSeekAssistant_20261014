"""每屏独立选区，Qt 逻辑坐标转换为 Windows 物理像素坐标。"""
import ctypes
import sys
from ctypes import wintypes
from PyQt6.QtCore import QObject, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget


def physical_screens() -> dict:
    if sys.platform != "win32":
        return {}

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32)]

    result = {}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    user32 = ctypes.windll.user32
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    @callback_type
    def callback(handle, dc, rect, data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            bounds = info.rcMonitor
            result[info.szDevice] = (bounds.left, bounds.top,
                                     bounds.right - bounds.left, bounds.bottom - bounds.top)
        return True

    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                         callback_type, wintypes.LPARAM]
    user32.EnumDisplayMonitors(None, None, callback, 0)
    return result


def map_region(rect: QRect, logical: QRect, physical: tuple) -> dict:
    x, y, width, height = physical
    sx, sy = width / logical.width(), height / logical.height()
    left, top = round(rect.x() * sx), round(rect.y() * sy)
    right = min(width, round((rect.x() + rect.width()) * sx))
    bottom = min(height, round((rect.y() + rect.height()) * sy))
    return {"x": x + left, "y": y + top,
            "width": right - left, "height": bottom - top}


def physical_screen_bounds(screen) -> tuple:
    """通过原生窗口定位显示器，不依赖 Qt 名称和 DISPLAY 名称相同。"""
    geo = screen.geometry()
    if sys.platform != "win32":
        ratio = screen.devicePixelRatio()
        return (round(geo.x() * ratio), round(geo.y() * ratio),
                round(geo.width() * ratio), round(geo.height() * ratio))

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32)]

    probe = QWidget()
    probe.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
    probe.setGeometry(geo.x() + 8, geo.y() + 8, 16, 16)
    probe.winId()
    probe.windowHandle().setScreen(screen)
    probe.setGeometry(geo.x() + 8, geo.y() + 8, 16, 16)
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    try:
        handle = user32.MonitorFromWindow(int(probe.winId()), 2)
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if not handle or not user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            raise RuntimeError("无法读取显示器的物理坐标。")
        rect = info.rcMonitor
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    finally:
        probe.destroy()
        probe.deleteLater()


class ScreenOverlay(QWidget):
    selected = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, screen, physical: tuple) -> None:
        super().__init__()
        self.screen_geometry = screen.geometry()
        self.physical = physical
        self.start = None
        self.selection = QRect()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(self.screen_geometry)
        self.setMouseTracking(True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        path = QPainterPath()
        path.addRect(0, 0, self.width(), self.height())
        if not self.selection.isNull():
            path.addRect(float(self.selection.x()), float(self.selection.y()),
                         float(self.selection.width()), float(self.selection.height()))
        path.setFillRule(Qt.FillRule.OddEvenFill)
        painter.fillPath(path, QColor(0, 0, 0, 110))
        if not self.selection.isNull():
            painter.setPen(QPen(QColor("#4fc3ff"), 2))
            painter.drawRect(self.selection)
        painter.fillRect(16, 16, min(600, self.width() - 32), 52, QColor(25, 35, 50, 230))
        painter.setPen(QColor("white"))
        painter.drawText(28, 47, "拖动左键框选题目（限单个屏幕） · Esc / 右键取消")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()
            self.selection = QRect()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start is not None:
            self.selection = QRect(self.start, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.start is not None:
            self.selection = QRect(self.start, event.position().toPoint()).normalized().intersected(self.rect())
            self.start = None
            self.update()
            if self.selection.width() >= 10 and self.selection.height() >= 10:
                self.selected.emit(map_region(self.selection, self.screen_geometry, self.physical))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.cancelled.emit()
        event.accept()


class RegionSelector(QObject):
    selected = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.overlays = []

    def start(self) -> None:
        screens = QApplication.screens()
        if not screens:
            raise RuntimeError("没有可用的显示器。")
        # 先验证所有坐标映射，避免只显示部分遮罩。
        definitions = []
        for screen in screens:
            physical = physical_screen_bounds(screen)
            definitions.append((screen, physical))
        for screen, physical in definitions:
            overlay = ScreenOverlay(screen, physical)
            overlay.selected.connect(self._selected)
            overlay.cancelled.connect(self._cancelled)
            self.overlays.append(overlay)
            overlay.show()
        self.overlays[0].activateWindow()

    def cleanup(self) -> None:
        for overlay in self.overlays:
            overlay.blockSignals(True)
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def _selected(self, region: dict) -> None:
        self.cleanup()
        self.selected.emit(region)

    def _cancelled(self) -> None:
        self.cleanup()
        self.cancelled.emit()
