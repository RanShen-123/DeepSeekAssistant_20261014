"""可拖动、可缩放、始终置顶的主悬浮窗口。"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TitleBar(QWidget):
    """通过系统窗口移动 API 拖动，失败时使用坐标移动。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._drag_offset = None
        self.setObjectName("titleBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        title = QLabel("DeepSeek AI 助手")
        title.setObjectName("title")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(title)
        layout.addStretch()
        minimize = QPushButton("−")
        minimize.setToolTip("最小化")
        minimize.setFixedSize(30, 28)
        minimize.clicked.connect(parent.showMinimized)
        close = QPushButton("×")
        close.setToolTip("关闭")
        close.setFixedSize(30, 28)
        close.clicked.connect(parent.close)
        layout.addWidget(minimize)
        layout.addWidget(close)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is None or not handle.startSystemMove():
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
                )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class MainWindow(QWidget):
    """主界面通过信号与控制器连接。"""

    region_selection_requested = pyqtSignal()
    recognition_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self.setWindowTitle("DeepSeek AI 助手")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowOpacity(0.94)
        self.setMinimumSize(320, 350)
        self.resize(380, 480)
        self.setStyleSheet("""
            MainWindow { background-color: #202630; }
            QLabel { color: #e8edf5; font-size: 13px; }
            QLabel#title { font-size: 16px; font-weight: 600; }
            QLabel#status { color: #b8c7dc; }
            QPushButton {
                background-color: #34435a; color: #ffffff;
                border: 1px solid #4d607b; border-radius: 6px;
                padding: 9px; font-size: 13px;
            }
            QPushButton:hover { background-color: #465c7a; }
            QPushButton:pressed { background-color: #28374c; }
            QPushButton:disabled { color: #8793a3; background-color: #29313d; }
            QWidget#titleBar QPushButton { padding: 0; }
            QTextEdit {
                background-color: #151b24; color: #edf2fa;
                border: 1px solid #42516a; border-radius: 6px;
                padding: 8px; font-size: 14px;
                selection-background-color: #3d6aab;
            }
            QSizeGrip { width: 18px; height: 18px; background-color: #34435a; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 6)
        layout.setSpacing(12)
        layout.addWidget(TitleBar(self))

        self.status_label = QLabel("状态：等待识别")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.region_button = QPushButton("设置题目区域")
        self.region_button.clicked.connect(self._request_region)
        layout.addWidget(self.region_button)

        self.recognize_button = QPushButton("识别题目")
        self.recognize_button.clicked.connect(self._request_recognition)
        layout.addWidget(self.recognize_button)

        layout.addWidget(QLabel("答案"))
        self.answer_edit = QTextEdit()
        self.answer_edit.setReadOnly(True)
        self.answer_edit.setPlaceholderText(
            "答案和解析将显示在这里。\n\n"
            "先设置题目区域，再点击“识别题目”。\n"
            "截图会发送至 DeepSeek 进行分析。"
        )
        layout.addWidget(self.answer_edit, 1)

        footer = QHBoxLayout()
        tip = QLabel("拖动标题栏移动 · 拖动右下角缩放")
        tip.setStyleSheet("color: #97a5ba; font-size: 11px;")
        footer.addWidget(tip)
        footer.addStretch()
        footer.addWidget(QSizeGrip(self))
        layout.addLayout(footer)

    def set_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{text}")

    def show_answer(self, text: str) -> None:
        # 以纯文本显示，避免将模型输出当作 HTML。
        self.answer_edit.setPlainText(text)
        self.set_status("识别完成")

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.region_button.setEnabled(not busy)
        self.recognize_button.setEnabled(not busy)
        if busy:
            self.set_status("正在识别，请稍候…")

    def _request_region(self) -> None:
        self.region_selection_requested.emit()

    def _request_recognition(self) -> None:
        self.recognition_requested.emit()

    def closeEvent(self, event) -> None:
        if self._busy:
            self.set_status("任务进行中，请等待完成后关闭（API 最长等待配置的 timeout 秒）")
            event.ignore()
        else:
            event.accept()
