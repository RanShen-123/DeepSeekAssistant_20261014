"""采集/读取截图，诊断严格题目标识差异；无 API、鼠标或自动答题。"""
import argparse
from datetime import datetime
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def diagnose_image(image, engine):
    import cv2
    import numpy as np
    from vision.control_reader import ControlReader, content_bbox
    from vision.screen_session import annotate_controls

    bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    ox, oy, width, height = content_bbox(bgr)
    lines = engine.read(bgr[oy:oy+height, ox:ox+width])

    class RecordedOCR:
        def read(self, content):
            return lines

        def read_crop(self, *args, **kwargs):
            return engine.read_crop(*args, **kwargs)

    # 使用同一批 OCR 文字生成实际报告，避免为诊断再 OCR 一遍引入新差异。
    report = ControlReader(RecordedOCR()).read(image)
    bottom = min((c["bbox"][1]-oy for c in report["controls"] if c["kind"].endswith("option")), default=0)
    records, included = [], []
    for line in sorted(lines, key=lambda item: (item.bbox[1], item.bbox[0])):
        use = line.bbox[1]+line.bbox[3] < bottom
        normalized = re.sub(r"\s", "", line.text)
        records.append({"text": line.text, "normalized": normalized, "score": line.score,
                        "bbox": [line.bbox[0]+ox, line.bbox[1]+oy, *line.bbox[2:]],
                        "included_in_signature": use})
        if use:
            included.append(normalized)
    text = "|".join(included)
    legacy = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
    identity = report.get("question_identity")
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if identity else ""
    rebuilt = hashlib.sha256(serialized.encode("utf-8")).hexdigest() if serialized else None
    identity_lines = ([identity["stem"]]+[json.dumps(item, ensure_ascii=False) for item in identity["options"]]) if identity else []
    details = {"question_text_used": serialized, "question_lines_used": identity_lines,
               "legacy_text_including_header": text, "legacy_signature": legacy,
               "option_top_in_content": bottom, "ocr_lines": records,
               "signature_rebuild_matches": rebuilt == report["question_signature"], "report": report}
    return details, annotate_controls(image, report)


def comparison(before, after):
    a, b = before["report"], after["report"]
    reasons = []
    if a["question_signature"] != b["question_signature"]:
        reasons.append("严格题目标识不一致，会在点击前暂停")
    if not b["question_signature"]:
        reasons.append("新截图题目标识为空：优先检查圆圈漏检或题干未框入")
    if a["content_bbox"] != b["content_bbox"]:
        reasons.append("主内容裁剪范围改变：检查侧栏分隔线或窗口遮挡")
    if before["question_lines_used"] != after["question_lines_used"]:
        reasons.append("参与标识的 OCR 文字或分行改变，见 question_diff.txt")
    labels_a = [(c["kind"], c["label"]) for c in a["controls"] if c["kind"].endswith("option")]
    labels_b = [(c["kind"], c["label"]) for c in b["controls"] if c["kind"].endswith("option")]
    if labels_a != labels_b:
        reasons.append("选项检测结果变化")
    if a["question_signature"] == b["question_signature"] and before.get("legacy_signature") != after.get("legacy_signature"):
        reasons.append("旧标识因标题/分行变化而不同，新标识已稳定匹配")
    return {"strict_signature_equal": bool(a["question_signature"] and a["question_signature"] == b["question_signature"]),
            "text_equal_ignoring_line_breaks": "".join(before["question_lines_used"]) == "".join(after["question_lines_used"]),
            "findings": reasons or ["两次题目标识一致，本组样本未复现该拦截"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--capture", action="store_true", help="读取已保存选区，倒计时后截图；不点击")
    source.add_argument("--images", nargs="+", type=Path, help="已有原尺寸截图，不操作桌面")
    parser.add_argument("--count", type=int, default=3, help="采集张数，2~10")
    parser.add_argument("--interval", type=float, default=2, help="采集间隔秒数，0.2~30")
    args = parser.parse_args()
    if not 2 <= args.count <= 10 or not .2 <= args.interval <= 30:
        parser.error("count 应为 2~10，interval 应为 0.2~30")
    if args.images and len(args.images) < 2:
        parser.error("至少提供两张图片才能比较")
    from PIL import Image
    from vision.ocr_engine import LocalOCR
    region = None
    if args.capture:
        import ctypes
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            except (AttributeError, OSError):
                pass
        from core.config import ConfigStore, validate_region
        from vision.screen_session import capture_image
        region = validate_region(ConfigStore().load().get("screen_region"))
        print("仅截图和本地 OCR，不调用 API、不移动或点击鼠标。", flush=True)
        print(f"使用已保存物理选区：{region}。请暂停自动助手并将终端移出答题区域。", flush=True)
        for remaining in range(5, 0, -1):
            print(f"{remaining} 秒后开始采集…", flush=True)
            time.sleep(1)
        # 先采图再 OCR，以便观察实际页面变化而不是 OCR 耗时。
        pictures = []
        for index in range(args.count):
            pictures.append(capture_image(region))
            if index+1 < args.count:
                time.sleep(args.interval)
    else:
        pictures = []
        for path in args.images:
            with Image.open(path) as image:
                pictures.append(image.convert("RGB"))
    folder = ROOT/"outputs"/f"diagnose_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    folder.mkdir(parents=True, exist_ok=False)
    # 即使 OCR 失败也保留原图，便于复查；不保存 API 配置。
    for index, image in enumerate(pictures, 1):
        image.save(folder/f"{index:02d}_original.png")
    print(f"诊断输出：{folder}", flush=True)
    engine = LocalOCR()
    results = []
    for index, image in enumerate(pictures, 1):
        details, marked = diagnose_image(image, engine)
        details["screen_region"] = region
        (folder/f"{index:02d}_ocr.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
        marked.save(folder/f"{index:02d}_marked.png")
        results.append(details)
    comparisons, diff_lines = [], []
    for index in range(1, len(results)):
        pair = comparison(results[index-1], results[index])
        pair["images"] = [index, index+1]
        comparisons.append(pair)
        diff_lines.extend(difflib.unified_diff(results[index-1]["question_lines_used"],
                                              results[index]["question_lines_used"],
                                              fromfile=f"image_{index}", tofile=f"image_{index+1}", lineterm=""))
        print(f"图片 {index} → {index+1}："+"；".join(pair["findings"]), flush=True)
    (folder/"comparison.json").write_text(json.dumps(comparisons, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder/"question_diff.txt").write_text("\n".join(diff_lines) or "参与标识的文字行一致。", encoding="utf-8")
    print("完成。请检查 comparison.json、question_diff.txt 和各张标注图。", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("诊断已取消。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"诊断未完成：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
