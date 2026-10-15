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
    auto_start_requested = pyqtSignal()
    auto_stop_requested = pyqtSignal()
    auto_retry_requested = pyqtSignal()
    auto_new_round_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._retry_available = False
        self._display_question_signature = None
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

        auto_row = QHBoxLayout()
        self.auto_button = QPushButton("开始自动答题")
        self.auto_button.clicked.connect(lambda: self.auto_start_requested.emit())
        self.stop_button = QPushButton("停止（Esc）")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(lambda: self.auto_stop_requested.emit())
        auto_row.addWidget(self.auto_button)
        auto_row.addWidget(self.stop_button)
        layout.addLayout(auto_row)
        self.retry_button = QPushButton("重新检查并重试本题")
        self.retry_button.setToolTip("请先手动完成安全核验。本按钮只授权当前待恢复题重新核对后提交一次。")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(lambda: self.auto_retry_requested.emit())
        layout.addWidget(self.retry_button)
        self.new_round_button = QPushButton("新一轮答题（清除旧记录）")
        self.new_round_button.setToolTip("重新开始另一套题或重新作答时使用。清除本地待确认/成功记录并启动；不改变网页记录，不自动处理安全核验。")
        self.new_round_button.clicked.connect(lambda: self.auto_new_round_requested.emit())
        layout.addWidget(self.new_round_button)
        self.auto_info = QLabel("自动模式：单选/判断；已提交且下一题灰色时结束")
        self.auto_info.setWordWrap(True)
        layout.addWidget(self.auto_info)

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
        self.auto_button.setEnabled(not busy)
        self.new_round_button.setEnabled(not busy)
        self.retry_button.setEnabled(not busy and self._retry_available)
        if busy:
            self.set_status("正在识别，请稍候…")

    def _request_region(self) -> None:
        self.region_selection_requested.emit()

    def _request_recognition(self) -> None:
        self.recognition_requested.emit()

    def set_auto_running(self, running: bool) -> None:
        self.set_busy(running)
        self.stop_button.setEnabled(running)

    def set_retry_available(self, available: bool) -> None:
        self._retry_available = available
        self.retry_button.setEnabled(available and not self._busy)

    def show_auto_progress(self, data: dict) -> None:
        signature = data.get("question_signature")
        if signature and signature != self._display_question_signature:
            self.answer_edit.clear()
            self._display_question_signature = signature
        kind = {"single": "单选题", "boolean": "判断题"}.get(data.get("question_type"), "待识别")
        self.auto_info.setText(f"题型：{kind}；本次确认提交：{data['confirmed']}；跳过已提交：{data['skipped']}")
        self.set_status(data["status"])

    def show_auto_answer(self, data: dict) -> None:
        answer = {"true": "√（正确）", "false": "×（错误）"}.get(data["answer"][0], data["answer"][0])
        self.answer_edit.setPlainText(f"AI 答案：{answer}\n\n解析：\n{data['explanation']}")

    def closeEvent(self, event) -> None:
        if self._busy:
            self.set_status("任务进行中，请等待完成后关闭（API 最长等待配置的 timeout 秒）")
            event.ignore()
        else:
            event.accept()
