"""协调主窗口、选区配置和异步识别任务。"""
from PyQt6.QtCore import QObject, QTimer
from core.config import ConfigStore, validate_region
from core.worker import RecognitionWorker
from ui.selector import RegionSelector


class AssistantController(QObject):
    def __init__(self, window, store: ConfigStore | None = None) -> None:
        super().__init__(window)
        self.window = window
        self.store = store or ConfigStore()
        self.selector = RegionSelector(self)
        self.worker = None
        self.selecting = False
        window.region_selection_requested.connect(self.select_region)
        window.recognition_requested.connect(self.recognize)
        self.selector.selected.connect(self.save_region)
        self.selector.cancelled.connect(self.cancel_selection)

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
