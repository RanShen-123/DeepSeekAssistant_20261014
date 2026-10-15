"""独立交互测试：手动框选 → 内存截图 → 本地定位 → 预览，点击保存才写文件。"""
import ctypes
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QLineEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from core.config import validate_region
from ui.selector import RegionSelector
from vision.screen_session import capture_image, analyze_capture, save_result
from vision.manual_answer import normalize_answer, matching_option, choose_once
from vision.mouse_input import click_physical, escape_pressed
from vision.manual_buttons import matching_button, button_once


class ImageView(QScrollArea):
    def __init__(self):
        super().__init__()
        self.label = QLabel("尚无图片")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self.label)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pixmap = None
        self.fit = True
        self.rendering = False

    def set_image(self, image):
        # Qt 必须持有自己的像素副本；临时转换对象释放后仍可能被缩放器读取。
        rgb = image.convert("RGB")
        pixels = rgb.tobytes()
        owned = QImage(pixels, rgb.width, rgb.height, rgb.width * 3,
                       QImage.Format.Format_RGB888).copy()
        if owned.isNull():
            raise ValueError("无法创建预览图片。")
        self.pixmap = QPixmap.fromImage(owned)
        self.render()

    def clear_image(self):
        self.pixmap = None
        self.label.clear()
        self.label.setText("等待本次截图识别")

    def render(self):
        if self.pixmap is None or self.rendering:
            return
        self.rendering = True
        try:
            pixmap = self.pixmap
            if self.fit:
                pixmap = pixmap.scaled(self.viewport().size(), Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
            self.label.setPixmap(pixmap)
            self.label.resize(pixmap.size())
        finally:
            self.rendering = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "rendering"):
            self.render()


class CaptureWorker(QThread):
    captured = pyqtSignal()
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, region, parent=None):
        super().__init__(parent)
        self.region = validate_region(region)

    def run(self):
        try:
            image = capture_image(self.region)
            self.captured.emit()
            from vision.control_reader import ControlReader
            result = analyze_capture(image, self.region, ControlReader())
            self.result_ready.emit(result)
        except ImportError:
            self.failed.emit("缺少本地识别依赖，请用第二版虚拟环境安装 requirements-vision.txt。")
        except (ValueError, OSError, RuntimeError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"本地识别失败（{type(exc).__name__}），请检查选区和依赖。")


class ManualClickWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    clicking = pyqtSignal(str)

    def __init__(self, region, baseline, answer, parent=None, action="answer"):
        super().__init__(parent)
        self.region = validate_region(region)
        self.baseline = baseline
        self.answer = answer
        self.action = action
        self.stop_event = threading.Event()

    def cancelled(self):
        return self.stop_event.is_set() or escape_pressed()

    def run(self):
        try:
            from vision.control_reader import ControlReader
            reader = ControlReader()

            def observe():
                if self.cancelled():
                    raise RuntimeError("已停止。")
                return analyze_capture(capture_image(self.region), self.region, reader)

            def send_click(x, y, cancelled):
                if cancelled():
                    raise RuntimeError("已停止，未点击。")
                self.clicking.emit(self.action)
                click_physical(x, y, cancelled)

            if self.action == "answer":
                result = choose_once(self.baseline, self.answer, observe, send_click,
                                     self.cancelled, lambda: self.stop_event.wait(.4))
            else:
                result = button_once(self.baseline, self.action, observe, send_click,
                                     self.cancelled, lambda: self.stop_event.wait(.5))
            self.result_ready.emit(result)
        except Exception as exc:
            self.failed.emit(f"手动操作停止：{exc}（不会重试或继续其它操作）")


