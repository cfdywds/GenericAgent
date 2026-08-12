"""Per-session role profiles loaded from ``assets/roles/*.md``."""
from pathlib import Path
import re

import plugins.hooks as hooks


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ROLES_DIR = _PROJECT_ROOT / "assets" / "roles"
_ROLE_PROMPT_ATTR = "_ga_role_profile_prompt"
_ROLE_NAME_ATTR = "_ga_role_profile_name"
_CLEAR_FLAGS = {"--clear", "-c", "clear"}
_ROLE_COMMAND_RE = re.compile(r"^/role(?:\s+(.*?))?\s*$", re.IGNORECASE)


def _profile_paths():
    """Return direct Markdown profiles keyed by a case-insensitive role name."""
    try:
        paths = [path for path in _ROLES_DIR.iterdir()
                 if path.is_file() and path.suffix.lower() == ".md"]
    except OSError:
        return {}
    return {path.stem.casefold(): path
            for path in sorted(paths, key=lambda path: path.name.casefold())}


def list_profiles():
    """Return display names for the available profiles."""
    return [path.stem for path in _profile_paths().values()]


def read_profile(name):
    """Return a role's display name and prompt, or ``None`` when unavailable."""
    path = _profile_paths().get((name or "").casefold())
    if path is None:
        return None
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not prompt:
        return None
    return path.stem, prompt


def _extra_prompts(agent):
    prompts = getattr(agent, "extra_sys_prompts", None)
    if isinstance(prompts, list):
        return prompts
    prompts = list(prompts or [])
    agent.extra_sys_prompts = prompts
    return prompts


def _replace_role_prompt(agent, name=None, prompt=None):
    """Replace only this plugin's prompt and retain other session additions."""
    prompts = _extra_prompts(agent)
    previous = getattr(agent, _ROLE_PROMPT_ATTR, None)
    if previous:
        for index, item in enumerate(prompts):
            if item is previous:
                del prompts[index]
                break
    if prompt:
        prompts.append(prompt)
    setattr(agent, _ROLE_PROMPT_ATTR, prompt)
    setattr(agent, _ROLE_NAME_ATTR, name)


def activate_profile(agent, name):
    """Load and attach a profile to one agent instance.

    ``None`` is returned for an unknown or empty profile so non-command callers
    can validate a persisted name without parsing a user-facing message.
    """
    profile = read_profile(name)
    if profile is None:
        return None
    display_name, prompt = profile
    attach_profile(agent, display_name, prompt)
    return display_name


def attach_profile(agent, name, prompt):
    """Attach already-loaded role content to one agent instance."""
    _replace_role_prompt(agent, name, prompt)


def deactivate_profile(agent):
    """Remove this plugin's role prompt from one agent instance."""
    _replace_role_prompt(agent)


def _clear_context(agent):
    """Clear current conversation state without rotating the session log or UI."""
    if hasattr(agent, "history"):
        agent.history = []
    clients = list(getattr(agent, "llmclients", []) or [])
    current = getattr(agent, "llmclient", None)
    if current is not None and all(current is not client for client in clients):
        clients.append(current)
    for client in clients:
        backend = getattr(client, "backend", None)
        if backend is not None and hasattr(backend, "history"):
            backend.history = []
        if hasattr(client, "last_tools"):
            client.last_tools = ""
    if hasattr(agent, "handler"):
        agent.handler = None


def _usage():
    return "用法: /role list | /role <角色名> [--clear] | /role off [--clear]"


def _list_message(agent):
    names = list_profiles()
    current = getattr(agent, _ROLE_NAME_ATTR, None) or "off"
    lines = ["可用角色:"]
    lines.extend(f"- {name}" for name in names)
    lines.append(f"当前角色: {current}")
    lines.append(_usage())
    return "\n".join(lines)


def handle_role_command(agent, raw_query):
    """Return a command result, or ``None`` when the query is unrelated."""
    match = _ROLE_COMMAND_RE.match(raw_query or "")
    if not match:
        return None
    tokens = (match.group(1) or "").split()
    if not tokens or tokens[0].casefold() == "list":
        return _list_message(agent) if len(tokens) <= 1 else _usage()

    clear_context = False
    if tokens and tokens[-1].casefold() in _CLEAR_FLAGS:
        clear_context = True
        tokens.pop()
    if len(tokens) != 1:
        return _usage()
    if getattr(agent, "is_running", False):
        return "当前任务正在运行；请先停止任务后再切换角色。"

    requested = tokens[0]
    if requested.casefold() == "off":
        deactivate_profile(agent)
        if clear_context:
            _clear_context(agent)
        suffix = "，已清空旧模型上下文（界面历史保留）" if clear_context else ""
        return f"已关闭角色提示词{suffix}。"

    selected = activate_profile(agent, requested)
    if selected is None:
        return f"未找到角色: {requested}\n{_list_message(agent)}"
    if clear_context:
        _clear_context(agent)
    suffix = "，已清空旧模型上下文（界面历史保留）" if clear_context else ""
    return f"已切换角色: {selected}{suffix}。"


@hooks.register("slash_command")
def _handle_slash_command(ctx):
    message = handle_role_command(ctx.get("agent"), ctx.get("raw_query"))
    if message is not None:
        ctx["handled"] = True
        ctx["message"] = message
    return ctx
