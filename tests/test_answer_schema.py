"""AI 答案数据校验；无网络调用。"""
import unittest
from core.answer_schema import validate_answer


class AnswerSchemaTests(unittest.TestCase):
    def answer(self, **changes):
        value = {"question_type": "single", "answer": ["B"], "explanation": "解析", "uncertain": False}
        value.update(changes)
        return value

    def test_single_and_boolean(self):
        self.assertEqual(validate_answer(self.answer(), "single", list("ABCD"))["answer"], ["B"])
        value = self.answer(question_type="boolean", answer=["false"])
        self.assertEqual(validate_answer(value, "boolean", ["true", "false"])["answer"], ["false"])

    def test_rejects_ambiguous_or_instruction_fields(self):
        values = [self.answer(answer=["A", "B"]), self.answer(uncertain=True),
                  self.answer(answer=["E"]), self.answer(click=[100, 200]),
                  self.answer(uncertain="false"), self.answer(question_type="boolean"),
                  "答案 B，然后点击提交", self.answer(answer=[True])]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_answer(value, "single", list("ABCD"))
