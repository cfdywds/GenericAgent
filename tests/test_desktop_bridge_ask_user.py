import io
import pathlib
import queue
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

import desktop_bridge


ASK_CONTEXT = {
    "exit_reason": {
        "result": "EXITED",
        "data": {
            "status": "INTERRUPT",
            "intent": "HUMAN_INTERVENTION",
            "data": {"question": "请确认是否继续", "candidates": ["继续", "取消"]},
        },
    },
}


class FakeAgent:
    inc_out = True

    def __init__(self, *, ask_context=None, done="", exit_reason=None, error=None, transcript=None, outputs=None):
        self._turn_end_hooks = {}
        self.ask_context = ask_context
        self.done = done
        self.exit_reason = exit_reason
        self.error = error
        self.transcript = transcript
        self.outputs = list(outputs or [])
        self.prompts = []
        self.histories_at_put_task = []
        self.llmclient = SimpleNamespace(backend=SimpleNamespace(history=[]))

    def put_task(self, prompt, images=None):
        self.prompts.append(prompt)
        self.histories_at_put_task.append(self.llmclient.backend.history)
        if self.ask_context:
            for hook in list(self._turn_end_hooks.values()):
                hook(self.ask_context)
        display_queue = queue.Queue()
        item = {"done": self.done, "outputs": self.outputs}
        if self.exit_reason is not None:
            item["exit_reason"] = self.exit_reason
        if self.error is not None:
            item["error"] = self.error
        if self.transcript is not None:
            item["transcript"] = self.transcript
        display_queue.put(item)
        return display_queue


def manager_for_test(root):
    manager = object.__new__(desktop_bridge.AgentManager)
    manager.lock = threading.RLock()
    manager.ga_root = str(root)
    manager.config = {}
    manager.sessions = {}
    manager.active_session_id = None
    manager.bridge_token = "test-token"
    manager._sessions_dir = root / "sessions"
    manager._sessions_file = root / "desktop_sessions.json"
    return manager