class ScreenPreview(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("第二版控件识别与手动答案单击实验")
        self.resize(1180, 800)
        self.region = None
        self.result = None
        self.worker = None
        self.busy = False
        self.selecting = False
        self.saved = False
        self.submit_attempts = set()
        self.selector = RegionSelector(self)
        self.selector.selected.connect(self.region_selected)
        self.selector.cancelled.connect(self.selection_cancelled)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        self.select_button = QPushButton("框选并识别")
        self.repeat_button = QPushButton("重新识别当前区域")
        self.save_button = QPushButton("保存结果")
        self.select_button.clicked.connect(self.select_region)
        self.repeat_button.clicked.connect(self.repeat)
        self.save_button.clicked.connect(self.save)
        for button in (self.select_button, self.repeat_button, self.save_button):
            toolbar.addWidget(button)
        fit_button = QPushButton("适应窗口")
        actual_button = QPushButton("原始尺寸")
        fit_button.clicked.connect(lambda: self.set_fit(True))
        actual_button.clicked.connect(lambda: self.set_fit(False))
        toolbar.addStretch()
        toolbar.addWidget(fit_button)
        toolbar.addWidget(actual_button)
        layout.addLayout(toolbar)
        answer_bar = QHBoxLayout()
        answer_bar.addWidget(QLabel("手动答案："))
        self.answer_input = QLineEdit()
        self.answer_input.setPlaceholderText("A / B / C / D，或 √ / × / 正确 / 错误")
        self.answer_input.setMaxLength(12)
        self.click_button = QPushButton("点击对应选项（一次）")
        self.click_button.clicked.connect(self.click_answer)
        self.stop_button = QPushButton("停止（Esc）")
        self.stop_button.clicked.connect(self.stop_click)
        answer_bar.addWidget(self.answer_input, 1)
        answer_bar.addWidget(self.click_button)
        answer_bar.addWidget(self.stop_button)
        layout.addLayout(answer_bar)
        action_bar = QHBoxLayout()
        self.submit_button = QPushButton("点击提交（一次）")
        self.next_button = QPushButton("点击下一题（一次）")
        self.submit_button.clicked.connect(lambda: self.click_page_button("submit"))
        self.next_button.clicked.connect(lambda: self.click_page_button("next"))
        action_bar.addWidget(self.submit_button)
        action_bar.addWidget(self.next_button)
        action_bar.addStretch()
        layout.addLayout(action_bar)
        help_label = QLabel("框入顶部题型、全部选项与底部按钮。选择、提交、下一题分别手动触发，各执行一次，不自动串联。Esc 可停止任务或取消框选。")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self.region_label = QLabel("选区：尚未框选（仅保存在测试程序内存，不修改助手配置）")
        self.region_label.setWordWrap(True)
        layout.addWidget(self.region_label)
        self.type_label = QLabel("题型：尚未识别")
        layout.addWidget(self.type_label)
        self.page_state_label = QLabel("页面状态：尚未识别")
        self.page_state_label.setWordWrap(True)
        layout.addWidget(self.page_state_label)
        splitter = QSplitter()
        self.tabs = QTabWidget()
        self.marked_view, self.original_view = ImageView(), ImageView()
        self.tabs.addTab(self.marked_view, "控件标注")
        self.tabs.addTab(self.original_view, "本次原图")
        splitter.addWidget(self.tabs)
        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.addWidget(QLabel("候选控件坐标（屏幕坐标为物理像素）"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["控件", "图内中心", "屏幕中心", "匹配分数", "可用状态", "选择状态"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        details_layout.addWidget(self.table, 2)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setPlaceholderText("识别结果与不确定原因显示在这里。不会读取左侧题号和进度。")
        details_layout.addWidget(self.messages, 1)
        splitter.addWidget(details)
        splitter.setSizes([760, 420])
        layout.addWidget(splitter, 1)
        self.status = QLabel("就绪。点击“框选并识别”开始，结果暂存内存。")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.escape_timer = QTimer(self)
        self.escape_timer.setInterval(40)
        self.escape_timer.timeout.connect(self.poll_escape)
        self.escape_timer.start()
        self.update_buttons()

    def update_buttons(self):
        self.select_button.setEnabled(not self.busy)
        self.repeat_button.setEnabled(not self.busy and self.region is not None)
        self.save_button.setEnabled(not self.busy and self.result is not None and not self.saved)
        self.click_button.setEnabled(not self.busy and self.result is not None and self.region is not None)
        self.submit_button.setEnabled(not self.busy and self.result is not None and self.region is not None)
        self.next_button.setEnabled(not self.busy and self.result is not None and self.region is not None)
        self.answer_input.setEnabled(not self.busy)
        self.stop_button.setEnabled(isinstance(self.worker, ManualClickWorker))

    def poll_escape(self):
        if isinstance(self.worker, ManualClickWorker) and escape_pressed():
            self.stop_click()

    def stop_click(self):
        if isinstance(self.worker, ManualClickWorker):
            self.worker.stop_event.set()
            self.status.setText("已请求停止，等待后台返回；不会再发送新的单击。")

    def click_answer(self):
        if self.busy or self.result is None or self.region is None:
            return
        try:
            answer = normalize_answer(self.answer_input.text())
            matching_option(self.result.report, answer)
            if not self.result.report.get("question_signature"):
                raise ValueError("题目无法确认，请重新框入顶部题型和完整题干。")
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        baseline = self.result.report
        self.busy = True
        self.result, self.saved = None, False
        self.worker = ManualClickWorker(self.region, baseline, answer, self)
        self.worker.result_ready.connect(self.result_ready)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.status.setText("重新截图核对题目后单击目标选项；Esc 停止。请勿移动或遮挡答题页面。")
        self.update_buttons()
        self.hide()
        QTimer.singleShot(300, self.worker.start)

    def click_page_button(self, action):
        if self.busy or self.result is None or self.region is None:
            return
        baseline = self.result.report
        try:
            signature = baseline.get("question_signature")
            if not signature:
                raise ValueError("题目无法确认，请完整框入题型和题干。")
            if action == "submit" and signature in self.submit_attempts:
                raise ValueError("本题已发送过提交请求，禁止重复提交；请重新识别并核对页面。")
            matching_button(baseline, action)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.busy = True
        self.result, self.saved = None, False
        self.worker = ManualClickWorker(self.region, baseline, None, self, action=action)
        self.worker.clicking.connect(lambda sent: self.submit_attempts.add(signature) if sent == "submit" else None)
        self.worker.result_ready.connect(self.result_ready)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.status.setText("重新截图核对后单击按钮，随后检查状态。Esc 停止。")
        self.update_buttons()
        self.hide()
        QTimer.singleShot(300, self.worker.start)

    def set_fit(self, fit):
        for view in (self.marked_view, self.original_view):
            view.fit = fit
            view.render()

    def select_region(self):
        if self.busy:
            return
        self.busy, self.selecting = True, True
        self.update_buttons()
        self.hide()
        QTimer.singleShot(200, self.open_selector)

    def open_selector(self):
        try:
            self.selector.start()
        except Exception as exc:
            self.selector.cleanup()
            self.busy, self.selecting = False, False
            self.show()
            self.status.setText(f"无法打开框选：{exc}")
            self.update_buttons()

    def region_selected(self, region):
        self.selecting = False
        try:
            self.region = validate_region(region)
            self.region_label.setText(f"物理选区：x={self.region['x']}，y={self.region['y']}，"
                                      f"宽={self.region['width']}，高={self.region['height']}（不写配置）")
            self.begin_capture()
        except (ValueError, OSError) as exc:
            self.busy = False
            self.show()
            self.status.setText(str(exc))
            self.update_buttons()

    def selection_cancelled(self):
        self.busy, self.selecting = False, False
        self.show()
        self.status.setText("已取消框选，保留原选区和已有预览，没有截图。")
        self.update_buttons()

    def repeat(self):
        if not self.busy and self.region is not None:
            self.begin_capture()

    def begin_capture(self):
        self.busy = True
        self.result, self.saved = None, False
        self.table.setRowCount(0)
        self.messages.clear()
        self.type_label.setText("题型：正在识别")
        self.page_state_label.setText("页面状态：正在识别")
        self.marked_view.clear_image()
        self.original_view.clear_image()
        self.status.setText("正在截取当次选区…")
        self.update_buttons()
        self.hide()
        self.worker = CaptureWorker(self.region, self)
        self.worker.captured.connect(self.capture_done)
        self.worker.result_ready.connect(self.result_ready)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        QTimer.singleShot(250, self.worker.start)

    def capture_done(self):
        self.show()
        self.status.setText("截图已在内存中，本地 OCR 正在识别题型与控件…")

    def result_ready(self, result):
        self.result = result
        self.marked_view.set_image(result.marked)
        self.original_view.set_image(result.original)
        self.tabs.setCurrentIndex(0)
        report = result.report
        kind = {"single": "单选题", "boolean": "判断题", "multiple": "多选题"}.get(report["question_type"], "未知")
        self.type_label.setText("题型："+kind)
        state = report.get("page_state", {})
        submitted = {True: "已提交", False: "未提交", None: "未知"}.get(state.get("submitted"))
        next_state = {True: "可用", False: "灰色禁用", None: "未知"}.get(state.get("next_enabled"))
        can_submit = {True: "可提交（蓝色）", False: "不可提交", None: "未知"}.get(state.get("can_submit"))
        self.page_state_label.setText(f"提交：{submitted}；是否可提交：{can_submit}；下一题：{next_state}。"+
                                      state.get("message", "尚未判断")+"（仅预览，不执行）")
        self.table.setRowCount(len(report["controls"]))
        for row, control in enumerate(report["controls"]):
            label = {"true": "√", "false": "×"}.get(control["label"], control["label"]) or "未知"
            enabled = {True: "可用", False: "禁用", None: "未知"}.get(control.get("enabled"))
            selected = ({True: "已选择", False: "未选择", None: "未知"}.get(control.get("selected"))
                        if control.get("kind", "").endswith("option") else "—")
            values = (label, str(control["center"]), str(control["screen_center"]), f"{control['confidence']:.3f}", enabled, selected)
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.messages.setPlainText("\n".join(report["warnings"])+
                                   "\n\n分数表示识别/匹配结果，不是点击可靠性的保证。")
        self.status.setText(f"本地识别完成：{len(report['controls'])} 个候选控件。尚未保存任何结果文件。")
        if "manual_click" in report:
            self.status.setText(report["manual_click"]["message"]+" 可保存本次验证截图与 JSON。")
        if "manual_action" in report:
            self.status.setText(report["manual_action"]["message"]+" 可保存本次截图与 JSON。")

    def failed(self, message):
        self.show()
        self.type_label.setText("题型：识别未完成")
        self.page_state_label.setText("页面状态：识别未完成")
        self.status.setText("识别失败："+message)

    def finished(self):
        self.busy = False
        self.show()
        previous, self.worker = self.worker, None
        if previous:
            previous.deleteLater()
        self.update_buttons()

    def save(self):
        if self.busy or self.result is None or self.saved:
            return
        try:
            folder = save_result(self.result, ROOT/"outputs")
            self.saved = True
            self.status.setText(f"已保存 original.png、marked.png 和 result.json：{folder}")
        except (ValueError, OSError) as exc:
            self.status.setText(f"保存失败：{exc}。可能已有部分输出，请检查 outputs。")
        self.update_buttons()

    def closeEvent(self, event):
        if self.busy:
            self.status.setText("正在截图或识别，请等待完成后关闭；框选可按 Esc 取消。")
            event.ignore()
        else:
            self.selector.cleanup()
            event.accept()


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("控件识别交互实验")
    window = ScreenPreview()
    available = app.primaryScreen().availableGeometry() if app.primaryScreen() else None
    if available:
        window.resize(min(1180, int(available.width()*.92)), min(800, int(available.height()*.9)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
