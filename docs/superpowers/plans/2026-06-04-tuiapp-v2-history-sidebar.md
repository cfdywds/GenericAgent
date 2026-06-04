# TUI v2 History Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `frontends/tuiapp_v2.py` history sidebar sorting, naming, render performance, and scan-friendly styling.

**Architecture:** Keep the change local to `tuiapp_v2.py` by adding sidebar metadata helpers and lightweight cached fields on `AgentSession`. Tests exercise pure helper behavior and Rich render output without launching the Textual app.

**Tech Stack:** Python 3, `unittest`, Textual/Rich already used by `frontends/tuiapp_v2.py`, existing `continue_cmd` and `session_names` helpers.

---

## File Structure

- Modify `frontends/tuiapp_v2.py`: add sidebar metadata fields, sort/name helpers, compact `render_sidebar`, metadata refresh calls, and `/continue` display-name reuse.
- Create `tests/test_tuiapp_v2_sidebar.py`: focused unit tests for sorting, naming, lazy metadata, and rendered sidebar text.
- Read-only reference `docs/superpowers/specs/2026-06-04-tuiapp-v2-history-sidebar-design.md`: approved behavior.

## Task 1: Sidebar Helper Tests

**Files:**
- Create: `tests/test_tuiapp_v2_sidebar.py`
- Modify: none

- [ ] **Step 1: Write failing tests for sort and naming helpers**

Create `tests/test_tuiapp_v2_sidebar.py` with this content:

```python
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

import tuiapp_v2 as tui


class SidebarHelperTests(unittest.TestCase):
    def test_sidebar_sessions_current_then_running_then_recent_activity(self):
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

        self.assertEqual([sid for sid, _ in ordered], [1, 3, 4, 2])

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
            "history 06-30 21:46",
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


class SidebarRenderTests(unittest.TestCase):
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

        rendered = tui.render_sidebar({2: sess}, current_id=2)
        text = rendered.__rich_console__(None, None)
        output = "\n".join(str(part) for part in text)

        self.assertIn("SESSIONS 1", output)
        self.assertIn("优化历史栏排序", output)
        self.assertIn("3轮", output)
        self.assertNotIn("model_responses_2", output)
        self.assertNotIn("Q:", output)
        self.assertNotIn("S:", output)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m unittest tests.test_tuiapp_v2_sidebar -v`

Expected: FAIL with missing helper attributes such as `sidebar_ordered_sessions`, `sidebar_display_name`, or `refresh_sidebar_metadata`.

## Task 2: Metadata Fields and Pure Helpers

**Files:**
- Modify: `frontends/tuiapp_v2.py` near `AgentSession` and sidebar helper functions
- Test: `tests/test_tuiapp_v2_sidebar.py`

- [ ] **Step 1: Add `AgentSession` metadata fields**

In `frontends/tuiapp_v2.py`, add these fields at the end of `AgentSession`:

```python
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    sidebar_title: str = ""
    sidebar_preview: str = ""
    sidebar_summary: str = ""
    sidebar_activity_at: float = 0.0
    sidebar_meta_sig: tuple = field(default_factory=tuple, repr=False)
```

- [ ] **Step 2: Add title, activity, and ordering helpers**

Replace the old `_history_session_name()` usage with module-level helpers near `# ---------- sidebar ----------`:

