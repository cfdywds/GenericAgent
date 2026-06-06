import io
import math
import os
import pathlib
import sys
import time
import tempfile
import unittest
from itertools import count
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

    def test_continue_choice_label_uses_session_meta_role_and_parent(self):
        with patch.object(
            tui.session_meta,
            "get_meta",
            return_value={"role": "goal_child", "parent_log": "D:/tmp/model_responses_parent.txt"},
        ):
            label = tui.sidebar_continue_choice_label(
                path="D:/tmp/model_responses_12.txt",
                mtime=1_783_000_000.0,
                preview="持续推进修复历史栏",
                rounds=5,
                persisted_name="",
            )

        self.assertIn("[goal child]", label)
        self.assertIn("└─", label)
        self.assertIn("5轮", label)

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
    def test_sidebar_rows_keep_internal_display_order_for_click_mapping(self):
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
        self.assertEqual(tui.sidebar_sid_at_visual_row({1: current, 10: first_history, 20: second_history}, 1, 3), 10)

    def test_sidebar_order_does_not_change_when_current_session_changes(self):
        older = tui.AgentSession(agent_id=1, name="older", status="history", sidebar_sort_at=100.0)
        newer = tui.AgentSession(agent_id=2, name="newer", status="history", sidebar_sort_at=200.0)
        rows_when_older_current = tui.sidebar_render_rows({1: older, 2: newer}, current_id=1)
        rows_when_newer_current = tui.sidebar_render_rows({1: older, 2: newer}, current_id=2)

        self.assertEqual([row.sid for row in rows_when_older_current], [2, 1])
        self.assertEqual([row.sid for row in rows_when_newer_current], [2, 1])

    def test_sidebar_click_mapping_uses_displayed_titles_without_refreshing_names(self):
        first_path = "D:/tmp/model_responses_first.txt"
        first = tui.AgentSession(
            agent_id=1,
            name="history-first",
            status="history",
            lazy_history_path=first_path,
            lazy_history_mtime=200.0,
            lazy_history_preview="这是一个非常非常长的历史会话标题，会换很多行，导致点击区域变大",
            lazy_history_rounds=3,
            sidebar_sort_at=200.0,
        )
        second = tui.AgentSession(
            agent_id=2,
            name="history-second",
            status="history",
            lazy_history_path="D:/tmp/model_responses_second.txt",
            lazy_history_mtime=100.0,
            lazy_history_preview="第二个会话",
            lazy_history_rounds=2,
            sidebar_sort_at=100.0,
        )
        tui.refresh_sidebar_metadata(first, name_lookup=lambda path: "短名" if path == first_path else "")
        tui.refresh_sidebar_metadata(second, name_lookup=lambda _path: "")

        sid = tui.sidebar_sid_at_visual_row({1: first, 2: second}, None, visual_row=4, content_width=18)

        self.assertEqual(sid, 2)

    def test_sidebar_history_row_hides_volatile_display_number(self):
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

        self.assertNotIn("#1", title_text.plain)
        self.assertNotIn(tui.C_CHIP_TASKS, title_styles)
        self.assertIn(f"bold {tui.C_CHIP_NAME}", title_styles)
        self.assertIn(tui.C_CHIP_TIME, meta_styles)
        self.assertIn(tui.C_GREEN, meta_styles)
        self.assertIn(time.strftime("%m-%d", time.localtime(1_783_000_000.0)), meta_text.plain)
        self.assertIn("3轮", meta_text.plain)

    def test_scroll_active_session_does_not_move_when_active_row_is_visible(self):
        app = tui.GenericAgentTUI(agent_factory=lambda: SimpleNamespace())
        current = tui.AgentSession(agent_id=1, name="current", status="idle")
        current.sidebar_title = "current"
        current.sidebar_activity_at = 300.0
        other = tui.AgentSession(agent_id=2, name="other", status="idle")
        other.sidebar_title = "other"
        other.sidebar_activity_at = 200.0
        app.sessions = {1: current, 2: other}
        app.current_id = 2
        scroll = SimpleNamespace(
            scroll_y=0,
            content_region=SimpleNamespace(height=12),
            size=SimpleNamespace(height=12),
            scroll_to_region=lambda *args, **kwargs: None,
        )

        with patch.object(app, "query_one", return_value=scroll), \
             patch.object(app, "_sidebar_content_width", return_value=30), \
             patch.object(app, "call_after_refresh") as after_refresh:
            app._scroll_active_session_into_view()

        after_refresh.assert_not_called()

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
        self.assertIn("────────", output)
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

        self.assertIn("Browser", output)
        self.assertNotIn("#1", output)
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

        self.assertIn("runner", output)
        self.assertNotIn("#1 runner", output)
        self.assertIn("running", output)

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

    def test_render_sidebar_uses_session_meta_for_child_history(self):
        sess = tui.AgentSession(
            agent_id=6,
            name="history-goal-child",
            status="history",
            lazy_history_path="D:/tmp/model_responses_6.txt",
            lazy_history_mtime=1_783_000_000.0,
            lazy_history_preview="持续推进修复侧栏",
            lazy_history_rounds=7,
        )

        with patch.object(
            tui.session_meta,
            "get_meta",
            return_value={"role": "goal_child", "parent_log": "D:/tmp/model_responses_parent.txt"},
        ):
            tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")
            output = render_plain(tui.render_sidebar({6: sess}, current_id=6))

        self.assertEqual(sess.sidebar_kind, "goal_child")
        self.assertIn("└─", output)
        self.assertIn("[goal child]", output)

    def test_goal_launcher_stays_grouped_with_running_child(self):
        parent_log = "D:/tmp/model_responses_parent.txt"
        child_log = "D:/tmp/model_responses_child.txt"
        launcher = tui.AgentSession(agent_id=3, name="launcher", status="idle")
        launcher.agent = SimpleNamespace(log_path=parent_log, llmclient=SimpleNamespace(backend=SimpleNamespace(history=[])))
        launcher.sidebar_title = "记忆更新已校验完成。"
        launcher.sidebar_activity_at = 100.0
        child = tui.AgentSession(
            agent_id=1,
            name="goal-child",
            status="running",
            lazy_history_path=child_log,
            lazy_history_mtime=110.0,
            lazy_history_preview="完善手机服务器环境",
            lazy_history_rounds=7,
        )

        def fake_meta(path):
            if path == parent_log:
                return {"role": "goal_launcher"}
            if path == child_log:
                return {"role": "goal_child", "parent_log": parent_log}
            return {}

        with patch.object(tui.session_meta, "get_meta", side_effect=fake_meta):
            for sess in (launcher, child):
                tui.refresh_sidebar_metadata(sess, name_lookup=lambda _path: "")
            output = render_plain(tui.render_sidebar({3: launcher, 1: child}, current_id=3))
            rows = tui.sidebar_render_rows({3: launcher, 1: child}, current_id=3)

        self.assertEqual([row.sid for row in rows], [3, 1])
        self.assertIn("goal running", output)
        self.assertNotIn("goal_launcher idle", output)

    def test_goal_parent_child_order_does_not_change_when_child_is_current(self):
        parent_log = "D:/tmp/model_responses_parent.txt"
        child_log = "D:/tmp/model_responses_child.txt"
        launcher = tui.AgentSession(agent_id=3, name="launcher", status="idle")
        launcher.agent = SimpleNamespace(log_path=parent_log, llmclient=SimpleNamespace(backend=SimpleNamespace(history=[])))
        child = tui.AgentSession(
            agent_id=1,
            name="goal-child",
            status="history",
            lazy_history_path=child_log,
            lazy_history_mtime=110.0,
            lazy_history_preview="持续推进",
            lazy_history_rounds=7,
            sidebar_sort_at=110.0,
        )

        def fake_meta(path):
            if path == parent_log:
                return {"role": "goal_launcher"}
            if path == child_log:
                return {"role": "goal_child", "parent_log": parent_log}
            return {}

        with patch.object(tui.session_meta, "get_meta", side_effect=fake_meta):
            rows_when_parent_current = tui.sidebar_render_rows({3: launcher, 1: child}, current_id=3)
            rows_when_child_current = tui.sidebar_render_rows({3: launcher, 1: child}, current_id=1)

        self.assertEqual([row.sid for row in rows_when_parent_current], [3, 1])
        self.assertEqual([row.sid for row in rows_when_child_current], [3, 1])

    def test_goal_child_groups_with_parent_when_paths_use_different_slashes(self):
        parent_log = "D:/tmp/model_responses_parent.txt"
        child_log = "D:/tmp/model_responses_child.txt"
        launcher = tui.AgentSession(agent_id=3, name="launcher", status="idle")
        launcher.agent = SimpleNamespace(log_path=parent_log, llmclient=SimpleNamespace(backend=SimpleNamespace(history=[])))
        child = tui.AgentSession(
            agent_id=1,
            name="goal-child",
            status="history",
            lazy_history_path=child_log,
            lazy_history_mtime=110.0,
            lazy_history_preview="持续推进",
            lazy_history_rounds=7,
            sidebar_sort_at=110.0,
        )

        def fake_meta(path):
            if path == parent_log:
                return {"role": "goal_launcher"}
            if path == child_log:
                return {"role": "goal_child", "parent_log": parent_log.replace("/", "\\")}
            return {}

        with patch.object(tui.session_meta, "get_meta", side_effect=fake_meta):
            rows = tui.sidebar_render_rows({3: launcher, 1: child}, current_id=3)

        self.assertEqual([row.sid for row in rows], [3, 1])

    def test_goal_child_history_uses_live_pid_as_running_status(self):
        child_log = "D:/tmp/model_responses_child.txt"
        child = tui.AgentSession(
            agent_id=1,
            name="goal-child",
            status="history",
            lazy_history_path=child_log,
            lazy_history_mtime=110.0,
            lazy_history_preview="持续推进",
            lazy_history_rounds=7,
        )

        with patch.object(
            tui.session_meta,
            "get_meta",
            return_value={"role": "goal_child", "parent_log": "D:/tmp/model_responses_parent.txt", "pid": 4242},
        ), patch.object(tui, "_pid_is_running", return_value=True):
            tui.refresh_sidebar_metadata(child, name_lookup=lambda _path: "")
            output = render_plain(tui.render_sidebar({1: child}, current_id=None))

        self.assertIn("running", output)
        self.assertIn("7轮", output)

    def test_history_loader_does_not_readd_materialized_history_session(self):
        app = tui.GenericAgentTUI(agent_factory=lambda: SimpleNamespace())
        app._ids = count(2)
        history_log = os.path.abspath("D:/tmp/model_responses_history.txt")
        live_log = os.path.abspath("D:/tmp/model_responses_live.txt")
        restored = tui.AgentSession(
            agent_id=1,
            name="restored",
            status="idle",
            lazy_history_path=history_log,
            lazy_history_mtime=110.0,
            lazy_history_preview="已恢复的历史会话",
            lazy_history_rounds=3,
            agent=SimpleNamespace(log_path=live_log),
        )
        app.sessions = {1: restored}
        app.current_id = 1

        with patch.object(tui, "continue_list", return_value=[(history_log, 110.0, "已恢复的历史会话", 3)]):
            added = app._load_history_sidebar_sessions(report_errors=False, refresh=False)

        self.assertEqual(added, 0)
        self.assertEqual(len(app.sessions), 1)

    def test_history_loader_collapses_byte_identical_log_files(self):
        app = tui.GenericAgentTUI(agent_factory=lambda: SimpleNamespace())
        app._ids = count(1)
        with tempfile.TemporaryDirectory() as tmp:
            first_log = os.path.join(tmp, "model_responses_111111.txt")
            second_log = os.path.join(tmp, "model_responses_222222.txt")
            content = b"=== Prompt === 2026-06-06 01:19:14\nsame\n=== Response ===\nsame\n"
            for path in (first_log, second_log):
                with open(path, "wb") as fh:
                    fh.write(content)

            entries = [
                (first_log, 1_780_679_954.0, "已改为PowerShell单bat启动", 20),
                (second_log, 1_780_679_954.0, "已改为PowerShell单bat启动", 20),
            ]
            with patch.object(tui, "continue_list", return_value=entries):
                added = app._load_history_sidebar_sessions(report_errors=False, refresh=False)

        self.assertEqual(added, 1)
        self.assertEqual(len(app.sessions), 1)

    def test_history_activation_keeps_source_log_reserved_for_later_sync(self):
        app = tui.GenericAgentTUI(agent_factory=lambda: SimpleNamespace())
        with tempfile.TemporaryDirectory() as tmp:
            source_log = os.path.join(tmp, "model_responses_111111.txt")
            live_log = os.path.join(tmp, "model_responses_222222.txt")
            content = b"=== Prompt === 2026-06-06 01:19:14\nsame\n=== Response ===\nsame\n"
            with open(source_log, "wb") as fh:
                fh.write(content)

            sess = tui.AgentSession(
                agent_id=1,
                name="history",
                status="history",
                lazy_history_path=source_log,
                lazy_history_mtime=1_780_679_954.0,
                lazy_history_preview="已改为PowerShell单bat启动",
                lazy_history_rounds=20,
            )
            app.sessions = {1: sess}
            app.current_id = 1
            fake_agent = SimpleNamespace(log_path=live_log)

            def start_agent(target):
                target.agent = fake_agent
                return fake_agent

            import continue_cmd

            with patch.object(app, "_start_agent_for_session", side_effect=start_agent), \
                 patch.object(app, "_remount_current_session"), \
                 patch.object(app, "_refresh_all"), \
                 patch.object(continue_cmd, "reset_conversation"), \
                 patch.object(continue_cmd, "restore", return_value=("✅ 已恢复", True)), \
                 patch.object(tui, "continue_extract", return_value=[]):
                self.assertTrue(app._activate_history_session(sess))

            entries = [
                (source_log, 1_780_679_954.0, "已改为PowerShell单bat启动", 20),
                (live_log, 1_780_679_954.0, "已改为PowerShell单bat启动", 20),
            ]
            with patch.object(tui, "continue_list", return_value=entries):
                added = app._load_history_sidebar_sessions(report_errors=False, refresh=False)

        self.assertEqual(added, 0)
        self.assertEqual(len(app.sessions), 1)

    def test_history_activation_preserves_sidebar_order_from_logical_history_time(self):
        app = tui.GenericAgentTUI(agent_factory=lambda: SimpleNamespace())
        with tempfile.TemporaryDirectory() as tmp:
            source_log = os.path.join(tmp, "model_responses_111111.txt")
            live_log = os.path.join(tmp, "model_responses_222222.txt")
            with open(source_log, "wb") as fh:
                fh.write(b"=== Prompt === 2026-06-06 01:19:14\nsame\n=== Response ===\nsame\n")
            os.utime(source_log, (1_000.0, 1_000.0))

            newer = tui.AgentSession(agent_id=1, name="newer", status="history", sidebar_sort_at=500.0)
            target = tui.AgentSession(
                agent_id=2,
                name="target",
                status="history",
                lazy_history_path=source_log,
                lazy_history_mtime=300.0,
                lazy_history_preview="target",
                lazy_history_rounds=2,
                sidebar_sort_at=300.0,
            )
            older = tui.AgentSession(agent_id=3, name="older", status="history", sidebar_sort_at=100.0)
            app.sessions = {1: newer, 2: target, 3: older}
            app.current_id = 1
            before = [sid for sid, _sess in tui.sidebar_ordered_sessions(app.sessions, app.current_id)]
            fake_agent = SimpleNamespace(log_path=live_log)

            def start_agent(sess):
                sess.agent = fake_agent
                return fake_agent

            import continue_cmd

            with patch.object(app, "_start_agent_for_session", side_effect=start_agent), \
                 patch.object(app, "_remount_current_session"), \
                 patch.object(app, "_refresh_all"), \
                 patch.object(continue_cmd, "reset_conversation"), \
                 patch.object(continue_cmd, "restore", return_value=("✅ 已恢复", True)), \
                 patch.object(tui, "continue_extract", return_value=[]):
                self.assertTrue(app._activate_history_session(target))

            after = [sid for sid, _sess in tui.sidebar_ordered_sessions(app.sessions, app.current_id)]

        self.assertEqual(before, [1, 2, 3])
        self.assertEqual(after, before)
        self.assertEqual(target.sidebar_sort_at, 300.0)

    def test_tick_discovers_new_goal_child_history_while_launcher_is_active(self):
        app = tui.GenericAgentTUI(agent_factory=lambda: SimpleNamespace())
        app._ids = count(2)
        parent_log = "D:/tmp/model_responses_parent.txt"
        child_log = "D:/tmp/model_responses_child.txt"
        launcher = tui.AgentSession(agent_id=1, name="goal launcher", status="idle")
        launcher.agent = SimpleNamespace(
            log_path=parent_log,
            llmclient=SimpleNamespace(backend=SimpleNamespace(history=[])),
        )
        launcher.sidebar_kind = "goal_launcher"
        app.sessions = {1: launcher}
        app.current_id = 1
        app._last_size = (80, 24)

        def fake_meta(path):
            base = os.path.basename(str(path).replace("\\", "/"))
            if base == os.path.basename(parent_log):
                return {"role": "goal_launcher"}
            if base == os.path.basename(child_log):
                return {"role": "goal_child", "parent_log": parent_log, "pid": 4242}
            return {}

        with patch.object(tui, "continue_list", return_value=[(child_log, 110.0, "持续推进", 7)]) as list_mock, \
             patch.object(tui.session_meta, "get_meta", side_effect=fake_meta), \
             patch.object(tui, "_pid_is_running", return_value=True), \
             patch.object(app, "_refresh_topbar"), \
             patch.object(app, "_refresh_sidebar"), \
             patch.object(app, "_apply_responsive_layout"):
            app._tick()
            list_mock.assert_called_once()
            self.assertIn(child_log, [sess.lazy_history_path for sess in app.sessions.values()])
            rows = tui.sidebar_render_rows(app.sessions, current_id=1)

        self.assertEqual([row.sid for row in rows], [1, 2])
        self.assertEqual(rows[1].sess.sidebar_parent_log, parent_log)


if __name__ == "__main__":
    unittest.main()
