import importlib
import queue
import threading
from types import SimpleNamespace
from unittest import mock

import agentmain
from plugins import hooks
from plugins import role_profiles


def _agent(*, prompts=None, history=None, backend_history=None):
    backend = SimpleNamespace(history=list(backend_history or []))
    client = SimpleNamespace(backend=backend, last_tools="tool cache")
    return SimpleNamespace(
        extra_sys_prompts=list(prompts or ["other session prompt"]),
        history=list(history or []),
        llmclient=client,
        llmclients=[client],
        handler=SimpleNamespace(),
        is_running=False,
    )


def test_switch_replaces_only_role_owned_prompt_and_off_preserves_others():
    engineer_prompt = (role_profiles._ROLES_DIR / "engineer.md").read_text(encoding="utf-8").strip()
    agent = _agent(prompts=["other session prompt", engineer_prompt])

    assert "已切换角色: engineer" in role_profiles.handle_role_command(agent, "/role engineer")
    assert agent.extra_sys_prompts[0:2] == ["other session prompt", engineer_prompt]
    assert len(agent.extra_sys_prompts) == 3

    assert "已切换角色: reviewer" in role_profiles.handle_role_command(agent, "/role reviewer")
    reviewer_prompt = (role_profiles._ROLES_DIR / "reviewer.md").read_text(encoding="utf-8").strip()
    assert agent.extra_sys_prompts == ["other session prompt", engineer_prompt, reviewer_prompt]

    assert "已关闭角色提示词" in role_profiles.handle_role_command(agent, "/role off")
    assert agent.extra_sys_prompts == ["other session prompt", engineer_prompt]


def test_role_clear_resets_session_context_but_keeps_the_selected_profile():
    agent = _agent(history=["summary"], backend_history=[{"role": "user", "content": "old"}])

    result = role_profiles.handle_role_command(agent, "/role analyst --clear")

    assert "已清空旧模型上下文" in result
    assert agent.history == []
    assert agent.llmclient.backend.history == []
    assert agent.llmclient.last_tools == ""
    assert agent.handler is None
    assert getattr(agent, "_ga_role_profile_name") == "analyst"
    assert len(agent.extra_sys_prompts) == 2


def test_list_is_loaded_from_role_assets():
    profiles = role_profiles.list_profiles()
    assert {"analyst", "engineer", "reviewer", "writer"}.issubset(profiles)
    assert profiles == sorted(profiles, key=str.casefold)


def test_agent_core_consumes_auto_loaded_role_command_and_uses_session_prompt():
    hooks.unregister("slash_command", role_profiles._handle_slash_command)
    role_profiles_module = importlib.reload(role_profiles)
    agent = object.__new__(agentmain.GenericAgent)
    agent.task_queue = queue.Queue()
    agent.history = []
    agent.handler = None
    agent.stop_sig = False
    agent.task_dir = None
    agent.is_running = False
    agent.inc_out = False
    agent.verbose = True
    agent.peer_hint = False
    agent.force_non_stream = False
    agent.extra_sys_prompts = ["other session prompt"]
    agent.log_path = ""
    agent.all_outputs = []
    agent.llmclient = SimpleNamespace(backend=SimpleNamespace(extra_sys_prompt="", history=[]), last_tools="")
    agent.llmclients = [agent.llmclient]
    output = queue.Queue()
    agent.task_queue.put({"query": "/role reviewer", "source": "test", "images": [], "output": output})
    agent.task_queue.put({"query": "ordinary task", "source": "test", "images": [], "output": output})
    agent.task_queue.put("stop")
    handler = SimpleNamespace(working={}, history_info=[], code_stop_signal=[])
    captured = []

    def runner(_client, system_prompt, *_args, **_kwargs):
        captured.append(system_prompt)
        yield {"turn": 1}
        yield "done"

    with (mock.patch.object(agentmain, "GenericAgentHandler", return_value=handler),
          mock.patch.object(agentmain, "get_system_prompt", return_value="base system\n"),
          mock.patch.object(agentmain, "agent_runner_loop", side_effect=runner)):
        thread = threading.Thread(target=agent.run)
        thread.start()
        role_result = output.get(timeout=2)
        task_result = output.get(timeout=2)
        thread.join(timeout=2)

    assert not thread.is_alive()
    assert "已切换角色: reviewer" in role_result["done"]
    assert task_result["done"] == "done"
    reviewer_prompt = (role_profiles_module._ROLES_DIR / "reviewer.md").read_text(encoding="utf-8").strip()
    assert captured == ["base system\nother session prompt\n" + reviewer_prompt]
