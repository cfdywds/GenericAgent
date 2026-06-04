# TUI v2 History Sidebar Design

## Context

`frontends/tuiapp_v2.py` loads historical `temp/model_responses/model_responses_*.txt` logs into the session sidebar as lazy `AgentSession` entries. The current sidebar mostly preserves insertion order from `continue_cmd.list_sessions()`, uses filename-derived fallback names such as `history-<pid>`, and recomputes preview text by scanning session history during render. The result is harder to scan, older restored sessions do not naturally rise, and large histories make repeated sidebar rendering more expensive than necessary.

## Goals

- Improve the history session sidebar sorting rule.
- Improve sidebar and `/continue` display naming for historical sessions.
- Reduce repeated sidebar rendering work for large histories.
- Adjust the sidebar style so session rows are denser and easier to scan.

## Non-Goals

- Do not add pinned/favorite sessions or new persistent state beyond existing `session_names`.
- Do not rewrite `continue_cmd` scanning or session restoration behavior.
- Do not restructure the whole TUI file; keep changes scoped to sidebar/session metadata helpers.

## Sorting

Sidebar order will be derived from a stable sort key rather than raw dict insertion order:

1. Current session first.
2. Running sessions before idle/history sessions.
3. Remaining sessions by descending activity time.
4. Ties by descending numeric session id so newer in-memory entries appear first.

Activity time sources:

- Lazy historical sessions use `lazy_history_mtime` from `continue_cmd.list_sessions()`.
- Materialized sessions use the current agent log file `mtime` when available.
- New sessions without a readable log use a `created_at`/`last_activity_at` timestamp kept on `AgentSession`.
- Submitting a user message, finishing a stream, restoring a history session, and renaming a session update the relevant metadata so the sidebar order reflects recent work.

## Naming

Display names will be computed through one helper so the sidebar and `/continue` picker follow the same precedence:

1. Existing persistent `/rename` value from `session_names.name_for(path)`.
2. A short title from the most recent real user prompt or lazy preview text.
3. A readable fallback based on the log timestamp, such as `history 06-04 20:53`.
4. Final fallback `history` when no timestamp is available.

The internal `AgentSession.name` remains usable for commands and existing behavior, but rendering uses the computed display name. This avoids exposing raw `model_responses_<pid>` filenames for unnamed historical sessions.

## Performance

`AgentSession` will carry lightweight sidebar metadata fields:

- `sidebar_title`
- `sidebar_preview`
- `sidebar_summary`
- `sidebar_activity_at`
- `sidebar_meta_sig`

Rendering will consume these fields instead of scanning `backend.history` on every sidebar refresh. A refresh helper will recompute metadata only when the session signature changes. For lazy historical sessions, metadata is populated once from the `continue_cmd.list_sessions()` tuple. For live sessions, the signature can include history length, status, lazy path, stored name, and log mtime.

This keeps startup lazy and keeps sidebar refresh cost proportional to visible sessions rather than full conversation length.

## Sidebar Style

The sidebar row layout becomes compact and consistent:

- Header: `SESSIONS` plus count.
- First row per session: status glyph, display name, right-aligned status/round count, short age.
- Second row per session: preview or summary text, truncated with ellipsis.
- Current session keeps the selected background.
- Running sessions use the active green glyph; lazy history sessions use muted styling.
- Empty spacer rows are reduced so more historical sessions fit in the same terminal height.

## Error Handling

- If `session_names` import or lookup fails, rendering falls back to generated titles.
- If a log file cannot be statted, activity time falls back to stored metadata or zero.
- If history content cannot be inspected, the preview remains empty rather than breaking sidebar rendering.

## Testing

Add focused tests for pure helper behavior:

- Sorting puts the current session first, running sessions before idle/history, and newer activity before older activity.
- Naming prefers persisted names, then preview-derived titles, then timestamp fallback.
- Sidebar metadata for lazy sessions is prefilled without requiring an agent object.
- Rendering includes compact status/count/age information and avoids the old raw filename fallback.

Use Python unit tests that import `frontends.tuiapp_v2` with lightweight session objects. Avoid launching the Textual app in tests.
