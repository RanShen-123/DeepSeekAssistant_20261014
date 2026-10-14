"""使用物理像素坐标截屏，支持负坐标显示器。"""
from pathlib import Path
from datetime import datetime
import uuid
import mss
from PIL import Image
from core.config import PROJECT_DIR, validate_region


def capture_region(region: dict, output_dir: Path | None = None) -> Path:
    region = validate_region(region)
    folder = Path(output_dir) if output_dir else PROJECT_DIR / "screenshots"
    try:
        with mss.mss() as capture:
            # 选区必须完整位于一个显示器内，避免跨屏缩放和空白区域。
            if not any(region["x"] >= m["left"] and region["y"] >= m["top"]
                       and region["x"] + region["width"] <= m["left"] + m["width"]
                       and region["y"] + region["height"] <= m["top"] + m["height"]
                       for m in capture.monitors[1:]):
                raise ValueError("保存的区域不在当前显示器内，请重新设置题目区域。")
            shot = capture.grab({"left": region["x"], "top": region["y"],
                                 "width": region["width"], "height": region["height"]})
            picture = Image.frombytes("RGB", shot.size, shot.rgb)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"question_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.png"
        picture.save(path, "PNG")
        return path
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError("截图失败，请检查显示器连接和截图目录权限。") from exc
