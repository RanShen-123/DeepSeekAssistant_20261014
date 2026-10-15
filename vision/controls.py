"""轮廓、颜色与符号几何识别，控件含义不依赖固定的屏幕坐标。"""
import re
import cv2
import numpy as np
from vision.models import Control
from vision.selection_state import option_selected, selected_letter_image


def contained(point, bbox):
    x, y, w, h = bbox
    return x <= point[0] < x+w and y <= point[1] < y+h


def header_without_accent(bgr, line, ocr):
    """去除标题旁的蓝色竖条后重新识别，避免将装饰条当作数字 1。"""
    x, y, w, h = line.bbox
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (95, 130, 120), (135, 255, 255))
    contours, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bars = []
    height, width = bgr.shape[:2]
    for contour in contours:
        bx, by, bw, bh = cv2.boundingRect(contour)
        if (width*.15 < bx < x+w*.35 and 2.5 < bh/max(bw, 1) < 12
                and max(2, width*.002) <= bw < width*.02 and height*.015 < bh < height*.07
                and cv2.contourArea(contour) > bw*bh*.6
                and abs(by+bh/2-line.center[1]) < h):
            bars.append((bx, by, bw, bh))
    if not bars:
        return []
    bx, by, bw, bh = max(bars, key=lambda b: b[0])
    left = max(x, bx+bw+max(2, int(bw*.4)))
    if left >= x+w:
        return []
    return ocr.read_crop(bgr, [left, y, x+w-left, h])


def deduplicate(boxes):
    result = []
    for box in sorted(boxes, key=lambda b: b[2]*b[3], reverse=True):
        cx, cy = box[0]+box[2]/2, box[1]+box[3]/2
        if not any(abs(cx-(b[0]+b[2]/2)) < min(box[2], b[2])*.25 and
                   abs(cy-(b[1]+b[3]/2)) < min(box[3], b[3])*.25 for b in result):
            result.append(box)
    return result


