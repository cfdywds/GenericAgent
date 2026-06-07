import os
import pathlib
import sys
import tempfile
import time
import unittest
import textwrap
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

import continue_cmd


def _ts(value: str) -> float:
    return time.mktime(time.strptime(value, "%Y-%m-%d %H:%M:%S"))


def _write_log(path: pathlib.Path, prompt_ts: str, response_ts: str, text: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"=== Prompt === {prompt_ts}",
                '{"role":"user","content":[{"type":"text","text":"' + text + '"}]}',
                "",
                f"=== Response === {response_ts}",
                "[{'type':'text','text':'<summary>" + text + " summary</summary>'}]",
                "",
            ]
        ),
        encoding="utf-8",
    )


class ContinueListSessionsTests(unittest.TestCase):
    def test_list_sessions_orders_by_log_header_time_not_file_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            touched_old = root / "model_responses_100.txt"
            actual_recent = root / "model_responses_200.txt"
            _write_log(touched_old, "2026-06-05 20:00:00", "2026-06-05 20:01:00", "old session")
            _write_log(actual_recent, "2026-06-05 21:00:00", "2026-06-05 21:01:00", "recent session")
            os.utime(touched_old, (_ts("2026-06-05 23:00:00"), _ts("2026-06-05 23:00:00")))
            os.utime(actual_recent, (_ts("2026-06-05 22:00:00"), _ts("2026-06-05 22:00:00")))

            with patch.object(continue_cmd, "_LOG_GLOB", str(root / "model_responses_*.txt")), \
                 patch.object(continue_cmd, "_ROUNDS_CACHE_PATH", str(root / "rounds_cache.json")):
                continue_cmd._rounds_cache = None
                continue_cmd._rounds_cache_dirty = False
                sessions = continue_cmd.list_sessions()

        self.assertEqual(pathlib.Path(sessions[0][0]).name, "model_responses_200.txt")
        self.assertEqual(sessions[0][1], _ts("2026-06-05 21:01:00"))

    def test_restore_skips_corrupt_native_rounds_instead_of_downgrading(self):
        class Backend:
            history = []

        class Client:
            backend = Backend()

        class Agent:
            llmclient = Client()
            llmclients = [llmclient]
            history = []

            def abort(self):
                self.aborted = True

        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "model_responses_300.txt"
            log_path.write_text(
                textwrap.dedent(
                    """\
                    === Prompt === 2026-06-05 20:00:00
                    {"role":"user","content":[{"type":"text","text":"first"}]}

                    === Response === 2026-06-05 20:00:01
                    [{'type':'text','text':'<summary>first summary</summary>'}]

                    === Prompt === 2026-06-05 20:00:02
                    {"role":"user","content":[{"type":"text","text":"broken
                    prompt"}]}

                    === Response === 2026-06-05 20:00:03
                    [{'type':'text','text':'<summary>broken summary</summary>'}]

                    === Prompt === 2026-06-05 20:00:04
                    {"role":"user","content":[{"type":"text","text":"second"}]}

                    === Response === 2026-06-05 20:00:05
                    [{'type':'text','text':'<summary>second summary</summary>'}]

                    """
                ),
                encoding="utf-8",
            )
            agent = Agent()

            message, ok = continue_cmd.restore(agent, str(log_path))

        self.assertTrue(ok, message)
        self.assertIn("跳过 1 轮损坏记录", message)
        self.assertEqual([m["role"] for m in agent.llmclient.backend.history], ["user", "assistant", "user", "assistant"])
        self.assertEqual(agent.llmclient.backend.history[0]["content"][0]["text"], "first")
        self.assertEqual(agent.llmclient.backend.history[2]["content"][0]["text"], "second")

    def test_restore_removes_tool_edges_left_dangling_by_corrupt_rounds(self):
        class Backend:
            def __init__(self):
                self.history = []

        class Client:
            def __init__(self):
                self.backend = Backend()

        class Agent:
            def __init__(self):
                self.llmclient = Client()
                self.llmclients = [self.llmclient]
                self.history = []

            def abort(self):
                self.aborted = True

        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "model_responses_301.txt"
            log_path.write_text(
                textwrap.dedent(
                    """\
                    === Prompt === 2026-06-05 20:00:00
                    {"role":"user","content":[{"type":"text","text":"first"}]}

                    === Response === 2026-06-05 20:00:01
                    [{'type':'text','text':'first text'}, {'type':'tool_use','id':'call_good','name':'demo','input':{}}]

                    === Prompt === 2026-06-05 20:00:02
                    {"role":"user","content":[{"type":"tool_result","tool_use_id":"call_good","content":"ok"},{"type":"text","text":"broken
                    prompt"}]}

                    === Response === 2026-06-05 20:00:03
                    [{'type':'tool_use','id':'call_bad','name':'demo','input':{}}]

                    === Prompt === 2026-06-05 20:00:04
                    {"role":"user","content":[{"type":"tool_result","tool_use_id":"call_bad","content":"orphan"},{"type":"text","text":"second"}]}

                    === Response === 2026-06-05 20:00:05
                    [{'type':'text','text':'second text'}]

                    """
                ),
                encoding="utf-8",
            )
            agent = Agent()

            message, ok = continue_cmd.restore(agent, str(log_path))

        self.assertTrue(ok, message)
        all_blocks = [
            block
            for message in agent.llmclient.backend.history
            for block in message.get("content", [])
            if isinstance(block, dict)
        ]
        self.assertFalse([b for b in all_blocks if b.get("type") == "tool_use"])
        self.assertFalse([b for b in all_blocks if b.get("type") == "tool_result"])


if __name__ == "__main__":
    unittest.main()
