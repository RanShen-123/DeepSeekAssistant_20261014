"""后台自动流程，通过界面信号握手保证截图前窗口已经隐藏。"""
import threading
import time
from collections import deque
from datetime import datetime
import json
import uuid
from PyQt6.QtCore import QThread, pyqtSignal
from core.auto_flow import AutoFlow, AutoStopped
from core.config import validate_region, PROJECT_DIR
from core.deepseek import analyze_answer


class AutoAnswerWorker(QThread):
    progress = pyqtSignal(object)
    answer_ready = pyqtSignal(object)
    visibility_requested = pyqtSignal(bool, object)
    ended = pyqtSignal(str)

    def __init__(self, config, submit_attempts, parent=None, retry_signature=None,
                 confirmed_submissions=None, session_id=None):
        super().__init__(parent)
        self.config = config.copy()
        self.region = validate_region(config.get("screen_region"))
        self.submit_attempts = submit_attempts
        self.stop_event = threading.Event()
        self.recent_observations = deque(maxlen=4)
        self.last_progress = {}
        self.retry_signature = retry_signature
        self.confirmed_submissions = confirmed_submissions if confirmed_submissions is not None else set()
        self.session_id = session_id

    def record_progress(self, value):
        self.last_progress = value.copy()
        self.progress.emit(value)

    def report_failure(self, message):
        if self.cancelled():
            self.ended.emit("已停止。")
            return
        if self.recent_observations:
            try:
                folder = PROJECT_DIR/"outputs"/f"auto_debug_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
                folder.mkdir(parents=True, exist_ok=False)
                for index, item in enumerate(self.recent_observations, 1):
                    item["image"].save(folder/f"{index:02d}_original.png")
                    (folder/f"{index:02d}_report.json").write_text(
                        json.dumps(item["report"], ensure_ascii=False, indent=2), encoding="utf-8")
                (folder/"failure.json").write_text(json.dumps(
                    {"reason": message, "stage": self.last_progress, "screen_region": self.region,
                     "session_id": self.session_id, "pending_submissions": sorted(self.submit_attempts),
                     "confirmed_submissions": sorted(self.confirmed_submissions)},
                    ensure_ascii=False, indent=2), encoding="utf-8")
                message += f"\n诊断已保存：{folder}"
            except Exception:
                message += "\n诊断文件保存失败。"
        self.ended.emit(message)

    def stop(self):
        self.stop_event.set()

    def cancelled(self):
        from vision.mouse_input import escape_pressed
        return self.stop_event.is_set() or escape_pressed()

    def visibility(self, visible):
        ready = threading.Event()
        self.visibility_requested.emit(visible, ready)
        deadline = time.monotonic()+5
        while not ready.wait(.05):
            if self.cancelled():
                raise AutoStopped("已停止，等待中的 AI 答案不会用于点击。")
            if time.monotonic() > deadline:
                raise RuntimeError("界面未响应显示/隐藏请求，已暂停。")
        if self.cancelled():
            raise AutoStopped("已停止。")

    def run(self):
        try:
            from vision.control_reader import ControlReader
            from vision.screen_session import capture_image, analyze_capture
            from vision.mouse_input import click_physical
            reader = ControlReader()

            def observe():
                self.visibility(False)
                image = capture_image(self.region)
                entry = {"image": image, "report": None}
                self.recent_observations.append(entry)
                result = analyze_capture(image, self.region, reader)
                entry["report"] = result.report
                if result.report.get("page_blocker"):
                    raise RuntimeError("页面安全核验已暂停自动答题，请手动完成核验后重新开始；未尝试绕过验证。")
                if self.cancelled():
                    raise AutoStopped("已停止。")
                return result

            def ask(image, kind, labels):
                self.visibility(True)
                answer = analyze_answer(image, self.config, kind, labels)
                if self.cancelled():
                    raise AutoStopped("已停止，AI 返回的答案已丢弃。")
                return answer

            AutoFlow(observe, ask, click_physical, self.cancelled, lambda: self.stop_event.wait(.5),
                     self.record_progress, self.answer_ready.emit, self.submit_attempts,
                     retry_signature=self.retry_signature, confirmed_submissions=self.confirmed_submissions).run()
            self.ended.emit("全部作答完成（已提交且下一题灰色禁用）。")
        except ImportError:
            self.report_failure("自动答题暂停：缺少本地视觉依赖，请安装 requirements-vision.txt。")
        except (ValueError, RuntimeError, OSError) as exc:
            self.report_failure(f"自动答题暂停：{exc}")
        except Exception:
            self.report_failure("自动答题暂停：发生未预期错误，没有继续操作。")
