"""组合 OCR 与视觉观察；不执行题目、页面文字或任何鼠标指令。"""
import re
import cv2
import numpy as np
from vision.models import PageResult
from vision.ocr_engine import LocalOCR
from vision.controls import navigation, options, buttons, header_without_accent


class PageReader:
    def __init__(self, ocr=None):
        self.ocr = ocr if ocr is not None else LocalOCR()

    def read(self, image):
        bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        height, width = bgr.shape[:2]
        lines = self.ocr.read(bgr)
        result = PageResult([width, height], texts=lines)
        header = None
        for line in sorted(lines, key=lambda t: t.bbox[1]):
            compact = re.sub(r"\s", "", line.text)
            match = re.search(r"(\d{1,3})[.．、]?(单选题|多选题|判断题)", compact)
            if match and line.center[1] < height*.25:
                used_text, used_score, source = line.text, line.score, "full_image_ocr"
                for cropped, confidence in header_without_accent(bgr, line, self.ocr):
                    corrected = re.search(r"(\d{1,3})[.．、]?(单选题|多选题|判断题)", re.sub(r"\s", "", cropped))
                    if corrected and confidence >= max(.65, line.score-.15):
                        match = corrected
                        used_text, used_score, source = cropped, confidence, "accent_excluded_crop"
                        break
                header = line
                result.header_question_number = int(match.group(1))
                result.header_evidence = {"raw_text": line.text, "used_text": used_text,
                                          "confidence": used_score, "source": source, "bbox": line.bbox}
                result.question_type = {"单选题": "single", "多选题": "multiple", "判断题": "boolean"}[match.group(2)]
                break
        nav = navigation(bgr, lines, self.ocr)
        result.controls.extend(nav)
        sidebar_right = max((c.bbox[0]+c.bbox[2] for c in nav), default=int(width*.15))
        current = [c.question_number for c in nav if c.state == "current"]
        if len(current) == 1:
            result.sidebar_question_number = current[0]
        elif len(current) > 1:
            result.warnings.append("检测到多个深蓝当前题框，当前题号不能确定。")
        if result.header_question_number is not None and result.sidebar_question_number is not None:
            result.question_number_consistent = result.header_question_number == result.sidebar_question_number
            if result.question_number_consistent:
                result.current_question_number = result.header_question_number
            else:
                result.warnings.append("顶部题号与侧栏深蓝框题号冲突，未选定当前题号。")
        elif len(current) <= 1:
            result.current_question_number = result.header_question_number or result.sidebar_question_number
        counters = []
        for line in lines:
            if line.center[0] > sidebar_right+width*.02:
                continue
            match = re.search(r"(?<!\d)(\d+)\s*[/／]\s*(\d+)(?!\d)", line.text)
            if match:
                completed, total = map(int, match.groups())
                if 0 <= completed <= total and total > 0:
                    counters.append((completed, total, line.text))
        if len({c[:2] for c in counters}) == 1:
            result.completed_count, result.total_count, result.progress_evidence = counters[0]
            result.warnings.append("完成数量依据该页面的侧栏计数约定，不能泛用于‘当前题号/总题数’界面。")
        elif counters:
            result.warnings.append("侧栏存在互相矛盾的计数，未确定完成进度。")
        else:
            result.warnings.append("截图未包含可识别的完成计数；没有用当前题号代替进度。")
        if (result.total_count is not None and result.current_question_number is not None
                and not 1 <= result.current_question_number <= result.total_count):
            result.warnings.append("当前题号超出已读到的总题数，未确认当前题号。")
            result.current_question_number = None
        choices = options(bgr, lines, self.ocr, result.question_type, sidebar_right)
        result.controls.extend(choices)
        result.controls.extend(buttons(bgr, lines))
        if header and choices:
            first_y = min(c.bbox[1] for c in choices)
            questions = [line for line in lines if line.center[0] > sidebar_right and
                         line.bbox[1] > header.bbox[1]+header.bbox[3] and
                         line.bbox[1]+line.bbox[3] <= first_y]
            result.question_text = "\n".join(t.text for t in sorted(questions, key=lambda t: (t.bbox[1], t.bbox[0]))) or None
        if result.question_type is None:
            result.warnings.append("未识别到顶部题型。")
        if not choices:
            result.warnings.append("未找到可确认的一组选项圆圈；目前不支持方形多选框。")
        if any(c.label is None for c in choices):
            result.warnings.append("部分选项字母或符号未识别，未按上下/左右顺序补猜。")
        result.warnings.append("按钮启用状态与选项选中状态暂保留未知，需要更多实际样例验证。")
        return result
