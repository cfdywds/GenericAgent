import io
import math
import os
import pathlib
import sys
import time
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

import tuiapp_v2 as tui


def render_plain(renderable, width: int = 80) -> str:
    from rich.console import Console

    console = Console(width=width, record=True, file=io.StringIO())
    console.print(renderable)
    return console.export_text()


class SidebarHelperTests(unittest.TestCase):
    def test_sidebar_sessions_running_then_recent_activity_without_current_pin(self):
        current = tui.AgentSession(agent_id=1, name="current", status="idle")
        old_history = tui.AgentSession(
            agent_id=2,
            name="history-old",
            status="history",
            lazy_history_mtime=100.0,
            sidebar_activity_at=100.0,
        )
        running = tui.AgentSession(agent_id=3, name="runner", status="running")
        running.sidebar_activity_at = 10.0
        recent = tui.AgentSession(agent_id=4, name="recent", status="idle")
        recent.sidebar_activity_at = 500.0

        ordered = tui.sidebar_ordered_sessions(
            {2: old_history, 4: recent, 1: current, 3: running}, current_id=1
        )

        self.assertEqual([sid for sid, _ in ordered], [3, 1, 4, 2])

    def test_sidebar_sessions_tie_breaks_by_descending_id(self):
        first = tui.AgentSession(agent_id=1, name="first", status="idle")
        second = tui.AgentSession(agent_id=2, name="second", status="idle")
        first.sidebar_activity_at = 100.0
        second.sidebar_activity_at = 100.0

        ordered = tui.sidebar_ordered_sessions({1: first, 2: second}, current_id=None)

        self.assertEqual([sid for sid, _ in ordered], [2, 1])

    def test_refresh_sidebar_metadata_uses_live_agent_log_mtime_for_activity(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            log_path = f.name
        self.addCleanup(lambda: os.path.exists(log_path) and os.unlink(log_path))
        os.utime(log_path, (1_783_000_000.0, 1_783_000_000.0))
        agent = SimpleNamespace(
            log_path=log_path,
            llmclient=SimpleNamespace(
                backend=SimpleNamespace(
                    history=[
                        {"role": "user", "content": "live prompt"},
                        {"role": "assistant", "content": "<summary>live summary</summary>"},
                    ]
                )
            ),
        )
        sess = tui.AgentSession(agent_id=8, name="live", status="idle", agent=agent)
        sess.created_at = 10.0
        sess.last_activity_at = 20.0

        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        self.assertEqual(sess.sidebar_activity_at, 1_783_000_000.0)

    def test_refresh_sidebar_metadata_skips_history_scan_when_cheap_signature_matches(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            log_path = f.name
        self.addCleanup(lambda: os.path.exists(log_path) and os.unlink(log_path))
        os.utime(log_path, (1_783_000_000.0, 1_783_000_000.0))
        history = [
            {"role": "user", "content": "cached prompt"},
            {"role": "assistant", "content": "<summary>cached summary</summary>"},
        ]
        agent = SimpleNamespace(
            log_path=log_path,
            llmclient=SimpleNamespace(backend=SimpleNamespace(history=history)),
        )
        sess = tui.AgentSession(agent_id=10, name="cached", status="idle", agent=agent)
        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        with patch.object(tui, "_sidebar_last_user", side_effect=AssertionError("rescanned user")), \
             patch.object(tui, "_sidebar_last_summary", side_effect=AssertionError("rescanned summary")):
            tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        self.assertEqual(sess.sidebar_title, "cached")
        self.assertEqual(sess.sidebar_preview, "cached prompt")
        self.assertEqual(sess.sidebar_summary, "cached summary")

    def test_sidebar_display_name_prefers_persisted_then_preview_then_timestamp(self):
        self.assertEqual(
            tui.sidebar_display_name(
                path="model_responses_123.txt",
                persisted_name="Billing audit",
                preview="ignored preview",
                mtime=1_783_000_000.0,
            ),
            "Billing audit",
        )
        self.assertEqual(
            tui.sidebar_display_name(
                path="model_responses_123.txt",
                persisted_name="",
                preview="请帮我优化历史会话栏排序规则，并调整界面样式。",
                mtime=1_783_000_000.0,
            ),
            "请帮我优化历史会话栏排序规则，并调整界面样式。",
        )
        self.assertEqual(
            tui.sidebar_display_name(
                path="model_responses_123.txt",
                persisted_name="",
                preview="",
                mtime=1_783_000_000.0,
            ),
            "history " + time.strftime("%m-%d %H:%M", time.localtime(1_783_000_000.0)),
        )

    def test_lazy_sidebar_metadata_prefills_without_agent(self):
        sess = tui.AgentSession(
            agent_id=9,
            name="history-raw",
            status="history",
            lazy_history_path="D:/tmp/model_responses_9.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="最后一个真实用户问题",
            lazy_history_rounds=7,
        )

        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        self.assertEqual(sess.sidebar_title, "最后一个真实用户问题")
        self.assertEqual(sess.sidebar_preview, "最后一个真实用户问题")
        self.assertEqual(sess.sidebar_summary, "7轮")
        self.assertEqual(sess.sidebar_activity_at, 1_783_000_000.0)

    def test_goal_history_session_is_marked_as_goal_child_session(self):
        sess = tui.AgentSession(
            agent_id=11,
            name="history-goal",
            status="history",
            lazy_history_path="D:/tmp/model_responses_11.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="[Goal Mode — 持续推进] <objective>优化历史栏</objective>",
            lazy_history_rounds=4,
        )

        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        self.assertEqual(sess.sidebar_kind, "goal")
        self.assertIn("[goal]", sess.sidebar_summary)

    def test_continue_choice_label_marks_goal_child_session(self):
        label = tui.sidebar_continue_choice_label(
            path="D:/tmp/model_responses_11.txt",
            mtime=1_783_000_000.0,
            preview="[Goal Mode — 持续推进] <objective>优化历史栏</objective>",
            rounds=4,
            persisted_name="",
        )

        self.assertIn("[goal]", label)
        self.assertIn("4轮", label)

    def test_sidebar_sort_at_skips_nan_and_inf(self):
        nan_sess = tui.AgentSession(agent_id=21, name="nan")
        nan_sess.sidebar_sort_at = math.nan
        nan_sess.sidebar_activity_at = 200.0

        inf_sess = tui.AgentSession(agent_id=22, name="inf")
        inf_sess.sidebar_sort_at = math.inf
        inf_sess.sidebar_activity_at = math.inf
        inf_sess.created_at = 300.0

        self.assertEqual(tui._sidebar_sort_at(nan_sess), 200.0)
        self.assertEqual(tui._sidebar_sort_at(inf_sess), 300.0)

    def test_cell_width_counts_emoji_as_wide(self):
        self.assertEqual(tui._cell_width("🔥 Hot"), 6)
        self.assertEqual(tui._cell_width("❤️"), 2)


class SidebarRenderTests(unittest.TestCase):
    def test_sidebar_rows_use_display_order_numbers_not_internal_session_ids(self):
        current = tui.AgentSession(agent_id=1, name="current", status="idle")
        current.sidebar_title = "current"
        first_history = tui.AgentSession(
            agent_id=10,
            name="history-a",
            status="history",
            lazy_history_path="D:/tmp/model_responses_10.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="第一个历史会话",
            lazy_history_rounds=6,
        )
        second_history = tui.AgentSession(
            agent_id=20,
            name="history-b",
            status="history",
            lazy_history_path="D:/tmp/model_responses_20.txt",
            lazy_history_mtime=1_783_000_100.0,
            lazy_history_preview="第二个历史会话",
            lazy_history_rounds=8,
        )
        for sess in (first_history, second_history):
            tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        rows = tui.sidebar_render_rows(
            {1: current, 10: first_history, 20: second_history},
            current_id=1,
        )

        self.assertEqual([(row.sid, row.display_no) for row in rows], [(20, 1), (10, 2), (1, 3)])
        self.assertEqual(tui.sidebar_sid_at_visual_row({1: current, 10: first_history, 20: second_history}, 1, 2), 10)

    def test_sidebar_history_row_has_distinct_styled_number_name_time_and_rounds(self):
        sess = tui.AgentSession(
            agent_id=12,
            name="history-styled",
            status="history",
            lazy_history_path="D:/tmp/model_responses_12.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="优化历史栏排序",
            lazy_history_rounds=3,
        )
        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        row = tui.sidebar_render_rows({12: sess}, current_id=12)[0]
        title_text, meta_text = tui.sidebar_render_row_text(row)
        title_styles = {span.style for span in title_text.spans}
        meta_styles = {span.style for span in meta_text.spans}

        self.assertIn(tui.C_CHIP_TASKS, title_styles)
        self.assertIn(f"bold {tui.C_CHIP_NAME}", title_styles)
        self.assertIn(tui.C_CHIP_TIME, meta_styles)
        self.assertIn(tui.C_GREEN, meta_styles)
        self.assertIn(time.strftime("%m-%d", time.localtime(1_783_000_000.0)), meta_text.plain)
        self.assertIn("3轮", meta_text.plain)

    def test_render_sidebar_uses_compact_rows_and_hides_raw_history_filename(self):
        sess = tui.AgentSession(
            agent_id=2,
            name="history-raw",
            status="history",
            lazy_history_path="D:/tmp/model_responses_2.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="优化历史栏排序",
            lazy_history_rounds=3,
        )
        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        output = render_plain(tui.render_sidebar({2: sess}, current_id=2))

        self.assertIn("SESSIONS 1", output)
        self.assertIn("优化历史栏排序", output)
        self.assertIn("3轮", output)
        self.assertNotIn("model_responses_2", output)
        self.assertNotIn("Q:", output)
        self.assertNotIn("S:", output)

    def test_render_sidebar_keeps_title_visible_in_narrow_sidebar(self):
        sess = tui.AgentSession(
            agent_id=71,
            name="history-narrow",
            status="history",
            lazy_history_path="D:/tmp/model_responses_71.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="Goal agent卡住以后历史栏仍然要能看到标题",
            lazy_history_rounds=247,
        )
        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        output = render_plain(tui.render_sidebar({71: sess}, current_id=71), width=42)

        self.assertIn("Goal agent", output)
        self.assertNotIn("247轮 · 247轮", output)

    def test_render_sidebar_keeps_history_title_visible_in_narrow_sidebar(self):
        sess = tui.AgentSession(
            agent_id=7,
            name="history-browser",
            status="history",
            lazy_history_path="D:/tmp/model_responses_7.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="Browser unavailable after update",
            lazy_history_rounds=247,
        )
        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        output = render_plain(tui.render_sidebar({7: sess}, current_id=7), width=34)

        self.assertIn("#1 Browser", output)
        self.assertIn("247", output)

    def test_render_sidebar_includes_short_age_column(self):
        sess = tui.AgentSession(agent_id=3, name="aged", status="idle")
        sess.sidebar_title = "aged"
        sess.sidebar_summary = "idle"
        sess.sidebar_activity_at = 10_000.0 - 7_200.0

        with patch.object(tui.time, "time", return_value=10_000.0):
            output = render_plain(tui.render_sidebar({3: sess}, current_id=3))

        self.assertIn("2h", output)

    def test_render_sidebar_uses_active_glyph_for_non_current_running_session(self):
        current = tui.AgentSession(agent_id=1, name="current", status="idle")
        current.sidebar_title = "current"
        running = tui.AgentSession(agent_id=2, name="runner", status="running")
        running.sidebar_title = "runner"

        output = render_plain(tui.render_sidebar({1: current, 2: running}, current_id=1))

        self.assertIn("● #1 runner", output)

    def test_render_sidebar_distinguishes_goal_history_from_main_history(self):
        sess = tui.AgentSession(
            agent_id=5,
            name="history-goal",
            status="history",
            lazy_history_path="D:/tmp/model_responses_5.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="[Goal Mode — 持续推进] <objective>修复侧栏</objective>",
            lazy_history_rounds=2,
        )
        tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")

        output = render_plain(tui.render_sidebar({5: sess}, current_id=5))

        self.assertIn("[goal]", output)


if __name__ == "__main__":
    unittest.main()
