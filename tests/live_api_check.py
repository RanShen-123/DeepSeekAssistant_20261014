"""使用人工生成的图片验证真实视觉 API，绝不上传桌面截图。"""
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from core.config import ConfigStore
from core.deepseek import analyze_image


def main() -> int:
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
        path = Path(folder) / "arithmetic.png"
        image = Image.new("RGB", (600, 180), "white")
        ImageDraw.Draw(image).text((30, 45), "Question: 2 + 3 = ?", fill="black", font_size=40)
        image.save(path)
        try:
            answer = analyze_image(path, ConfigStore().load())
        except Exception as exc:
            print("Live API check failed:", str(exc))
            return 1
        print("Live API response:", answer)
        return 0 if "5" in answer or "五" in answer else 2


if __name__ == "__main__":
    raise SystemExit(main())
