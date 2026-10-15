"""输入现有截图，输出原尺寸标注图和 JSON；不访问 API 或鼠标。"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vision.page_reader import PageReader
from vision.annotation import annotate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, nargs="+", required=True, help="一张或多张现有截图")
    parser.add_argument("--output-dir", type=Path, help="新建结果目录，拒绝覆盖旧目录")
    args = parser.parse_args(argv)
    paths = [p.resolve() for p in args.image]
    for path in paths:
        if not path.is_file():
            raise ValueError(f"输入图片不存在：{path}")
    folder = args.output_dir or ROOT/"outputs"/("vision_"+time.strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6])
    if folder.exists():
        raise ValueError("输出目录已存在，请指定一个新目录。")
    reader = PageReader()
    folder.mkdir(parents=True)
    for index, path in enumerate(paths, 1):
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        started = time.monotonic()
        result = reader.read(image)
        destination = folder/f"{index:02d}_{path.stem[:60]}"
        destination.mkdir()
        image.save(destination/"original.png")
        annotate(image, result).save(destination/"marked.png")
        data = result.to_dict()
        data["input_file"] = str(path)
        data["elapsed_seconds"] = round(time.monotonic()-started, 3)
        (destination/"result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(destination), "type": result.question_type,
                          "header": result.header_question_number, "sidebar": result.sidebar_question_number,
                          "completed": result.completed_count, "total": result.total_count,
                          "options": [{"label": c.label, "center": c.center, "confidence": round(c.confidence, 3)}
                                      for c in result.controls if c.kind.endswith("option")],
                          "buttons": [c.id for c in result.controls if c.kind == "button"],
                          "elapsed": data["elapsed_seconds"]}, ensure_ascii=False), flush=True)
    print(f"RESULT_DIRECTORY={folder.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, ImportError) as exc:
        print(f"离线识别失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
