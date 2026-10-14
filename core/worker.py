"""后台截图与 API 请求，线程中只发信号、不访问界面。"""
from PyQt6.QtCore import QThread, pyqtSignal
from core.screenshot import capture_region
from core.deepseek import analyze_image


class RecognitionWorker(QThread):
    captured = pyqtSignal(str)
    answer_ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config.copy()

    def run(self) -> None:
        try:
            path = capture_region(self.config["screen_region"])
            self.captured.emit(str(path))
            answer = analyze_image(path, self.config)
            self.answer_ready.emit(answer)
        except (ValueError, RuntimeError, OSError) as exc:
            # 已知错误消息来自本地封装，不输出请求体、密钥或 SDK 异常详情。
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("识别失败，请检查配置格式和依赖安装后重试。")
