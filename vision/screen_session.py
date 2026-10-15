"""交互实验数据：截图和识别只在内存中，用户点击保存时才写入输出目录。"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import uuid
from PIL import Image, ImageDraw
from core.config import validate_region
from vision.annotation import font


def capture_image(region):
    import mss
    region = validate_region(region)
    with mss.mss() as screen:
        valid = any(region["x"] >= m["left"] and region["y"] >= m["top"] and
                    region["x"]+region["width"] <= m["left"]+m["width"] and
                    region["y"]+region["height"] <= m["top"]+m["height"] for m in screen.monitors[1:])
        if not valid:
            raise ValueError("选区已不在同一个显示器内，请重新框选。")
        shot = screen.grab({"left": region["x"], "top": region["y"],
                            "width": region["width"], "height": region["height"]})
        return Image.frombytes("RGB", shot.size, shot.rgb)


def annotate_controls(image, report):
    marked = image.convert("RGB").copy()
    draw = ImageDraw.Draw(marked)
    face = font(16)
    boolean_index = 0
    for control in report["controls"]:
        x, y, w, h = control["bbox"]
        cx, cy = control["center"]
        draw.rectangle((x, y, x+w-1, y+h-1), outline="#00a050", width=2)
        draw.line((cx-12, cy, cx+12, cy), fill="red", width=2)
        draw.line((cx, cy-12, cx, cy+12), fill="red", width=2)
        label = {"true": "√", "false": "×"}.get(control["label"], control["label"]) or "未知"
        if control["id"] in ("next", "submit"):
            label += {True: "[可用]", False: "[禁用]", None: "[状态未知]"}.get(control.get("enabled"))
        if control["kind"].endswith("option"):
            label += {True: "[已选择]", False: "[未选择]", None: "[选择未知]"}.get(control.get("selected"))
        text = f"{label} 图内({cx},{cy})"
        tx, ty = x, y-24
        if control["kind"] == "boolean_option":
            ty = y+h+6+boolean_index*25
            boolean_index += 1
        bounds = draw.textbbox((0, 0), text, font=face)
        tw, th = bounds[2]-bounds[0]+8, bounds[3]-bounds[1]+8
        tx, ty = max(0, min(tx, image.width-tw)), max(0, min(ty, image.height-th))
        draw.rectangle((tx, ty, tx+tw, ty+th), fill="white")
        draw.text((tx+4-bounds[0], ty+4-bounds[1]), text, font=face, fill="#cc0000")
    return marked


@dataclass
class ScreenResult:
    original: Image.Image
    marked: Image.Image
    report: dict


def analyze_capture(image, region, reader):
    region = validate_region(region)
    if image.size != (region["width"], region["height"]):
        raise ValueError("截图像素尺寸与选区不一致，未换算全局坐标。")
    report = reader.read(image)
    report["screen_region"] = region
    report["coordinate_system"] = {"center": "image_pixels", "bbox": "image_pixels_xywh",
                                   "screen_center": "physical_screen_pixels", "screen_bbox": "physical_screen_pixels_xywh"}
    for control in report["controls"]:
        cx, cy = control["center"]
        x, y, w, h = control["bbox"]
        if not (0 <= x < x+w <= image.width and 0 <= y < y+h <= image.height and
                x <= cx < x+w and y <= cy < y+h):
            raise ValueError("检测到越界控件，未输出全局坐标。")
        control["screen_center"] = [region["x"]+cx, region["y"]+cy]
        control["screen_bbox"] = [region["x"]+x, region["y"]+y, w, h]
    return ScreenResult(image.copy(), annotate_controls(image, report), report)


def save_result(result, root):
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    folder = Path(root)/f"screen_test_{stamp}_{uuid.uuid4().hex[:6]}"
    folder.mkdir(parents=True, exist_ok=False)
    result.original.save(folder/"original.png")
    result.marked.save(folder/"marked.png")
    (folder/"result.json").write_text(json.dumps(result.report, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder.resolve()
