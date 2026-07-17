# -*- coding: utf-8 -*-
import re
import unittest
from types import SimpleNamespace
from unittest import mock

import ga
from agent_loop import StepOutcome, exhaust


class FakeResponse:
    def __init__(self, content="", thinking=""):
        self.content = content
        self.thinking = thinking
        self.tool_calls = []


class DoNoToolMidTaskTests(unittest.TestCase):
    def setUp(self):
        parent = SimpleNamespace(
            task_dir=None,
            verbose=False,
            extrakeyinfo=None,
            intervene=None,
            get_ctx_multiplier=lambda: 1.0,
        )
        self.handler = ga.GenericAgentHandler(parent, last_history=[], cwd="./temp")
        self.handler.current_turn = 5
        self.handler.working["key_info"] = "long task context"
        self.handler.history_info = [
            "[USER]: do long work",
            "[Agent] reading files",
            "[Agent] editing modules",
        ]

    def _run(self, content):
        return exhaust(self.handler.do_no_tool({}, FakeResponse(content=content)))

    def test_mid_task_status_without_tools_continues(self):
        outcome = self._run("<summary>进度同步</summary>\n已检查模块，下一步准备继续改代码。")
        self.assertIsInstance(outcome, StepOutcome)
        self.assertFalse(outcome.should_exit)
        self.assertTrue(outcome.next_prompt)
        self.assertIn("不能结束整轮执行", outcome.next_prompt)
        self.assertEqual(outcome.data.get("result"), "NO_TOOL_CONTINUE")

    def test_mid_task_explicit_completion_can_finish(self):
        outcome = self._run("<summary>收尾</summary>\n任务已完成：所有目标都处理完毕。")
        self.assertIsInstance(outcome, StepOutcome)
        self.assertIsNone(outcome.next_prompt)

    def test_hidden_completion_cannot_override_visible_incomplete_status(self):
        outcome = self._run("<summary>任务已完成</summary>\n正在继续处理剩余问题。")
        self.assertIsInstance(outcome, StepOutcome)
        self.assertTrue(outcome.next_prompt)
        self.assertEqual(outcome.data.get("result"), "NO_TOOL_CONTINUE")

    def test_early_simple_answer_can_finish(self):
        self.handler.current_turn = 1
        self.handler.working = {}
        self.handler.history_info = ["[USER]: 1+1=?"]
        outcome = self._run("答案是 2。")
        self.assertIsNone(outcome.next_prompt)

    def test_plan_mode_open_items_force_continue(self):
        with mock.patch.object(self.handler, "_in_plan_mode", return_value="plan.md"), \
             mock.patch.object(self.handler, "_check_plan_completion", return_value=3):
            outcome = self._run("<summary>进度</summary>\n先看下一步。")
        self.assertTrue(outcome.next_prompt)
        self.assertEqual(outcome.data.get("result"), "PLAN_INCOMPLETE_CONTINUE")
        self.assertIn("未完成项", outcome.next_prompt)

    def test_blank_still_retries(self):
        outcome = self._run("<summary>only summary</summary>")
        self.assertTrue(outcome.next_prompt)
        self.assertIn("Blank response", outcome.next_prompt)


if __name__ == "__main__":
    unittest.main()
