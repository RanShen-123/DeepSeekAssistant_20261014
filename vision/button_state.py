"""针对当前白底页面：OCR 确认含义，文字前景亮度确认下一题状态。"""
import re
import cv2
import numpy as np


def text_enabled(bgr, bbox, *, allow_blue=False):
    x, y, w, h = bbox
    crop = bgr[max(0, y):min(bgr.shape[0], y+h), max(0, x):min(bgr.shape[1], x+w)]
    if crop.size == 0:
        return None, {"reason": "文字区域为空"}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    foreground = gray[gray < 225]
    if foreground.size < 12:
        return None, {"reason": "可用文字像素不足"}
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturation = float(np.median(hsv[:, :, 1][gray < 225]))
    level = float(np.percentile(foreground, 20))
    background = float(np.percentile(gray, 90))
    evidence = {"foreground_gray_p20": round(level, 1), "background_gray_p90": round(background, 1),
                "median_saturation": round(saturation, 1), "foreground_pixels": int(foreground.size)}
    if allow_blue:
        blue = cv2.inRange(hsv, (95, 100, 90), (135, 255, 255))
        blue_ratio = float(np.mean(blue[gray < 225] > 0))
        foreground_fraction = float(foreground.size/gray.size)
        evidence.update(blue_foreground_ratio=round(blue_ratio, 3),
                        foreground_fraction=round(foreground_fraction, 3))
        # 仅下一题允许白底蓝色文字（鼠标悬停/聚焦），不把蓝色背景当作文字。
        if background >= 235 and blue_ratio >= .65 and foreground_fraction < .65:
            return True, dict(evidence, reason="下一题文字为蓝色悬停或聚焦状态")
    # 灰区保留未知；不要把漏检、异常主题或淡色背景直接视作禁用。
    if background < 235 or saturation > 80:
        return None, dict(evidence, reason="不符合已约定的白底灰色文字样式")
    if level <= 130:
        return True, dict(evidence, reason="下一题文字为深色")
    if 165 <= level <= 215 and background-level >= 20:
        return False, dict(evidence, reason="下一题文字为浅灰色")
    return None, dict(evidence, reason="文字亮度处于不确定范围")


def submit_enabled(bgr, control, line):
    """只在 OCR 已确认的提交区域判断，避免把蓝色选项当成提交按钮。"""
    x, y, w, h = control.bbox
    crop = bgr[max(0, y):min(bgr.shape[0], y+h), max(0, x):min(bgr.shape[1], x+w)]
    if crop.size == 0:
        return None, {"reason": "提交区域为空"}
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (95, 100, 100), (135, 255, 255))
    white = cv2.inRange(hsv, (0, 0, 225), (179, 60, 255))
    blue_ratio = float(np.count_nonzero(blue)/blue.size)
    white_ratio = float(np.count_nonzero(white)/white.size)
    evidence = {"control": "submit", "blue_ratio": round(blue_ratio, 3),
                "white_ratio": round(white_ratio, 3)}
    if blue_ratio >= .5 and white_ratio >= .005:
        return True, dict(evidence, reason="提交按钮蓝色背景及白色文字")
    text_state, text_evidence = text_enabled(bgr, line.bbox)
    if blue_ratio <= .05 and text_state is False:
        return False, dict(evidence, reason="提交按钮非蓝底且文字浅灰", text_evidence=text_evidence)
    return None, dict(evidence, reason="提交按钮外观无法确认", text_evidence=text_evidence)


def detect_page_state(bgr, lines, controls):
    submitted, next_enabled, can_submit = None, None, None
    evidence = []
    submits = [c for c in controls if c.id == "submit"]
    nexts = [c for c in controls if c.id == "next"]
    if len(submits) == 1 and submits[0].confidence >= .65:
        submitted = submits[0].label == "已提交"
        if submitted:
            submits[0].enabled = False
            can_submit = False
        else:
            matches = [line for line in lines
                       if re.sub(r"\s", "", line.text) == submits[0].label
                       and line.score >= .65
                       and submits[0].bbox[0] <= line.center[0] < submits[0].bbox[0]+submits[0].bbox[2]
                       and submits[0].bbox[1] <= line.center[1] < submits[0].bbox[1]+submits[0].bbox[3]]
            if len(matches) == 1:
                can_submit, pixels = submit_enabled(bgr, submits[0], matches[0])
                submits[0].enabled = can_submit
                evidence.append(pixels)
        evidence.append("底部 OCR 文字："+submits[0].label)
    if len(nexts) == 1:
        matches = [line for line in lines if re.sub(r"\s", "", line.text) == "下一题"
                   and line.score >= .65
                   and nexts[0].bbox[0] <= line.center[0] < nexts[0].bbox[0]+nexts[0].bbox[2]
                   and nexts[0].bbox[1] <= line.center[1] < nexts[0].bbox[1]+nexts[0].bbox[3]]
        if len(matches) == 1:
            next_enabled, pixels = text_enabled(bgr, matches[0].bbox, allow_blue=True)
            nexts[0].enabled = next_enabled
            evidence.append(pixels)
    if submitted is True and next_enabled is False:
        completed, action, message = True, "stop", "全部作答完成（已提交且下一题灰色禁用）"
    elif submitted is True and next_enabled is True:
        completed, action, message = False, "next", "当前题已完成，建议下一题"
    elif submitted is False and can_submit is True:
        completed, action, message = False, "submit", "答案已可提交（蓝色提交按钮）"
    elif submitted is False and can_submit is False:
        completed, action, message = False, "answer", "当前不可提交（灰色提交按钮），需先完成选择"
    elif submitted is False:
        completed, action, message = False, "pause", "尚未提交，但按钮是否可提交未知，建议暂停核对"
    else:
        completed, action, message = None, "pause", "提交或下一题状态未知，建议暂停核对"
    return {"submitted": submitted, "can_submit": can_submit, "next_enabled": next_enabled, "all_completed": completed,
            "suggested_action": action, "message": message, "evidence": evidence,
            "completion_rule": "submitted_and_next_disabled"}
