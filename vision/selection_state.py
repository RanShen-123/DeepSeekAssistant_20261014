"""当前页面圆形选项的蓝底选中状态，不把状态当成答案正确性。"""
import cv2
import numpy as np


def option_selected(bgr, box):
    x, y, w, h = box
    crop = bgr[y:y+h, x:x+w]
    if crop.size == 0 or crop.shape[:2] != (h, w):
        return None, "选项区域为空或越界"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    interior = np.zeros((h, w), np.uint8)
    cv2.circle(interior, (w//2, h//2), max(1, int(min(w, h)*.39)), 255, -1)
    pixels = interior > 0
    blue = cv2.inRange(hsv, (95, 100, 100), (135, 255, 255))
    white = cv2.inRange(hsv, (0, 0, 235), (179, 45, 255))
    blue_ratio = float(np.mean(blue[pixels] > 0))
    white_ratio = float(np.mean(white[pixels] > 0))
    evidence = f"选项内圆蓝色占比={blue_ratio:.3f}，白色占比={white_ratio:.3f}"
    if blue_ratio >= .55:
        return True, evidence+"；蓝底已选择"
    gray_strokes = cv2.inRange(hsv, (0, 0, 85), (179, 65, 225))
    if blue_ratio <= .04 and white_ratio >= .65 and np.count_nonzero(gray_strokes) >= 6:
        return False, evidence+"；白底灰色笔画或边框，未选择"
    return None, evidence+"；样式不确定"


def selected_letter_image(bgr, box):
    """蓝底白字转换为白底黑字，仅替换选项区域，供局部 OCR 使用。"""
    x, y, w, h = box
    hsv = cv2.cvtColor(bgr[y:y+h, x:x+w], cv2.COLOR_BGR2HSV)
    glyph = cv2.inRange(hsv, (0, 0, 215), (179, 80, 255))
    result = bgr.copy()
    result[y:y+h, x:x+w] = cv2.cvtColor(255-glyph, cv2.COLOR_GRAY2BGR)
    return result
