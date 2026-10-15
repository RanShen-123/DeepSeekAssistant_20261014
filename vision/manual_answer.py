"""手动答案适配与一次选择流程；鼠标/截图通过参数注入，方便离线模拟。"""
import unicodedata


def normalize_answer(value):
    value = unicodedata.normalize("NFKC", value).strip().upper()
    mapping = {"√": "true", "✓": "true", "✔": "true", "正确": "true", "对": "true", "TRUE": "true",
               "×": "false", "✕": "false", "✖": "false", "❌": "false", "错误": "false", "错": "false", "FALSE": "false"}
    if value in ("A", "B", "C", "D"):
        return value
    if value in mapping:
        return mapping[value]
    raise ValueError("请输入一个 A/B/C/D，或 √/×、正确/错误；不支持多个答案。")


def matching_option(report, answer):
    expected = "boolean" if answer in ("true", "false") else "single"
    if report.get("question_type") != expected:
        raise ValueError("答案与题型不匹配或题型未知，仅支持单选和判断题。")
    if report.get("page_state", {}).get("submitted") is not False:
        raise ValueError("当前题已提交或提交状态未知，未点击。")
    choices = [c for c in report["controls"] if c["kind"].endswith("option")]
    if any(c.get("label") is None or c.get("selected") is None for c in choices):
        raise ValueError("部分选项含义或选择状态未知，未点击。")
    labels = [c["label"] for c in choices]
    if len(set(labels)) != len(labels) or sum(c["selected"] is True for c in choices) > 1:
        raise ValueError("选项标签重复或选中状态冲突，未点击。")
    matches = [c for c in choices if c["label"] == answer]
    if len(matches) != 1 or matches[0]["confidence"] < .65:
        raise ValueError("找不到唯一、可信的答案选项，未点击。")
    return matches[0]


def choose_once(baseline, answer, observe, click, cancelled, settle):
    """baseline 仅用来确认题目没变，点击坐标始终来自本次重新截图。"""
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    fresh = observe()
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    signature = baseline.get("question_signature")
    if not signature or signature != fresh.report.get("question_signature"):
        raise ValueError("题型、题干或选项与前次识别不一致，或题干无法确认，已暂停。")
    target = matching_option(fresh.report, answer)
    if target["selected"] is True:
        fresh.report["manual_click"] = {"answer": answer, "clicked": False, "verified": True,
                                        "message": "目标已选中，没有重复点击。"}
        return fresh
    region = fresh.report["screen_region"]
    cx, cy = target["screen_center"]
    ix, iy = target["center"]
    if ([cx, cy] != [region["x"]+ix, region["y"]+iy] or
            not (0 <= ix < region["width"] and 0 <= iy < region["height"])):
        raise ValueError("点击坐标无效，未点击。")
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    click(cx, cy, cancelled)
    if settle() or cancelled():
        raise RuntimeError("已停止；若已发送单击，请手动核对页面，不会重试。")
    after = observe()
    if cancelled():
        raise RuntimeError("已停止；不会继续操作。")
    options = [c for c in after.report["controls"] if c["kind"].endswith("option")]
    same_question = after.report.get("question_signature") == signature
    selection_confirmed = (len([c for c in options if c.get("label") == answer and c.get("selected") is True]) == 1
                and sum(c.get("selected") is True for c in options) == 1
                and all(c.get("selected") is not None for c in options))
    verified = same_question and selection_confirmed
    message = ("已点击且确认选中；未提交。" if verified else
               "点击后题型、题干或选项核对不一致，已暂停；不会重试。" if not same_question else
               "已点击但未确认对应选项选中，请人工核对；不会重试。")
    after.report["manual_click"] = {"answer": answer, "clicked": True, "verified": verified,
                                    "same_question": same_question, "selection_confirmed": selection_confirmed,
                                    "screen_center": [cx, cy],
                                    "message": message}
    return after