```python
def _plain_sidebar_text(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return _truncate(text, limit) if text else ""


def sidebar_display_name(path: str = "", persisted_name: str = "", preview: str = "", mtime: float = 0.0) -> str:
    persisted_name = _plain_sidebar_text(persisted_name, 40)
    if persisted_name:
        return persisted_name
    preview = _plain_sidebar_text(preview, 40)
    if preview:
        return preview
    if mtime:
        return "history " + time.strftime("%m-%d %H:%M", time.localtime(mtime))
    return "history"


def _safe_name_for(path: str) -> str:
    if not path:
        return ""
    try:
        import session_names as _sn
        return _sn.name_for(path)
    except Exception:
        return ""


def _session_log_path(sess: AgentSession) -> str:
    if sess.lazy_history_path:
        return sess.lazy_history_path
    try:
        return getattr(sess.agent, "log_path", "") or ""
    except Exception:
        return ""


def _session_log_mtime(path: str) -> float:
    if not path:
        return 0.0
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _sidebar_activity_time(sess: AgentSession, path: str = "") -> float:
    if sess.lazy_history_path and sess.agent is None:
        return float(sess.lazy_history_mtime or 0.0)
    log_mtime = _session_log_mtime(path)
    return max(float(log_mtime or 0.0), float(sess.last_activity_at or 0.0), float(sess.created_at or 0.0))


def refresh_sidebar_metadata(sess: AgentSession, name_lookup=None) -> None:
    path = _session_log_path(sess)
    activity = _sidebar_activity_time(sess, path)
    lazy = bool(sess.lazy_history_path and sess.agent is None)
    preview = sess.lazy_history_preview if lazy else _sidebar_last_user(sess)
    summary = f"{sess.lazy_history_rounds}轮" if lazy and sess.lazy_history_rounds else _sidebar_last_summary(sess)
    lookup = name_lookup or _safe_name_for
    try:
        persisted = lookup(path) if path else ""
    except Exception:
        persisted = ""
    sig = (path, activity, persisted, preview, summary, sess.status, sess.lazy_history_rounds)
    if sess.sidebar_meta_sig == sig:
        return
    sess.sidebar_title = sidebar_display_name(path, persisted, preview, activity)
    sess.sidebar_preview = _plain_sidebar_text(preview or summary, 96)
    sess.sidebar_summary = _plain_sidebar_text(summary, 40)
    sess.sidebar_activity_at = activity
    sess.sidebar_meta_sig = sig


def sidebar_ordered_sessions(sessions: dict[int, AgentSession], current_id: Optional[int]) -> list[tuple[int, AgentSession]]:
    def key(item):
        sid, sess = item
        refresh_sidebar_metadata(sess)
        current_rank = 0 if sid == current_id else 1
        running_rank = 0 if sess.status == "running" else 1
        return (current_rank, running_rank, -float(sess.sidebar_activity_at or 0.0), -sid)
    return sorted(sessions.items(), key=key)
```

- [ ] **Step 3: Run tests to verify helper tests pass or expose render-only failures**

Run: `python -m unittest tests.test_tuiapp_v2_sidebar -v`

Expected: helper tests pass; render test may still fail because `render_sidebar` still uses old layout.

## Task 3: Compact Sidebar Rendering and `/continue` Labels

**Files:**
- Modify: `frontends/tuiapp_v2.py` around `render_sidebar`, `_load_history_sidebar_sessions`, and `_cmd_continue`
- Test: `tests/test_tuiapp_v2_sidebar.py`

- [ ] **Step 1: Replace `render_sidebar` layout**

Change `render_sidebar()` to this structure:

```python
def render_sidebar(sessions: dict[int, AgentSession], current_id: Optional[int]) -> Table:
    outer = Table.grid(expand=True)
    outer.add_column()

    ordered = sidebar_ordered_sessions(sessions, current_id)
    outer.add_row(Text(f"SESSIONS {len(ordered)}", style=f"bold {C_DIM}"))
    outer.add_row(Text(""))

    sess_tbl = Table.grid(expand=True)
    sess_tbl.add_column(width=2)
    sess_tbl.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    sess_tbl.add_column(justify="right", no_wrap=True)
    sess_tbl.add_column(justify="right", no_wrap=True)

    SEL = f"on {C_SEL_BG}"
    blank = Text("")

    for sid, sess in ordered:
        active = sid == current_id
        lazy = bool(sess.lazy_history_path and sess.agent is None)
        style = SEL if active else None
        glyph = "●" if active or sess.status == "running" else "›"
        glyph_style = C_GREEN if active or sess.status == "running" else C_DIM
        name_style = f"bold {C_GREEN}" if active else (C_MUTED if lazy else C_FG)
        status = sess.sidebar_summary or (f"{sess.lazy_history_rounds}轮" if lazy and sess.lazy_history_rounds else sess.status)
        age = _short_age(sess.sidebar_activity_at) if sess.sidebar_activity_at else ""
        sess_tbl.add_row(
            Text(glyph, style=glyph_style),
            Text(_truncate(sess.sidebar_title or sess.name or "session", 24), style=name_style),
            Text(status, style=C_DIM),
            Text(age, style=C_DIM),
            style=style,
        )
        if sess.sidebar_preview:
            sess_tbl.add_row(
                blank,
                Text(sess.sidebar_preview, style=C_MUTED, no_wrap=True, overflow="ellipsis"),
                blank,
                blank,
                style=style,
            )
    outer.add_row(sess_tbl)
    return outer
```

- [ ] **Step 2: Prefill lazy history metadata on load**

Inside `_load_history_sidebar_sessions()`, after constructing each lazy `AgentSession`, call `refresh_sidebar_metadata(new_sess, name_lookup=(lambda p: _sn.name_for(p) if _sn else ""))` before storing it in `self.sessions`.

Use this shape:

