import os
import pathlib
import sys
import tempfile
import time
import unittest
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


if __name__ == "__main__":
    unittest.main()
