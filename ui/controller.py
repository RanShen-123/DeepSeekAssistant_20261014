"""协调主窗口、选区配置和异步识别任务。"""
from PyQt6.QtCore import QObject, QTimer
from core.config import ConfigStore, validate_region
from core.worker import RecognitionWorker
from ui.selector import RegionSelector
from core.auto_worker import AutoAnswerWorker
import uuid


class AssistantController(QObject):
    def __init__(self, window, store: ConfigStore | None = None) -> None:
        super().__init__(window)
        self.window = window
        self.store = store or ConfigStore()
        self.selector = RegionSelector(self)
        self.worker = None
        self.selecting = False
        self.submit_attempts = set()
        self.confirmed_submissions = set()
        self.session_id = uuid.uuid4().hex
        self._auto_end_message = None
        self.retry_target = None
        window.region_selection_requested.connect(self.select_region)
        window.recognition_requested.connect(self.recognize)
        window.auto_start_requested.connect(self.start_auto)
        window.auto_stop_requested.connect(self.stop_auto)
        window.auto_retry_requested.connect(self.retry_auto)
        window.auto_new_round_requested.connect(self.new_auto_round)
        self.selector.selected.connect(self.save_region)
        self.selector.cancelled.connect(self.cancel_selection)
        self.escape_timer = QTimer(self)
        self.escape_timer.setInterval(40)
        self.escape_timer.timeout.connect(self._poll_escape)
        self.escape_timer.start()

    def _poll_escape(self):
        if isinstance(self.worker, AutoAnswerWorker):
            from vision.mouse_input import escape_pressed
            if escape_pressed():
                self.stop_auto()

    def start_auto(self):
        self._start_auto()

    def new_auto_round(self):
        if not self.worker and not self.selecting:
            self._start_auto(new_round=True)

    def retry_auto(self):
        if self.worker or self.selecting:
            return
        if not self.retry_target or self.retry_target not in self.submit_attempts:
            self.window.set_status("没有待恢复的提交，请使用普通开始。")
            return
        self._start_auto(retry_signature=self.retry_target)

    def _start_auto(self, retry_signature=None, new_round=False):
        if self.worker or self.selecting:
            return
        try:
            config = self.store.load()
            validate_region(config.get("screen_region"))
            if not str(config.get("api_key") or "").strip():
                raise ValueError("缺少 API Key，请检查 config.yaml。")
            timeout = float(config.get("timeout", 90))
            if not 1 <= timeout <= 300:
                raise ValueError("timeout 必须在 1 到 300 秒之间。")
            if new_round:
                self.submit_attempts.clear()
                self.confirmed_submissions.clear()
                self.retry_target = None
                self.session_id = uuid.uuid4().hex
                self.window.set_retry_available(False)
            self.worker = AutoAnswerWorker(config, self.submit_attempts, self, retry_signature=retry_signature,
                                           confirmed_submissions=self.confirmed_submissions, session_id=self.session_id)
        except Exception as exc:
            self.error(str(exc))
            return
        self._auto_end_message = None
        self.window.answer_edit.clear()
        self.window.auto_info.setText("本轮任务启动，正在检查当前题目")
        self.window.set_auto_running(True)
        self.window.set_status("自动答题启动，Esc 可停止；请勿移动或遮挡答题页面")
        self.worker.progress.connect(self.window.show_auto_progress)
        self.worker.answer_ready.connect(self.window.show_auto_answer)
        self.worker.visibility_requested.connect(self._auto_visibility)
        self.worker.ended.connect(self._auto_ended)
        self.worker.finished.connect(self._auto_finished)
        self.window.hide()
        QTimer.singleShot(250, self.worker.start)

    def _auto_visibility(self, visible, ready):
        if visible:
            self.window.show()
        else:
            self.window.hide()
        QTimer.singleShot(250, ready.set)

    def stop_auto(self):
        if isinstance(self.worker, AutoAnswerWorker):
            self.worker.stop()
            self.window.set_status("已请求停止；等待中的 API 请求返回后结束，不再点击")

    def _auto_ended(self, message):
        self._auto_end_message = message

    def _auto_finished(self):
        previous, self.worker = self.worker, None
        self.retry_target = None
        if previous:
            for item in reversed(previous.recent_observations):
                report = item.get("report") or {}
                signature = report.get("question_signature")
                if signature in self.submit_attempts:
                    if report.get("page_state", {}).get("submitted") is True:
                        self.submit_attempts.discard(signature)
                        self.confirmed_submissions.add(signature)
                    else:
                        self.retry_target = signature
                    break
        self.window.show()
        self.window.set_auto_running(False)
        self.window.set_retry_available(self.retry_target is not None)
        self.window.set_status(self._auto_end_message or "自动答题已停止")
        if previous:
            previous.deleteLater()

    def initialize(self) -> None:
        try:
            region = self.store.load().get("screen_region")
            if region is None:
                self.select_region()
            else:
                validate_region(region)
                self.window.set_status("等待识别（已读取题目区域）")
        except Exception as exc:
            self.error(str(exc))

    def error(self, message: str) -> None:
        self.window.show()
        self.window.set_status(message)
        self.window.answer_edit.setPlainText("识别未完成：\n" + message)

    def select_region(self) -> None:
        if self.worker or self.selecting:
            return
        self.selecting = True
        self.window.set_busy(True)
        self.window.set_status("请框选题目区域")
        self.window.hide()
        QTimer.singleShot(200, self._open_selector)

    def _open_selector(self) -> None:
        try:
            self.selector.start()
        except Exception as exc:
            self.selector.cleanup()
            self.selecting = False
            self.window.set_busy(False)
            self.error(str(exc))

    def save_region(self, region: dict) -> None:
        self.selecting = False
        self.window.set_busy(False)
        self.window.show()
        try:
            self.store.set_region(region)
            self.window.set_status(f"区域已保存：{region['width']} × {region['height']} 像素")
        except Exception:
            self.error("选区保存失败，请检查 config.yaml 的写入权限。")

    def cancel_selection(self) -> None:
        self.selecting = False
        self.window.set_busy(False)
        self.window.show()
        self.window.set_status("已取消框选，保留原有区域")

    def recognize(self) -> None:
        if self.worker or self.selecting:
            return
        try:
            config = self.store.load()
            validate_region(config.get("screen_region"))
            if not str(config.get("api_key") or "").strip():
                raise ValueError("缺少 API Key，请在 config.yaml 中填写 api_key。")
            timeout = float(config.get("timeout", 90))
            if not 1 <= timeout <= 300:
                raise ValueError("timeout 必须在 1 到 300 秒之间。")
        except Exception as exc:
            self.error(str(exc))
            return
        self.window.answer_edit.clear()
        self.window.set_busy(True)
        self.window.set_status("正在截图…")
        self.window.hide()
        self.worker = RecognitionWorker(config, self)
        self.worker.captured.connect(self._captured)
        self.worker.answer_ready.connect(self.window.show_answer)
        self.worker.failed.connect(self.error)
        self.worker.finished.connect(self._finished)
        QTimer.singleShot(250, self.worker.start)

    def _captured(self, path: str) -> None:
        self.window.show()
        self.window.set_status("截图完成，AI 正在分析…")

    def _finished(self) -> None:
        self.window.show()
        self.window.set_busy(False)
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