class DesktopBridgeAskUserTests(unittest.TestCase):
    def test_extract_ask_user_interrupt(self):
        self.assertEqual(
            desktop_bridge.extract_ask_user_interrupt(ASK_CONTEXT),
            {"question": "请确认是否继续", "candidates": ["继续", "取消"]},
        )
        self.assertIsNone(desktop_bridge.extract_ask_user_interrupt({"exit_reason": {"result": "CURRENT_TASK_DONE"}}))

    def test_ask_user_pauses_session_without_empty_response_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            agent = FakeAgent(ask_context=ASK_CONTEXT)
            sess = desktop_bridge.Session(id="sess-ask", cwd=tmp, agent=agent,
                                          status="running", active_turn_id="turn-1")
            manager.sessions[sess.id] = sess

            with mock.patch.object(desktop_bridge, "emit_session_state") as emit:
                manager.run_agent_turn(sess, "开始任务", turn_id="turn-1")

            self.assertEqual(sess.status, "awaiting_input")
            self.assertEqual(sess.pending_input["question"], "请确认是否继续")
            self.assertEqual(sess.messages[-1]["role"], "assistant")
            self.assertEqual(sess.messages[-1]["ask_user"]["candidates"], ["继续", "取消"])
            self.assertEqual(sess.last_error, "")
            emit.assert_called_with(sess, "awaiting_input")
            payload = manager.messages(sess.id)
            self.assertEqual(payload["pendingInput"]["question"], "请确认是否继续")

    def test_ask_user_permitted_image_is_copied_to_session_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            qr_path = root / "temp" / "wx_qr.png"
            qr_path.parent.mkdir(parents=True)
            qr_path.write_bytes(b"fake-png")
            manager = manager_for_test(root)
            ask_context = {
                "exit_reason": {
                    "result": "EXITED",
                    "data": {
                        "status": "INTERRUPT",
                        "intent": "HUMAN_INTERVENTION",
                        "data": {"question": f"请扫描二维码：{qr_path}", "candidates": []},
                    },
                },
            }
            sess = desktop_bridge.Session(id="sess-qr", cwd=tmp, agent=FakeAgent(ask_context=ask_context),
                                          status="running", active_turn_id="turn-1")
            manager.sessions[sess.id] = sess

            with (mock.patch.object(desktop_bridge, "_WEB_UPLOAD_DIR", root / "uploads"),
                  mock.patch.object(desktop_bridge, "emit_session_state")):
                manager.run_agent_turn(sess, "登录微信", turn_id="turn-1")

            images = sess.pending_input["images"]
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0]["name"], "wx_qr.png")
            copied = pathlib.Path(images[0]["path"])
            self.assertTrue(copied.is_relative_to(root / "uploads" / "sess-qr"))
            self.assertEqual(copied.read_bytes(), b"fake-png")

    def test_ask_user_does_not_attach_image_outside_permitted_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            image_path = root / "private.png"
            image_path.write_bytes(b"not-public")
            payload = {"question": f"不要展示这个文件：{image_path}", "candidates": []}
            attached = desktop_bridge.attach_ask_user_images(payload, root, root / "uploads" / "sess")
            self.assertNotIn("images", attached)

    def test_ask_user_does_not_attach_a_permitted_path_embedded_in_a_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            image_path = root / "temp" / "qr.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"fake-png")
            payload = {"question": f"https://example.com/?file={image_path}", "candidates": []}
            attached = desktop_bridge.attach_ask_user_images(payload, root, root / "uploads" / "sess")
            self.assertNotIn("images", attached)

    def test_loading_existing_pending_input_adds_permitted_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            qr_path = root / "temp" / "wx_qr.png"
            qr_path.parent.mkdir(parents=True)
            qr_path.write_bytes(b"fake-png")
            manager = manager_for_test(root)
            item = {
                "id": "sess-existing-qr",
                "messages": [],
                "pending_input": {"question": f"请扫描二维码：{qr_path}", "candidates": []},
            }

            with mock.patch.object(desktop_bridge, "_WEB_UPLOAD_DIR", root / "uploads"):
                sess = manager._session_from_item(item)

            self.assertEqual(sess.pending_input["images"][0]["name"], "wx_qr.png")
            self.assertEqual(sess.status, "awaiting_input")

    def test_reloaded_pending_input_restores_history_before_resuming(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manager = manager_for_test(root)
            history = [{"role": "assistant", "content": [{"type": "text", "text": "请确认是否继续"}]}]
            sess = manager._session_from_item({
                "id": "sess-reloaded",
                "messages": [{"id": 1, "role": "assistant", "content": "请确认是否继续"}],
                "msg_seq": 1,
                "pending_input": {"question": "请确认是否继续", "candidates": ["继续"]},
                "llm_history": history,
            })
            resumed = FakeAgent(done="已继续执行")
            manager.sessions[sess.id] = sess

            with (mock.patch.object(manager, "make_agent", return_value=resumed),
                  mock.patch.object(desktop_bridge, "emit_session_state")):
                manager.submit_prompt(sess.id, "继续")
                sess.thread.join(timeout=2)

            self.assertFalse(sess.thread.is_alive())
            self.assertEqual(resumed.prompts, ["继续"])
            self.assertEqual(resumed.histories_at_put_task, [history])
            self.assertEqual(sess.status, "idle")

    def test_new_session_does_not_restore_the_prompt_being_submitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            sess = desktop_bridge.Session(id="sess-new", cwd=tmp)
            manager.sessions[sess.id] = sess
            agent = FakeAgent(done="已继续执行")

            with (mock.patch.object(manager, "make_agent", return_value=agent),
                  mock.patch.object(desktop_bridge, "emit_session_state")):
                manager.submit_prompt(sess.id, "第一条消息")
                sess.thread.join(timeout=2)

            self.assertFalse(sess.thread.is_alive())
            self.assertEqual(agent.prompts, ["第一条消息"])
            self.assertEqual(agent.histories_at_put_task, [[]])

    def test_restore_context_keeps_pending_session_awaiting_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            sess = desktop_bridge.Session(
                id="sess-restore", cwd=tmp, status="awaiting_input",
                pending_input={"question": "请确认是否继续", "candidates": ["继续"]},
            )
            manager.sessions[sess.id] = sess
            restored = FakeAgent()

            with mock.patch.object(manager, "make_agent", return_value=restored):
                manager.restore_context(sess.id)

            self.assertIs(sess.agent, restored)
            self.assertEqual(sess.status, "awaiting_input")

    def test_restore_and_submit_share_one_agent_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            sess = desktop_bridge.Session(
                id="sess-race", cwd=tmp, status="awaiting_input",
                pending_input={"question": "请确认是否继续", "candidates": ["继续"]},
            )
            manager.sessions[sess.id] = sess
            restored = FakeAgent(done="已继续执行")
            make_started = threading.Event()
            allow_make = threading.Event()

            def make_agent(_):
                make_started.set()
                self.assertTrue(allow_make.wait(timeout=2))
                return restored

            with (mock.patch.object(manager, "make_agent", side_effect=make_agent) as make,
                  mock.patch.object(desktop_bridge, "emit_session_state")):
                restore_thread = threading.Thread(target=manager.restore_context, args=(sess.id,))
                restore_thread.start()
                self.assertTrue(make_started.wait(timeout=2))
                submit_thread = threading.Thread(target=manager.submit_prompt, args=(sess.id, "继续"))
                submit_thread.start()
                allow_make.set()
                restore_thread.join(timeout=2)
                submit_thread.join(timeout=2)
                sess.thread.join(timeout=2)

            self.assertFalse(restore_thread.is_alive())
            self.assertFalse(submit_thread.is_alive())
            self.assertFalse(sess.thread.is_alive())
            self.assertEqual(make.call_count, 1)
            self.assertIs(sess.agent, restored)
            self.assertEqual(restored.prompts, ["继续"])

    def test_posix_absolute_image_paths_are_recognized(self):
        self.assertEqual(
            desktop_bridge._ASK_USER_IMAGE_PATH_RE.search("请扫描 /home/user/.wxbot/qr.png").group(0),
            "/home/user/.wxbot/qr.png",
        )

    def test_windows_lowercase_drive_image_paths_are_recognized(self):
        self.assertEqual(
            desktop_bridge._ASK_USER_IMAGE_PATH_RE.search(r"请扫描 d:\navy_code\GenericAgent\temp\qr.png").group(0),
            r"d:\navy_code\GenericAgent\temp\qr.png",
        )

    def test_answering_pending_input_resumes_the_same_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            agent = FakeAgent(done="已继续执行")
            sess = desktop_bridge.Session(
                id="sess-resume", cwd=tmp, agent=agent, status="awaiting_input",
                pending_input={"question": "请确认是否继续", "candidates": ["继续"]},
            )
            manager.sessions[sess.id] = sess

            with mock.patch.object(desktop_bridge, "emit_session_state"):
                manager.submit_prompt(sess.id, "继续")
                sess.thread.join(timeout=2)

            self.assertFalse(sess.thread.is_alive())
            self.assertEqual(agent.prompts, ["继续"])
            self.assertIsNone(sess.pending_input)
            self.assertEqual(sess.status, "idle")
            self.assertEqual(sess.messages[-1]["content"], "已继续执行")

    def test_empty_response_exit_is_resumable_and_keeps_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            transcript = "**LLM Running (Turn 3) ...**\n\n🛠️ Tool: `file_read`\n````text\n{}\n````\n`````\nresult\n`````"
            agent = FakeAgent(
                done=transcript,
                outputs=[transcript],
                exit_reason={"result": "EXITED", "data": {"reason": "EMPTY_RESPONSE_RETRY_EXHAUSTED", "attempts": 3}},
            )
            agent.llmclient.backend.history = [{"role": "assistant", "content": "tool context"}]
            sess = desktop_bridge.Session(id="sess-empty-response", cwd=tmp, agent=agent,
                                          status="running", active_turn_id="turn-1")
            manager.sessions[sess.id] = sess

            with mock.patch.object(desktop_bridge, "emit_session_state") as emit:
                manager.run_agent_turn(sess, "开始任务", turn_id="turn-1")

            self.assertEqual(sess.status, "idle")
            self.assertEqual(sess.last_error, "")
            self.assertEqual(sess.messages[-2]["role"], "assistant")
            self.assertEqual(sess.messages[-2]["content"], transcript)
            self.assertEqual(sess.messages[-1]["role"], "system")
            self.assertIn("连续 3 次", sess.messages[-1]["content"])
            self.assertEqual(sess.llm_history, agent.llmclient.backend.history)
            emit.assert_called_with(sess, "idle")

    def test_current_task_done_with_visible_text_remains_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            sess = desktop_bridge.Session(
                id="sess-complete", cwd=tmp,
                agent=FakeAgent(done="任务已完成", exit_reason={"result": "CURRENT_TASK_DONE", "data": {}}),
                status="running", active_turn_id="turn-1",
            )
            manager.sessions[sess.id] = sess

            with mock.patch.object(desktop_bridge, "emit_session_state"):
                manager.run_agent_turn(sess, "开始任务", turn_id="turn-1")

            self.assertEqual(sess.status, "idle")
            self.assertEqual(len(sess.messages), 1)
            self.assertEqual(sess.messages[-1]["role"], "assistant")
            self.assertEqual(sess.messages[-1]["content"], "任务已完成")

    def test_current_task_done_without_visible_text_is_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            sess = desktop_bridge.Session(
                id="sess-tool-only", cwd=tmp,
                agent=FakeAgent(exit_reason={"result": "CURRENT_TASK_DONE", "data": {}}),
                status="running", active_turn_id="turn-1",
            )
            manager.sessions[sess.id] = sess

            with mock.patch.object(desktop_bridge, "emit_session_state"):
                manager.run_agent_turn(sess, "开始任务", turn_id="turn-1")

            self.assertEqual(sess.status, "idle")
            self.assertEqual(sess.messages[-1]["role"], "system")
            self.assertIn("未生成面向用户的说明", sess.messages[-1]["content"])

    def test_backend_error_keeps_transcript_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            turn_one = "第一轮工具输出\n"
            turn_two = "第二轮工具输出\n"
            transcript = turn_one + turn_two
            agent = FakeAgent(
                done=transcript + "```\nprovider timeout\n```",
                transcript=transcript,
                error="provider timeout",
                outputs=[turn_one, turn_two],
            )
            agent.llmclient.backend.history = [{"role": "assistant", "content": "partial context"}]
            sess = desktop_bridge.Session(id="sess-backend-error", cwd=tmp, agent=agent,
                                          status="running", active_turn_id="turn-1")
            manager.sessions[sess.id] = sess

            with mock.patch.object(desktop_bridge, "emit_session_state") as emit:
                manager.run_agent_turn(sess, "开始任务", turn_id="turn-1")

            self.assertEqual(sess.status, "error")
            self.assertEqual(sess.messages[-2]["role"], "assistant")
            self.assertNotIn("provider timeout", sess.messages[-2]["content"])
            self.assertEqual(sess.messages[-2]["content"], transcript)
            self.assertEqual(sess.messages[-2]["turn_segs"], [turn_one, turn_two])
            self.assertEqual(sess.messages[-1]["role"], "error")
            self.assertIn("provider timeout", sess.messages[-1]["content"])
            self.assertEqual(sess.llm_history, agent.llmclient.backend.history)
            emit.assert_called_with(sess, "error")

    def test_non_final_exit_descriptions_cover_max_turns(self):
        message = desktop_bridge.describe_non_final_exit({"result": "MAX_TURNS_EXCEEDED"})
        self.assertIn("180", message)


    def test_empty_done_without_interrupt_remains_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = manager_for_test(pathlib.Path(tmp))
            sess = desktop_bridge.Session(id="sess-empty", cwd=tmp, agent=FakeAgent(),
                                          status="running", active_turn_id="turn-1")
            manager.sessions[sess.id] = sess

            with (mock.patch.object(desktop_bridge, "emit_session_state"),
                  mock.patch.object(desktop_bridge.sys, "stderr", new=io.StringIO())):
                manager.run_agent_turn(sess, "开始任务", turn_id="turn-1")

            self.assertEqual(sess.status, "error")
            self.assertEqual(sess.messages[-1]["role"], "error")


if __name__ == "__main__":
    unittest.main()
