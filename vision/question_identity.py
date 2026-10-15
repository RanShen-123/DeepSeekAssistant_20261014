"""使用题型、完整题干和选项文字确认同一道题，排除题号/分值/装饰条。"""
import hashlib
import json
import re
import unicodedata


def normalized(text):
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", text))


def build_identity(lines, choices, kind, header_bottom):
    if not choices or kind not in ("single", "boolean", "multiple") or header_bottom is None:
        return None, None
    bottom = min(c.bbox[1] for c in choices)
    stem_lines = [normalized(line.text) for line in sorted(lines, key=lambda item: (item.bbox[1], item.bbox[0]))
                  if line.bbox[1] >= header_bottom and line.bbox[1]+line.bbox[3] < bottom]
    stem = "".join(stem_lines)
    if not stem:
        return None, None
    option_texts = []
    for control in choices:
        x, y, w, h = control.bbox
        fragments = []
        for line in sorted(lines, key=lambda item: (item.bbox[1], item.bbox[0])):
            lx, ly, lw, lh = line.bbox
            # 任一选项内部的字母/符号都不是相邻选项的附加文字。
            inside_option = any(
                box.bbox[0] <= line.center[0] < box.bbox[0]+box.bbox[2]
                and box.bbox[1] <= line.center[1] < box.bbox[1]+box.bbox[3]
                and lw <= box.bbox[2]*1.3
                for box in choices)
            if inside_option:
                continue
            # 判断题两个符号可能被 OCR 合并成一行，也可能把 ×/√ 读成 X/V。
            if kind == "boolean" and re.fullmatch(r"[√✓✔×✕✖XxVv]+", normalized(line.text)):
                continue
            if abs(line.center[1]-control.center[1]) <= h*.6 and lx+lw > x+w+w*.15:
                text = normalized(line.text)
                # OCR 可能将字母与右侧文字合并成一行，移除已确认的圆内标签。
                if lx < x+w and control.label and text.startswith(control.label):
                    text = text[len(control.label):]
                if text:
                    fragments.append(text)
        option_texts.append({"label": control.label, "text": "".join(fragments)})
    identity = {"question_type": kind, "stem": stem, "options": option_texts}
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return identity, hashlib.sha256(serialized.encode("utf-8")).hexdigest()
