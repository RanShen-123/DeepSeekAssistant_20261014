"""交互实验专用：只识别题型、选项与上下题/提交，不处理导航题号或进度。"""
import re
import cv2
import numpy as np
from vision.controls import options, buttons
from vision.ocr_engine import LocalOCR
from vision.button_state import detect_page_state
from vision.question_identity import build_identity


def content_bbox(bgr):
    """若存在侧栏的长竖分隔线，先裁出主内容再 OCR；否则保留完整选区。"""
    height, width = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    mask = cv2.inRange(gray, 0, 248)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, int(height*.5))))
    vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    coverage = np.count_nonzero(vertical, axis=0)
    candidates = [x for x in range(int(width*.08), int(width*.4)) if coverage[x] > height*.55]
    left = min(width-1, max(candidates)+2) if candidates else 0
    return [left, 0, width-left, height]


class ControlReader:
    def __init__(self, ocr=None):
        self.ocr = ocr if ocr is not None else LocalOCR()

    def read(self, image):
        rgb = image.convert("RGB")
        bgr = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
        crop_box = content_bbox(bgr)
        ox, oy, w, h = crop_box
        content = bgr[oy:oy+h, ox:ox+w]
        lines = self.ocr.read(content)
        blocker = next(("页面要求手动完成安全核验" for line in lines
                        if re.search(r"请完成安全核验|请先完成验证|请完成安全验证|拖动滑块完成", re.sub(r"\s", "", line.text))), None)
        kind, type_box, type_score = None, None, None
        kinds = {"单选题": "single", "判断题": "boolean", "多选题": "multiple"}
        for line in sorted(lines, key=lambda item: item.bbox[1]):
            match = re.search(r"单选题|判断题|多选题", re.sub(r"\s", "", line.text))
            if match and line.center[1] < h*.3:
                kind, type_score = kinds[match.group(0)], line.score
                type_box = [line.bbox[0]+ox, line.bbox[1]+oy, *line.bbox[2:]]
                break
        choices = options(content, lines, self.ocr, kind, -1)
        header_bottom = type_box[1]-oy+type_box[3] if type_box else None
        question_identity, question_signature = build_identity(lines, choices, kind, header_bottom)
        found = choices + buttons(content, lines, minimum_x_ratio=0, include_submitted=True)
        page_state = detect_page_state(content, lines, found)
        controls = []
        warnings = []
        for control in found:
            label = control.label
            if control.kind == "choice_option" and label not in ("A", "B", "C", "D"):
                label = None
            controls.append({"id": control.id, "kind": control.kind, "label": label,
                             "bbox": [control.bbox[0]+ox, control.bbox[1]+oy, *control.bbox[2:]],
                             "center": [control.center[0]+ox, control.center[1]+oy],
                             "confidence": control.confidence, "evidence": control.evidence,
                             "selected": control.selected, "enabled": control.enabled})
        if kind is None:
            warnings.append("题型未识别，请把顶部题型框入选区。")
        if kind == "multiple":
            warnings.append("识别到了多选题标题，但本次实验不支持方形多选框。")
        if not choices:
            warnings.append("未识别到一组选项圆圈，请框入全部 A/B/C/D 或 √/×。")
        if any(c["label"] is None for c in controls if c["kind"].endswith("option")):
            warnings.append("部分选项标识未知，没有按上下或左右顺序补猜。")
        for name, label in (("previous", "上一题"), ("next", "下一题"), ("submit", "提交")):
            if not any(c["id"] == name for c in controls):
                warnings.append(f"未识别到{label}按钮，请确认完整框入。")
        labels = [c["label"] for c in controls if c["kind"].endswith("option") and c["label"]]
        if len(set(labels)) != len(labels):
            warnings.append("选项标识有重复，请人工核对，不能直接用于鼠标操作。")
        if kind in ("single", "boolean") and sum(c.selected is True for c in choices) > 1:
            warnings.append("单选或判断题识别出多个蓝色选项，请人工核对。")
        if any(c.selected is None for c in choices):
            warnings.append("部分选项是否已选择无法确认，请对照原图。")
        if page_state["suggested_action"] == "pause":
            warnings.append(page_state["message"])
        warnings.append("仅按当前页面样式检测已提交、是否可提交和下一题状态；不执行任何点击。")
        return {"schema_version": 6, "scope": "type_and_answer_controls_only",
                "image_size": list(rgb.size), "question_type": kind, "question_type_bbox": type_box,
                "question_type_confidence": type_score, "content_bbox": crop_box,
                "controls": controls, "page_state": page_state, "question_signature": question_signature,
                "question_identity": question_identity,
                "page_blocker": blocker,
                "warnings": warnings}
