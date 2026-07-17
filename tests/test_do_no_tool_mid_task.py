# -*- coding: utf-8 -*-
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

    def test_completion_plus_continue_investigate_is_not_final(self):
        # review P1: "修复完成，继续排查..." must not end the run
        outcome = self._run("模块A修复完成，继续排查线上问题。")
        self.assertTrue(outcome.next_prompt)
        self.assertEqual(outcome.data.get("result"), "NO_TOOL_CONTINUE")
        self.assertIsNotNone(outcome.next_prompt)

    def test_completion_plus_bare_continue_is_not_final(self):
        outcome = self._run("修复完成，继续优化性能。")
        self.assertEqual(outcome.data.get("result"), "NO_TOOL_CONTINUE")

    def test_mid_task_explicit_completion_can_finish(self):
        outcome = self._run("<summary>收尾</summary>\n任务已完成：所有目标都处理完毕。")
        self.assertIsInstance(outcome, StepOutcome)
        self.assertIsNone(outcome.next_prompt)

    def test_courtesy_continue_asking_does_not_block_finish(self):
        outcome = self._run("任务已完成。还有问题可以继续提问。")
        self.assertIsNone(outcome.next_prompt)

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

    def test_plan_verified_completion_with_next_step_continues(self):
        # review P1: verified+complete but still announces more work
        with mock.patch.object(self.handler, "_in_plan_mode", return_value="plan.md"), \
             mock.patch.object(self.handler, "_check_plan_completion", return_value=2):
            outcome = self._run("P0 热修复 VERIFY PASS，任务完成。下一步处理 D1/D2。")
        self.assertEqual(outcome.data.get("result"), "PLAN_INCOMPLETE_CONTINUE")
        self.assertTrue(outcome.next_prompt)

    def test_plan_deferred_completion_with_continue_work_continues(self):
        with mock.patch.object(self.handler, "_in_plan_mode", return_value="plan.md"), \
             mock.patch.object(self.handler, "_check_plan_completion", return_value=2):
            outcome = self._run("修复完成，等待确认后再进入 Phase 0，然后继续改配置。")
        self.assertEqual(outcome.data.get("result"), "PLAN_INCOMPLETE_CONTINUE")

    def test_plan_verified_scoped_completion_can_finish(self):
        with mock.patch.object(self.handler, "_in_plan_mode", return_value="plan.md"), \
             mock.patch.object(self.handler, "_check_plan_completion", return_value=2):
            outcome = self._run("当前子任务 VERIFY PASS，任务已完成。后续阶段等你确认后再继续。")
        # has incomplete-ish "后续...继续" -> should continue under new guard
        # If wording is pure await without more agent work, may finish.
        # This text has 继续 -> incomplete signal -> continue
        self.assertEqual(outcome.data.get("result"), "PLAN_INCOMPLETE_CONTINUE")

    def test_plan_verified_await_only_can_finish(self):
        with mock.patch.object(self.handler, "_in_plan_mode", return_value="plan.md"), \
             mock.patch.object(self.handler, "_check_plan_completion", return_value=2):
            outcome = self._run("P0 热修复 VERIFY PASS，任务已完成。请确认是否进入下一阶段。")
        self.assertIsNone(outcome.next_prompt)

    def test_completed_plan_uses_recent_verdict_to_finish(self):
        self.handler.history_info.append("[Agent] VERDICT: PASS - verification complete")
        with mock.patch.object(self.handler, "_in_plan_mode", return_value="plan.md"), \
             mock.patch.object(self.handler, "_check_plan_completion", return_value=0):
            outcome = self._run("最终核验后结案。")
        self.assertIsNone(outcome.next_prompt)

    def test_blank_still_retries(self):
        outcome = self._run("<summary>only summary</summary>")
        self.assertTrue(outcome.next_prompt)
        self.assertIn("Blank response", outcome.next_prompt)

    def test_has_incomplete_work_signal_helpers(self):
        h = self.handler
        self.assertTrue(h._has_incomplete_work_signal("模块A修复完成，继续排查线上问题。"))
        self.assertTrue(h._has_incomplete_work_signal("修复完成，继续优化。"))
        self.assertTrue(h._has_incomplete_work_signal("任务完成。下一步处理 D1。"))
        self.assertFalse(h._has_incomplete_work_signal("任务已完成。还有问题可以继续提问。"))
        self.assertFalse(h._has_incomplete_work_signal("任务已完成。"))


if __name__ == "__main__":
    unittest.main()
