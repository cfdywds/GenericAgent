import io
import pathlib
import sys
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

import tuiapp_v2 as tui


def render_plain(renderable, width: int = 100) -> str:
    from rich.console import Console

    console = Console(width=width, record=True, file=io.StringIO())
    console.print(renderable)
    return console.export_text()


class HistoryPickerTests(unittest.TestCase):
    def test_filter_choices_does_not_scan_session_files(self):
        choices = [
            ("2h · slow cached preview · 15轮", "D:/tmp/model_responses_1.txt"),
            ("3h · another label · 4轮", "D:/tmp/model_responses_2.txt"),
        ]

        with patch.object(tui.os.path, "isfile", side_effect=AssertionError("disk scan")):
            filtered = tui._filter_choices(choices, "slow")

        self.assertEqual(filtered, [choices[0]])


class TopbarRenderTests(unittest.TestCase):
    def test_topbar_uses_compact_spacing_and_short_session_label(self):
        rendered = render_plain(
            tui.render_topbar(
                "very-long-session-name-that-would-crowd-the-row",
                "idle",
                "claude-sonnet-4",
                0,
                effort="medium",
                term_width=100,
            ),
            width=100,
        )

        self.assertIn("sess ", rendered)
        self.assertNotIn("session:", rendered)
        self.assertNotIn("  ·  ", rendered)

    def test_topbar_keeps_session_name_visible_on_wide_terminals(self):
        rendered = render_plain(
            tui.render_topbar(
                "session-name-that-should-remain-visible-in-wide-topbar",
                "running",
                "gpt-5.5",
                1,
                sess_elapsed=21,
                term_width=140,
            ),
            width=140,
        )

        self.assertIn("session-name-that-should", rendered)
        self.assertIn("model:", rendered)


if __name__ == "__main__":
    unittest.main()
