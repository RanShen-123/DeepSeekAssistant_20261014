"""DeepSeek AI 助手程序入口。"""

import sys
import ctypes

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.controller import AssistantController
from PyQt6.QtCore import QTimer


def main() -> int:
    if sys.platform == "win32":
        # 在 QApplication 初始化之前设置，以便物理屏幕坐标不被 Windows 虚拟化。
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("DeepSeek AI 助手")
    app.setOrganizationName("DeepSeekAssistant")
    window = MainWindow()
    controller = AssistantController(window)
    window.show()
    QTimer.singleShot(200, controller.initialize)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