def nav_boxes(bgr):
    height, width = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    contours, _ = cv2.findContours(cv2.inRange(gray, 0, 225), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if (x+w < width*.21 and width*.035 < w < width*.13 and .8 < w/max(h, 1) < 1.25
                and cv2.contourArea(contour)/max(w*h, 1) > .75):
            # 该页面题号框为近方形，底部绿色圆标可能与边框连成更高的轮廓。
            boxes.append([x, y, w, min(w, h) if h > w*1.05 else h])
    return sorted(deduplicate(boxes), key=lambda b: b[1])


def navigation(bgr, lines, ocr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    controls = []
    for box in nav_boxes(bgr):
        x, y, w, h = box
        inner = hsv[y+int(h*.15):y+int(h*.85), x+int(w*.15):x+int(w*.85)]
        blue = cv2.inRange(inner, (95, 130, 90), (135, 255, 255))
        current = cv2.countNonZero(blue)/max(blue.size, 1) > .65
        marker = hsv[y+int(h*.7):min(hsv.shape[0], y+int(h*1.4)), x:x+w]
        green = cv2.inRange(marker, (35, 90, 70), (90, 255, 255))
        completed = cv2.countNonZero(green) > max(12, w*h*.008)
        evidence = "深蓝实心背景" if current else ("绿色完成标记；不代表答案正确" if completed else "普通导航框")
        state = "current" if current else ("completed_marker" if completed else "unmarked")
        number, score = None, .0
        for line in lines:
            if contained(line.center, box) and re.fullmatch(r"\d{1,3}", line.text.strip()):
                number, score = int(line.text.strip()), line.score
                break
        if number is None:
            crop = [x+int(w*.2), y+int(h*.2), int(w*.6), int(h*.6)]
            for value, confidence in ocr.read_crop(bgr, crop, invert=current):
                if re.fullmatch(r"\d{1,3}", value):
                    number, score = int(value), confidence
                    break
        controls.append(Control(f"nav_{number if number is not None else y}", "question_navigation",
                                str(number) if number is not None else None, box,
                                [x+w//2, y+h//2], score, evidence, state=state, question_number=number))
    return controls


def option_circles(bgr, sidebar_right):
    height, width = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    contours, _ = cv2.findContours(cv2.inRange(gray, 0, 215), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    # 判分红/绿角标会和蓝色圆圈连成灰度轮廓。单独提取蓝色，保留原圆圈。
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, (95, 100, 100), (135, 255, 255))
    blue_contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        if not (x > sidebar_right and area > width*height*.0004 and
                min(width, height)*.024 <= w <= min(width, height)*.10 and .85 < w/max(h, 1) < 1.18):
            continue
        perimeter = cv2.arcLength(contour, True)
        _, radius = cv2.minEnclosingCircle(contour)
        if perimeter > 0 and 4*np.pi*area/perimeter**2 > .72 and area/(np.pi*radius**2) > .82:
            boxes.append([x, y, w, h])
    for contour in blue_contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        _, radius = cv2.minEnclosingCircle(contour)
        if (x > sidebar_right and min(width, height)*.024 <= w <= min(width, height)*.10
                and .85 < w/max(h, 1) < 1.18 and area > width*height*.0004
                and perimeter > 0 and 4*np.pi*cv2.contourArea(hull)/perimeter**2 > .85
                and area/max(np.pi*radius**2, 1) > .72):
            boxes.append([x, y, w, h])
    boxes = deduplicate(boxes)
    best = []
    for seed in boxes:
        sx, sy = seed[0]+seed[2]/2, seed[1]+seed[3]/2
        for axis in ("vertical", "horizontal"):
            group = [b for b in boxes if .7 < b[2]/seed[2] < 1.4 and
                     (abs(b[0]+b[2]/2-sx) < seed[2]*.4 if axis == "vertical"
                      else abs(b[1]+b[3]/2-sy) < seed[3]*.4)]
            if len(group) > len(best):
                best = group
    return sorted(best, key=lambda b: (b[1]//max(1, int(b[3]*.6)), b[0])) if len(best) >= 2 else []


def normalized_glyph(mask):
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    if w < 3 or h < 3:
        return None
    result = np.zeros((48, 48), np.uint8)
    result[4:44, 4:44] = cv2.resize(mask[y:y+h, x:x+w], (40, 40), interpolation=cv2.INTER_NEAREST)
    return result


def classify_boolean_symbol(bgr, box):
    """将圆圈内部的笔画与多种 √/× 几何模板比较，不使用左右顺序。"""
    x, y, w, h = box
    gray = cv2.cvtColor(bgr[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
    selected, _ = option_selected(bgr, box)
    if selected is True:
        hsv = cv2.cvtColor(bgr[y:y+h, x:x+w], cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 0, 215), (179, 80, 255))
    else:
        mask = cv2.inRange(gray, 0, 220)
    interior = np.zeros_like(mask)
    cv2.circle(interior, (w//2, h//2), int(min(w, h)*.34), 255, -1)
    glyph = normalized_glyph(cv2.bitwise_and(mask, interior))
    if glyph is None:
        return None, 0.0
    distance = cv2.distanceTransform(255-glyph, cv2.DIST_L2, 3)
    costs = {"true": float("inf"), "false": float("inf")}
    for kind in costs:
        for thickness in (2, 3, 4, 5):
            for joint in (.25, .35, .45):
                template = np.zeros((48, 48), np.uint8)
                if kind == "false":
                    cv2.line(template, (5, 5), (42, 42), 255, thickness)
                    cv2.line(template, (5, 42), (42, 5), 255, thickness)
                else:
                    cv2.polylines(template, [np.array([[4, 24], [int(44*joint), 42], [43, 5]])],
                                  False, 255, thickness)
                template = normalized_glyph(template)
                other_distance = cv2.distanceTransform(255-template, cv2.DIST_L2, 3)
                cost = (float(distance[template > 0].mean()) + float(other_distance[glyph > 0].mean()))/2
                costs[kind] = min(costs[kind], cost)
    ranking = sorted(costs, key=costs.get)
    best, second = ranking
    if costs[best] > 3.5 or costs[second]-costs[best] < .6:
        return None, 0.0
    return best, round(max(0, 1-costs[best]/6), 3)


def options(bgr, lines, ocr, kind, sidebar_right):
    result = []
    for index, box in enumerate(option_circles(bgr, sidebar_right), 1):
        x, y, w, h = box
        selected, selection_evidence = option_selected(bgr, box)
        label, score, evidence = None, 0.0, "内部符号未能确定，不能按排列猜测"
        if kind == "boolean":
            label, score = classify_boolean_symbol(bgr, box)
            if label:
                evidence = "圆圈内笔画与 √/× 几何模板匹配"
        else:
            for line in lines:
                value = line.text.strip().upper()
                if contained(line.center, box) and re.fullmatch("[A-Z]", value):
                    label, score, evidence = value, line.score, "圆圈内部 OCR 字母"
                    break
            if label is None:
                inner = [x+int(w*.2), y+int(h*.2), int(w*.6), int(h*.6)]
                source = selected_letter_image(bgr, box) if selected is True else bgr
                for value, confidence in ocr.read_crop(source, inner):
                    if re.fullmatch("[A-Z]", value.upper()):
                        label, score, evidence = value.upper(), confidence, "圆圈内部放大后 OCR 字母"
                        break
        result.append(Control(f"option_{index}", "boolean_option" if kind == "boolean" else "choice_option",
                              label, box, [x+w//2, y+h//2], score,
                              evidence+"；"+selection_evidence, selected=selected))
    return result


def buttons(bgr, lines, *, minimum_x_ratio=.2, include_submitted=False):
    height, width = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    rectangles = []
    for threshold in (235, 245, 250):
        contours, _ = cv2.findContours(cv2.inRange(gray, 0, threshold), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if (y > height*.6 and width*.04 < w < width*.4 and height*.018 < h < height*.15
                    and 1.7 < w/max(h, 1) < 10 and cv2.contourArea(contour)/max(w*h, 1) > .7):
                rectangles.append([x, y, w, h])
    names = {"上一题": "previous", "下一题": "next", "提交": "submit", "提交答案": "submit"}
    if include_submitted:
        names["已提交"] = "submit"
    result = []
    for line in lines:
        value = re.sub(r"\s", "", line.text)
        if value not in names or line.center[1] < height*.6 or line.center[0] < width*minimum_x_ratio:
            continue
        matches = [b for b in rectangles if contained(line.center, b) and b[2] >= line.bbox[2]]
        box = min(matches, key=lambda b: b[2]*b[3]) if matches else line.bbox.copy()
        x, y, w, h = box
        result.append(Control(names[value], "button", value, box, [x+w//2, y+h//2],
                              line.score, "OCR 按钮文字" + ("与外围矩形" if matches else "（无独立按钮边框）")))
    return result
