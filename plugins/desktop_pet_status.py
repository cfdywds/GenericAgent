"""Desktop pet status bridge.

This plugin is intentionally best-effort: the pet is an optional local UI, so
failed requests must never slow down or break the agent loop.
"""
import json
import os
import threading
import urllib.parse
import urllib.request

import plugins.hooks as hooks


PET_PORT = int(os.environ.get("GA_DESKTOP_PET_PORT", "41983"))
PET_URL = os.environ.get("GA_DESKTOP_PET_URL", f"http://127.0.0.1:{PET_PORT}/")
ENABLED = os.environ.get("GA_DESKTOP_PET_STATUS", "1").strip().lower() not in {"0", "false", "no", "off"}
TIMEOUT = float(os.environ.get("GA_DESKTOP_PET_TIMEOUT", "0.25"))
LANGUAGE_ACTION = "thinking"
LANGUAGE_MESSAGE = "思考中"

TOOL_ACTIONS = {
    "web_search": "search",
    "web_scan": "browse",
    "web_execute_js": "browse",
    "code_run": "code",
    "file_read": "read",
    "file_write": "write",
    "file_patch": "write",
    "ask_user": "ask",
    "update_working_checkpoint": "memory",
    "start_long_term_update": "memory",
    "restore_quarantine": "fix",
}

_CONTINUE_RESULTS = {"MAX_TURNS_EXCEEDED"}
_CANCELLED_RESULTS = {"CANCELLED", "CANCELED", "ABORTED", "INTERRUPTED", "USER_ABORT"}
_ERROR_RESULTS = {"ERROR", "FAILED", "FAILURE", "EXCEPTION"}


def _short(value, limit=18):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_message(tool_name, args):
    args = args or {}
    if tool_name == "web_search":
        query = _short(args.get("query") or args.get("q") or "")
        return f"搜索 {query}" if query else "搜索中"
    if tool_name in {"web_scan", "web_execute_js"}:
        return "浏览网页"
    if tool_name == "code_run":
        return "运行代码"
    if tool_name == "file_read":
        path = _short(args.get("path") or "")
        return f"读取 {path}" if path else "读取文件"
    if tool_name in {"file_write", "file_patch"}:
        path = _short(args.get("path") or "")
        return f"写入 {path}" if path else "写入文件"
    if tool_name == "ask_user":
        return "等待确认"
    if tool_name == "update_working_checkpoint":
        return "写入记忆"
    if tool_name == "start_long_term_update":
        return "整理记忆"
    if tool_name == "restore_quarantine":
        return "恢复中"
    return _short(tool_name.replace("_", " "))


def _send(action, msg=""):
    if not ENABLED:
        return
    query = {"action": action}
    if msg:
        query["msg"] = msg
    url = PET_URL + "?" + urllib.parse.urlencode(query)

    def _request():
        try:
            urllib.request.urlopen(url, timeout=TIMEOUT).read(16)
        except Exception:
            pass

    threading.Thread(target=_request, daemon=True).start()


def _send_later(delay, action, msg=""):
    timer = threading.Timer(delay, lambda: _send(action, msg))
    timer.daemon = True
    timer.start()


def _outcome_status(ret):
    data = getattr(ret, "data", None)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {"text": data}
    if isinstance(data, dict):
        status = str(data.get("status") or data.get("result") or "").lower()
        if status in {"error", "failed", "blocked", "cancelled", "canceled"}:
            return "error"
    return "success"


def _agent_done_action(result, maxed=False):
    if maxed:
        return "ask"
    if isinstance(result, dict):
        code = str(result.get("result") or result.get("status") or "").upper()
    else:
        code = str(result or "").upper()
    if code in _CONTINUE_RESULTS:
        return "ask"
    if code in _CANCELLED_RESULTS:
        return "cancelled"
    if code in _ERROR_RESULTS:
        return "error"
    return "done"


def _agent_done_message(action):
    return {
        "ask": "需要继续",
        "cancelled": "已取消",
        "error": "出错了",
        "done": "完成",
    }.get(action, "完成")


@hooks.register("llm_before")
def _on_llm_before(ctx):
    _send(LANGUAGE_ACTION, LANGUAGE_MESSAGE)


@hooks.register("tool_before")
def _on_tool_before(ctx):
    tool_name = ctx.get("tool_name")
    action = TOOL_ACTIONS.get(tool_name)
    if action:
        _send(action, _tool_message(tool_name, ctx.get("args") or {}))


@hooks.register("tool_after")
def _on_tool_after(ctx):
    tool_name = ctx.get("tool_name")
    if tool_name not in TOOL_ACTIONS:
        return
    ret = ctx.get("ret")
    status = _outcome_status(ret)
    _send(status, "完成" if status == "success" else "出错了")
    if getattr(ret, "next_prompt", None) and not getattr(ret, "should_exit", False):
        _send_later(1.2, LANGUAGE_ACTION, LANGUAGE_MESSAGE)


@hooks.register("agent_after")
def _on_agent_after(ctx):
    result = ctx.get("exit_reason") or {}
    handler = ctx.get("handler")
    turn = int(ctx.get("turn") or 0)
    max_turns = int(getattr(handler, "max_turns", 0) or 0)
    maxed = (not result) and max_turns and turn >= max_turns
    action = _agent_done_action(result, maxed=maxed)
    _send(action, _agent_done_message(action))
    _send_later(1.8, "idle")