import pathlib
import sys
import tempfile
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

import desktop_bridge


def test_role_profiles_crud_updates_live_session_and_stays_under_ga_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "repo"
        root.mkdir()
        original_root = desktop_bridge.manager.ga_root
        original_sessions = desktop_bridge.manager.sessions
        original_sessions_dir = desktop_bridge.manager._sessions_dir
        desktop_bridge.manager.ga_root = str(root)
        desktop_bridge.manager.sessions = {}
        desktop_bridge.manager._sessions_dir = root / "temp" / "desktop_sessions"
        try:
            prompt = "You are a release manager."
            created = desktop_bridge.manager.save_role_profile("release_manager", prompt, create=True)
            profile_path = root / "assets" / "roles" / "release_manager.md"
            assert profile_path.read_text(encoding="utf-8") == prompt
            assert created["name"] == "release_manager"
            assert [p["name"] for p in desktop_bridge.manager.list_role_profiles()] == ["release_manager"]
            assert desktop_bridge.manager.get_role_profile("RELEASE_MANAGER")["content"] == prompt

            agent = SimpleNamespace(
                extra_sys_prompts=[],
                history=["old"],
                llmclient=SimpleNamespace(backend=SimpleNamespace(history=[{"role": "user"}]), last_tools="tools"),
                llmclients=[],
                handler=SimpleNamespace(),
            )
            agent.llmclients = [agent.llmclient]
            session = desktop_bridge.Session(id="sess-role", agent=agent, role_name=None)
            desktop_bridge.manager.sessions[session.id] = session

            applied = desktop_bridge.manager.set_session_role(session.id, "release_manager", clear_context=True)
            assert applied["roleName"] == "release_manager"
            assert session.role_name == "release_manager"
            assert agent.history == []
            assert agent.llmclient.backend.history == []
            assert getattr(agent, "_ga_role_profile_name") == "release_manager"
            assert prompt in agent.extra_sys_prompts

            revised = "You manage releases with explicit rollback steps."
            saved = desktop_bridge.manager.save_role_profile("release_manager", revised, create=False)
            assert saved["sessionsUpdated"] == 1
            assert revised in agent.extra_sys_prompts
            assert prompt not in agent.extra_sys_prompts

            removed = desktop_bridge.manager.delete_role_profile("release_manager")
            assert removed["sessionsCleared"] == 1
            assert session.role_name is None
            assert getattr(agent, "_ga_role_profile_name") is None
            assert not profile_path.exists()
        finally:
            desktop_bridge.manager.ga_root = original_root
            desktop_bridge.manager.sessions = original_sessions
            desktop_bridge.manager._sessions_dir = original_sessions_dir


def test_role_profile_rejects_traversal_and_invalid_names():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "repo"
        root.mkdir()
        original_root = desktop_bridge.manager.ga_root
        desktop_bridge.manager.ga_root = str(root)
        try:
            for name in ("../outside", "role/name", "role:name", "", "x" * 65):
                try:
                    desktop_bridge.manager.save_role_profile(name, "prompt", create=True)
                except ValueError:
                    continue
                raise AssertionError(f"invalid role name accepted: {name!r}")
            assert not (root / "assets" / "roles").exists()
        finally:
            desktop_bridge.manager.ga_root = original_root


def test_role_command_state_syncs_back_to_the_desktop_session():
    session = desktop_bridge.Session(id="sess-role-sync", role_name="engineer")
    agent = SimpleNamespace(_ga_role_profile_name="reviewer")

    desktop_bridge.manager._sync_session_role_from_agent(session, agent)
    assert session.role_name == "reviewer"

    agent._ga_role_profile_name = None
    desktop_bridge.manager._sync_session_role_from_agent(session, agent)
    assert session.role_name is None


def test_role_profile_changes_reject_running_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "repo"
        root.mkdir()
        original_root = desktop_bridge.manager.ga_root
        original_sessions = desktop_bridge.manager.sessions
        original_sessions_dir = desktop_bridge.manager._sessions_dir
        desktop_bridge.manager.ga_root = str(root)
        desktop_bridge.manager.sessions = {}
        desktop_bridge.manager._sessions_dir = root / "temp" / "desktop_sessions"
        try:
            desktop_bridge.manager.save_role_profile("active", "Keep the current role.", create=True)
            session = desktop_bridge.Session(id="sess-running-role", role_name="active", status="running")
            desktop_bridge.manager.sessions[session.id] = session

            for operation in (
                lambda: desktop_bridge.manager.save_role_profile("active", "Changed.", create=False),
                lambda: desktop_bridge.manager.delete_role_profile("active"),
            ):
                try:
                    operation()
                except desktop_bridge.RoleProfileBusyError:
                    continue
                raise AssertionError("running session allowed a role profile mutation")

            profile_path = root / "assets" / "roles" / "active.md"
            assert profile_path.read_text(encoding="utf-8") == "Keep the current role."
        finally:
            desktop_bridge.manager.ga_root = original_root
            desktop_bridge.manager.sessions = original_sessions
            desktop_bridge.manager._sessions_dir = original_sessions_dir


def test_role_management_cors_only_allows_bridge_origins():
    external = SimpleNamespace(headers={"Origin": "https://example.invalid"})
    loopback = SimpleNamespace(headers={"Origin": "http://127.0.0.1:14168"})
    local = SimpleNamespace(headers={"Origin": "http://localhost:14168"})

    assert not desktop_bridge._trusted_local_origin(external)
    assert desktop_bridge.cors_headers(external) == {}
    assert desktop_bridge._trusted_local_origin(loopback)
    assert desktop_bridge.cors_headers(loopback)["Access-Control-Allow-Origin"] == "http://127.0.0.1:14168"
    assert desktop_bridge._trusted_local_origin(local)


def test_role_context_clear_keeps_frontend_message_cursor():
    app = (ROOT / "frontends" / "desktop" / "static" / "app.js").read_text(encoding="utf-8")
    start = app.index("async function setActiveSessionRole")
    end = app.index("async function openRoleEditor", start)
    clear_block = app[start:end]

    assert "r.lastId = Math.max(r.lastId" in clear_block
    assert "r.seen.clear()" not in clear_block

def test_bridge_never_binds_a_public_interface():
    original = desktop_bridge.os.environ.get("BRIDGE_HOST")
    try:
        desktop_bridge.os.environ["BRIDGE_HOST"] = "0.0.0.0"
        assert desktop_bridge._bridge_bind_host() == "127.0.0.1"
    finally:
        if original is None:
            desktop_bridge.os.environ.pop("BRIDGE_HOST", None)
        else:
            desktop_bridge.os.environ["BRIDGE_HOST"] = original