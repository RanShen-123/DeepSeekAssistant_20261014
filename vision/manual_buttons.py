"""提交、下一题的独立单击流程，不串联执行、不重复发送。"""


def matching_button(report, action):
    if action not in ("submit", "next"):
        raise ValueError("不支持的按钮操作。")
    state = report.get("page_state", {})
    if action == "submit":
        if state.get("submitted") is not False or state.get("can_submit") is not True:
            raise ValueError("必须明确为未提交且蓝色提交按钮可用，才允许提交。")
    else:
        if state.get("submitted") is not True:
            raise ValueError("当前题尚未确认已提交，不允许点击下一题。")
        if state.get("next_enabled") is not True:
            raise ValueError("下一题禁用或状态未知，不点击；已提交且下一题灰色表示全部完成。")
    matches = [c for c in report["controls"] if c["id"] == action and c["kind"] == "button"]
    if len(matches) != 1 or matches[0]["confidence"] < .65 or matches[0].get("enabled") is not True:
        raise ValueError("按钮定位不唯一、匹配分数不足或可用状态未确认。")
    expected = ("提交", "提交答案") if action == "submit" else ("下一题",)
    if matches[0].get("label") not in expected:
        raise ValueError("按钮文字不符合本次操作。")
    return matches[0]


def button_once(baseline, action, observe, click, cancelled, settle):
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    fresh = observe()
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    signature = baseline.get("question_signature")
    if not signature or fresh.report.get("question_signature") != signature:
        raise ValueError("题目与预览不一致，请重新识别后操作。")
    target = matching_button(fresh.report, action)
    region = fresh.report["screen_region"]
    cx, cy = target["screen_center"]
    ix, iy = target["center"]
    x, y, w, h = target["bbox"]
    if (any(type(v) is not int for v in (cx, cy, ix, iy, x, y, w, h)) or
            [cx, cy] != [region["x"]+ix, region["y"]+iy] or
            not (0 <= x <= ix < x+w <= region["width"] and
                 0 <= y <= iy < y+h <= region["height"])):
        raise ValueError("按钮坐标无效，未点击。")
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    click(cx, cy, cancelled)
    after = fresh
    verified, changed = False, False
    # 只重读状态，不重试点击，给异步页面有限的更新时间。
    for _ in range(3):
        if settle() or cancelled():
            raise RuntimeError("已停止；若已发送单击，请手动核对，不会重试。")
        after = observe()
        if cancelled():
            raise RuntimeError("已停止；不会继续操作。")
        current = after.report.get("question_signature")
        changed = bool(current and current != signature)
        if action == "submit":
            verified = (current == signature and after.report.get("page_state", {}).get("submitted") is True)
            if verified or changed:
                break
        elif changed:
            verified = True
            break
    if action == "submit":
        message = ("提交成功：已识别到已提交，未点击下一题。" if verified else
                   "提交后页面已切换，未单独确认提交成功，未再点击下一题。" if changed else
                   "已点击提交，但未确认成功；已阻止本题再次提交，请人工核对。")
    else:
        message = "已点击下一题并检测到题目切换。" if verified else "已点击下一题，但未确认题目切换；不会重试。"
    after.report["manual_action"] = {"action": action, "clicked": True, "verified": verified,
                                      "question_changed": changed, "screen_center": [cx, cy], "message": message}
    return after
