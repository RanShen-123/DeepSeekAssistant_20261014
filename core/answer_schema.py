"""AI 输出仅解析为答案数据，不接受坐标、命令或执行步骤。"""
import json


def validate_answer(value, question_type, labels):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise ValueError("AI 未返回有效 JSON，已暂停，未点击。") from None
    if not isinstance(value, dict) or set(value) != {"question_type", "answer", "explanation", "uncertain"}:
        raise ValueError("AI 答案字段不符合约定，已暂停。")
    if value["question_type"] != question_type or question_type not in ("single", "boolean"):
        raise ValueError("AI 题型与本地识别不一致，已暂停。")
    if type(value["uncertain"]) is not bool or value["uncertain"]:
        raise ValueError("AI 答案不确定，已暂停。")
    answers = value["answer"]
    allowed = {"A", "B", "C", "D"} if question_type == "single" else {"true", "false"}
    if (not isinstance(answers, list) or len(answers) != 1 or not isinstance(answers[0], str)
            or answers[0] not in allowed or answers[0] not in labels):
        raise ValueError("AI 答案不能唯一匹配本地选项，已暂停。")
    if not isinstance(value["explanation"], str) or len(value["explanation"]) > 6000:
        raise ValueError("AI 解析字段无效，已暂停。")
    return value.copy()
