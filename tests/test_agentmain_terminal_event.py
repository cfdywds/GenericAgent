import queue
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import agentmain


class StubHandler:
    def __init__(self):
        self.working = {}
        self.history_info = []
        self.code_stop_signal = []


def failing_runner():
    yield {"turn": 1}
    yield "已完成前半段"
    raise RuntimeError("provider timeout")


class AgentMainTerminalEventTests(unittest.TestCase):
    def test_backend_exception_keeps_legacy_done_and_structured_transcript(self):
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
        agent.extra_sys_prompts = []
        agent.log_path = ""
        agent.llmclient = SimpleNamespace(backend=SimpleNamespace(extra_sys_prompt=""))
        agent._handle_slash_cmd = lambda raw, _queue: raw
        output = queue.Queue()
        agent.task_queue.put({"query": "开始任务", "source": "test", "images": [], "output": output})
        agent.task_queue.put("stop")
        handler = StubHandler()

        with (mock.patch.object(agentmain, "get_system_prompt", return_value=""),
              mock.patch.object(agentmain, "GenericAgentHandler", return_value=handler),
              mock.patch.object(agentmain, "agent_runner_loop", return_value=failing_runner())):
            thread = threading.Thread(target=agent.run)
            thread.start()
            item = output.get(timeout=2)
            thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertEqual(item["transcript"], "已完成前半段")
        self.assertIn("provider timeout", item["error"])
        self.assertIn("已完成前半段", item["done"])
        self.assertIn("provider timeout", item["done"])
        self.assertEqual(item["exit_reason"], {"result": "ERROR"})


if __name__ == "__main__":
    unittest.main()
