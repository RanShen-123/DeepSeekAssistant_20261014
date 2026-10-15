"""纯模拟浏览器与 AI；不截图、不调用 API、不点击真实桌面。"""
import unittest
from types import SimpleNamespace
from core.auto_flow import AutoFlow, AutoStopped


class FakePage:
    def __init__(self, total=2, auto_advance=False, accept_submit=True):
        self.total, self.index = total, 1
        self.selected, self.submitted = False, False
        self.auto_advance, self.accept_submit = auto_advance, accept_submit
        self.clicks, self.requests = [], 0
        self.stopped = False

    def observe(self):
        controls = [{"id": "option_"+label, "kind": "choice_option", "label": label,
                     "selected": self.selected and label == "B", "confidence": .99,
                     "center": [100, 100+i*60], "screen_center": [100, 100+i*60],
                     "bbox": [80, 80+i*60, 40, 40]}
                    for i, label in enumerate("ABCD")]
        for name, label, x, enabled in (
            ("submit", "已提交" if self.submitted else "提交", 400, self.selected and not self.submitted),
            ("next", "下一题", 700, self.index < self.total),
        ):
            controls.append({"id": name, "kind": "button", "label": label,
                             "enabled": enabled, "confidence": .99, "center": [x, 550],
                             "screen_center": [x, 550], "bbox": [x-30, 530, 60, 40]})
        return SimpleNamespace(original=None, report={
            "question_type": "single", "question_signature": str(self.index), "controls": controls,
            "screen_region": {"x": 0, "y": 0, "width": 800, "height": 600},
            "page_state": {"submitted": self.submitted,
                           "can_submit": self.selected and not self.submitted,
                           "next_enabled": self.index < self.total}})

    def ask(self, image, kind, labels):
        self.requests += 1
        return {"question_type": "single", "answer": ["B"], "explanation": "模拟答案", "uncertain": False}

    def click(self, x, y, cancelled):
        if cancelled():
            raise RuntimeError("已停止")
        self.clicks.append((x, y))
        if (x, y) == (100, 160):
            self.selected = True
        elif x == 400:
            if self.accept_submit:
                self.submitted = True
                if self.auto_advance and self.index < self.total:
                    self.advance()
        elif x == 700:
            self.advance()
        else:
            raise AssertionError("出现预期以外的模拟点击")

    def advance(self):
        self.index += 1
        self.selected, self.submitted = False, False

    def flow(self, attempts=None):
        return AutoFlow(self.observe, self.ask, self.click, lambda: self.stopped,
                        lambda: False, lambda value: None, lambda value: None, attempts)


class AutoFlowTests(unittest.TestCase):
    def test_gray_submit_before_answer_still_answers(self):
        page = FakePage(total=1)
        self.assertFalse(page.observe().report["page_state"]["can_submit"])
        page.flow().run()
        self.assertEqual(page.requests, 1)
        self.assertEqual(page.clicks, [(100, 160), (400, 550)])

    def test_selected_answer_waits_for_submit_to_enable(self):
        class DelayedPage(FakePage):
            reads = 0

            def observe(self):
                result = super().observe()
                if self.selected and not self.submitted:
                    self.reads += 1
                    if self.reads <= 3:
                        result.report["page_state"]["can_submit"] = False
                        next(c for c in result.report["controls"] if c["id"] == "submit")["enabled"] = False
                return result

        page = DelayedPage(total=1)
        page.flow().run()
        self.assertEqual(page.clicks, [(100, 160), (400, 550)])
        self.assertGreater(page.reads, 3)

    def test_submit_stays_gray_pauses_without_finishing(self):
        class GrayPage(FakePage):
            def observe(self):
                result = super().observe()
                result.report["page_state"]["can_submit"] = False
                return result

        page = GrayPage(total=1)
        with self.assertRaisesRegex(ValueError, "不判定为完成"):
            page.flow().run()
        self.assertEqual(page.requests, 1)
        self.assertEqual(page.clicks, [(100, 160)])

    def test_answer_changes_before_submit_blocks_submission(self):
        page = FakePage(total=1)
        page.selected = True
        fresh = page.observe()
        choices = [c for c in fresh.report["controls"] if c["kind"].endswith("option")]
        for control in choices:
            control["selected"] = control["label"] == "D"
        with self.assertRaisesRegex(ValueError, "DeepSeek 答案不一致"):
            page.flow().wait_to_submit(fresh, "1", "B")
        self.assertEqual(page.clicks, [])

    def test_boolean_answer_uses_actual_false_label(self):
        class BooleanPage(FakePage):
            def observe(self):
                result = super().observe()
                result.report["question_type"] = "boolean"
                controls = []
                for control in result.report["controls"]:
                    if control["kind"] == "choice_option":
                        if control["label"] not in ("A", "B"):
                            continue
                        control["kind"] = "boolean_option"
                        control["label"] = {"A": "true", "B": "false"}[control["label"]]
                    controls.append(control)
                result.report["controls"] = controls
                return result

            def ask(self, image, kind, labels):
                self.requests += 1
                return {"question_type": "boolean", "answer": ["false"], "explanation": "模拟", "uncertain": False}

        page = BooleanPage(total=1)
        page.flow().run()
        self.assertEqual(page.clicks, [(100, 160), (400, 550)])

    def test_fifty_questions_end_only_at_disabled_next(self):
        page = FakePage(total=50)
        flow = page.flow()
        flow.run()
        self.assertEqual(len(flow.completed), 50)
        self.assertEqual(page.requests, 50)
        self.assertEqual(sum(x == 400 for x, _ in page.clicks), 50)
        self.assertEqual(sum(x == 700 for x, _ in page.clicks), 49)

    def test_skip_previously_submitted(self):
        page = FakePage()
        page.selected, page.submitted = True, True
        flow = page.flow()
        flow.run()
        self.assertEqual(len(flow.skipped), 1)
        self.assertEqual(page.requests, 1)

    def test_auto_advance_never_clicks_extra_next(self):
        page = FakePage(auto_advance=True)
        page.flow().run()
        self.assertEqual(page.requests, 2)
        self.assertEqual(sum(x == 700 for x, _ in page.clicks), 0)

    def test_submit_unconfirmed_does_not_retry_even_after_restart(self):
        page = FakePage(accept_submit=False)
        attempts = set()
        with self.assertRaises(ValueError):
            page.flow(attempts).run()
        with self.assertRaises(ValueError):
            page.flow(attempts).run()
        self.assertEqual(sum(x == 400 for x, _ in page.clicks), 1)

    def test_stop_during_ai_prevents_clicks(self):
        page = FakePage()
        ask = page.ask

        def stopping_ask(*args):
            value = ask(*args)
            page.stopped = True
            return value

        flow = page.flow()
        flow.ask = stopping_ask
        with self.assertRaises(AutoStopped):
            flow.run()
        self.assertEqual(page.clicks, [])

    def test_unknown_submit_pauses_without_api(self):
        page = FakePage()
        page.submitted = None
        with self.assertRaises(ValueError):
            page.flow().run()
        self.assertEqual(page.requests, 0)
        self.assertEqual(page.clicks, [])