```python
            new_sess = AgentSession(
                agent_id=sid,
                name=name,
                status="history",
                lazy_history_path=path,
                lazy_history_mtime=mtime,
                lazy_history_preview=(first or "（无法预览）").replace("\n", " ").strip(),
                lazy_history_rounds=int(n or 0),
            )
            refresh_sidebar_metadata(new_sess, name_lookup=(lambda p: _sn.name_for(p) if _sn else ""))
            self.sessions[sid] = new_sess
```

- [ ] **Step 3: Reuse naming helper in `/continue` picker**

In `_cmd_continue()`, replace the `tag` label construction with:

```python
            nm = _sn.name_for(path) if _sn else ""
            title = sidebar_display_name(path, nm, first, mtime)
            preview = (first or "（无法预览）").replace("\n", " ").strip()[:50]
            text = title if title != preview else preview
            choices.append((f"{_short_age(mtime)} · {n}轮 · {text}", path))
```

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python -m unittest tests.test_tuiapp_v2_sidebar -v`

Expected: PASS.

## Task 4: Activity Updates and Cache Invalidation

**Files:**
- Modify: `frontends/tuiapp_v2.py` around session creation, restore, rename, submit, stream completion, and sidebar refresh
- Test: `tests/test_tuiapp_v2_sidebar.py`

- [ ] **Step 1: Update metadata at lifecycle points**

Add this method on `GenericAgentTUI` near `_refresh_sidebar()`:

```python
    def _touch_session_activity(self, sess: AgentSession, when: Optional[float] = None) -> None:
        sess.last_activity_at = when or time.time()
        sess.sidebar_meta_sig = ()
```

Call it in these places:

```python
# add_session(), after creating sess and before storing/refreshing:
        self._touch_session_activity(sess)

# submit_user_message(), before self._refresh_all():
        self._touch_session_activity(sess)

# _on_stream(), inside if done after status/current_display_queue updates:
            self._touch_session_activity(s)

# _restore_session_from_path() _finish(), after sess.status = "idle":
            self._touch_session_activity(sess)

# _cmd_rename(), after self.current.name = name:
        self._touch_session_activity(self.current)
```

- [ ] **Step 2: Refresh metadata before painting the sidebar**

Change `_refresh_sidebar()` to refresh each session before rendering:

```python
    def _refresh_sidebar(self):
        if not self.is_mounted: return
        for sess in self.sessions.values():
            refresh_sidebar_metadata(sess)
        self.query_one("#sidebar-content", Static).update(render_sidebar(self.sessions, self.current_id))
```

- [ ] **Step 3: Run focused tests**

Run: `python -m unittest tests.test_tuiapp_v2_sidebar -v`

Expected: PASS.

## Task 5: Verification and Final Cleanup

**Files:**
- Modify only if verification reveals a defect: `frontends/tuiapp_v2.py`, `tests/test_tuiapp_v2_sidebar.py`

- [ ] **Step 1: Run sidebar tests**

Run: `python -m unittest tests.test_tuiapp_v2_sidebar -v`

Expected: all tests pass.

- [ ] **Step 2: Run existing Python tests**

Run: `python -m unittest tests.test_agentmain_llm_selection -v`

Expected: all tests pass.

- [ ] **Step 3: Compile touched Python files**

Run: `python -m compileall frontends/tuiapp_v2.py tests/test_tuiapp_v2_sidebar.py`

Expected: command exits 0 with no syntax errors.

- [ ] **Step 4: Inspect diff for scope**

Run: `git diff -- frontends/tuiapp_v2.py tests/test_tuiapp_v2_sidebar.py docs/superpowers/plans/2026-06-04-tuiapp-v2-history-sidebar.md`

Expected: diff only contains sidebar metadata, rendering, tests, and this plan.

- [ ] **Step 5: Commit implementation**

Run:

```bash
git add frontends/tuiapp_v2.py tests/test_tuiapp_v2_sidebar.py docs/superpowers/plans/2026-06-04-tuiapp-v2-history-sidebar.md
git commit -m "feat: improve tui v2 history sidebar"
```

Expected: commit succeeds without staging unrelated `agentmain.py`, `docs/ctf/`, or `tools/` changes.

## Self-Review

- Spec coverage: Task 2 covers naming and cached metadata; Task 3 covers compact style and `/continue` labels; Task 4 covers activity ordering; Task 5 covers verification.
- Placeholder scan: no deferred implementation markers are present.
- Type consistency: helper names used by tests match helper names defined in implementation steps: `sidebar_ordered_sessions`, `sidebar_display_name`, and `refresh_sidebar_metadata`.
