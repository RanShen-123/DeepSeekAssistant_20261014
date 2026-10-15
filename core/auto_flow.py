"""自动答题状态流程；全部外部操作均注入，便于无桌面的模拟验证。"""
from core.answer_schema import validate_answer
from vision.manual_answer import choose_once
from vision.manual_buttons import button_once


class AutoStopped(RuntimeError):
    pass


class AutoFlow:
    def __init__(self, observe, ask, click, cancelled, settle, notify, answer_ready, submit_attempts=None,
                 retry_signature=None, confirmed_submissions=None):
        self.observe, self.ask, self.click = observe, ask, click
        self.cancelled, self.settle = cancelled, settle
        self.notify, self.answer_ready = notify, answer_ready
        self.submit_attempts = submit_attempts if submit_attempts is not None else set()
        self.completed, self.skipped = set(), set()
        self.visited = set()
        self.retry_signature = retry_signature
        # submit_attempts 现在只表示等待确认的请求，成功记录单独存储。
        self.confirmed_submissions = confirmed_submissions if confirmed_submissions is not None else set()

    def mark_confirmed(self, signature):
        self.submit_attempts.discard(signature)
        self.confirmed_submissions.add(signature)

    def prepare_retry(self, current):
        """用户显式授权的一题一次恢复，不清除其它题或本题原提交记录。"""
        target = self.retry_signature
        if not target or target not in self.submit_attempts:
            raise ValueError("没有可恢复的提交记录，请使用普通开始。")
        self.status("重新检查本题；请先手动完成页面安全核验", current.report)
        for attempt in range(2):
            self.check_stop()
            report = current.report
            if report.get("page_blocker"):
                raise ValueError("安全核验尚未完成，请手动处理后再恢复。")
            if report.get("question_signature") != target:
                raise ValueError("当前题与待恢复的题不一致，未允许重试。")
            state = report.get("page_state", {})
            if state.get("submitted") is True:
                self.retry_signature = None
                return current  # 已提交就正常检查下一题，不能重发。
            if state.get("submitted") is not False or state.get("can_submit") is not True:
                raise ValueError("恢复前必须确认当前未提交且蓝色提交按钮可用。")
            choices = [c for c in report["controls"] if c["kind"].endswith("option")]
            kind = report.get("question_type")
            expected = {"A", "B", "C", "D"} if kind == "single" else {"true", "false"} if kind == "boolean" else set()
            if (not expected or len(choices) != len(expected) or {c.get("label") for c in choices} != expected
                    or any(c.get("selected") is None or c["confidence"] < .65 for c in choices)
                    or sum(c.get("selected") is True for c in choices) != 1):
                raise ValueError("恢复前选项或选择状态无法确认，未允许重试。")
            if attempt == 0:
                if self.settle():
                    raise AutoStopped("已停止，未重试。")
                current = self.observe()
        return current

    def check_stop(self):
        if self.cancelled():
            raise AutoStopped("已停止；不会执行后续点击。")

    def status(self, text, report=None):
        self.check_stop()
        self.notify({"status": text, "question_type": (report or {}).get("question_type"),
                     "question_signature": (report or {}).get("question_signature"),
                     "confirmed": len(self.completed), "skipped": len(self.skipped)})

    def wait_to_submit(self, selected, signature, answer):
        """确认选中的是 AI 答案后等待提交可用，不把灰色提交当成完成。"""
        current = selected
        for attempt in range(6):
            self.check_stop()
            report = current.report
            if report.get("question_signature") != signature:
                raise ValueError("提交前题目发生变化，已暂停，未提交。")
            state = report.get("page_state", {})
            if state.get("submitted") is True:
                return current
            choices = [c for c in report["controls"] if c["kind"].endswith("option")]
            chosen = [c for c in choices if c.get("selected") is True]
            if (len(chosen) != 1 or chosen[0].get("label") != answer or
                    any(c.get("selected") is None for c in choices)):
                raise ValueError("提交前选中项与 DeepSeek 答案不一致或选择状态未知，已暂停。")
            if state.get("submitted") is False and state.get("can_submit") is True:
                return current
            if attempt < 5:
                self.status("AI 答案已选中，等待提交按钮更新", report)
                if self.settle():
                    raise AutoStopped("已停止，未提交。")
                self.check_stop()
                current = self.observe()
        raise ValueError("AI 答案已确认选中，但提交按钮尚未可用；已暂停，不判定为完成。")

    def run(self):
        self.status("正在识别答题页面")
        current = self.observe()
        if self.retry_signature:
            current = self.prepare_retry(current)
        while True:
            self.check_stop()
            report = current.report
            signature = report.get("question_signature")
            if not signature:
                raise ValueError("无法确认题目，请框入完整题型、题干和全部选项。")
            state = report.get("page_state", {})
            self.status("检查页面状态", report)
            if state.get("submitted") is True:
                self.mark_confirmed(signature)
                if signature not in self.completed:
                    self.skipped.add(signature)
                if state.get("next_enabled") is False:
                    # 同一状态再读一次，避免短暂绘制或漏检误判结束。
                    confirm = self.observe()
                    end = confirm.report.get("page_state", {})
                    if (confirm.report.get("question_signature") != signature or
                            end.get("submitted") is not True or end.get("next_enabled") is not False):
                        raise ValueError("完成状态未稳定确认，已暂停。")
                    self.status("全部作答完成（已提交且下一题灰色禁用）", confirm.report)
                    return
                if state.get("next_enabled") is not True:
                    raise ValueError("下一题是否可用无法确认，已暂停。")
                if signature in self.visited:
                    raise ValueError("检测到重复题目或翻题循环，已暂停。")
                self.visited.add(signature)
                self.status("当前题已提交，正在进入下一题", report)
                current = button_once(report, "next", self.observe, self.click, self.cancelled, self.settle)
                if not current.report["manual_action"]["verified"]:
                    raise ValueError("未确认下一题切换，已暂停，不重复点击。")
                continue
            if state.get("submitted") is not False:
                raise ValueError("提交状态未知，请完整框入底部提交按钮。")
            if signature in self.submit_attempts and signature != self.retry_signature:
                raise ValueError("本题有待确认提交。恢复同题请用“重新检查并重试本题”；重新作答请用“新一轮答题”。")
            kind = report.get("question_type")
            expected = {"A", "B", "C", "D"} if kind == "single" else {"true", "false"} if kind == "boolean" else None
            choices = [c for c in report["controls"] if c["kind"].endswith("option")]
            labels = [c.get("label") for c in choices]
            if expected is None or len(labels) != len(expected) or set(labels) != expected:
                raise ValueError("仅支持完整识别的 A/B/C/D 单选题和 √/× 判断题。")
            if any(c.get("selected") is None for c in choices):
                raise ValueError("部分选项选择状态未知，已暂停。")
            if sum(c.get("selected") is True for c in choices) > 1:
                raise ValueError("单选或判断题出现多个已选中项，已暂停。")
            # 灰色提交只是尚不能提交，未答题时仍正常请求 AI 并选择答案。
            self.status("当前题未提交，DeepSeek 正在作答", report)
            answer = validate_answer(self.ask(current.original, kind, labels), kind, labels)
            self.check_stop()
            self.answer_ready(answer)
            self.status("重新核对题目并选择 AI 答案", report)
            selected = choose_once(report, answer["answer"][0], self.observe, self.click,
                                   self.cancelled, self.settle)
            self.check_stop()
            if not selected.report["manual_click"]["verified"]:
                raise ValueError(selected.report["manual_click"]["message"])
            selected = self.wait_to_submit(selected, signature, answer["answer"][0])
            if selected.report.get("page_state", {}).get("submitted") is True:
                current = selected
                continue
            self.status("正在提交并确认结果", selected.report)
            submit_sent = False

            def submit_click(x, y, cancelled):
                nonlocal submit_sent
                self.check_stop()
                # 一次恢复授权只用于本题本次提交；失败后仍保留锁。
                self.retry_signature = None
                self.submit_attempts.add(signature)
                submit_sent = True
                self.click(x, y, cancelled)

            def submit_observe():
                # button_once 在真正点击前会再读一次，仍须核对所选答案。
                fresh = self.observe()
                if not submit_sent:
                    return self.wait_to_submit(fresh, signature, answer["answer"][0])
                return fresh

            current = button_once(selected.report, "submit", submit_observe, submit_click,
                                  self.cancelled, self.settle)
            self.check_stop()
            result = current.report["manual_action"]
            if result["verified"]:
                self.mark_confirmed(signature)
                self.completed.add(signature)
            elif result["question_changed"]:
                # 自动翻题时不补点下一题，先确认新题连续两次观察一致。
                confirm = self.observe()
                if (confirm.report.get("question_signature") != current.report.get("question_signature") or
                        confirm.report.get("page_state", {}).get("submitted") not in (True, False)):
                    raise ValueError("提交后页面切换未稳定确认，已暂停。")
                self.status("提交后检测到页面自动切换；提交结果未单独确认，继续检查新题", confirm.report)
                current = confirm
            else:
                raise ValueError("未确认提交成功，已暂停，不重复提交。")
