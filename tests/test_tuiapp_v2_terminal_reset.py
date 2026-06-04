import io
import importlib
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

tuiapp_v2 = importlib.import_module("tuiapp_v2")


class TuiAppV2TerminalResetTests(unittest.TestCase):
    def test_terminal_reset_disables_mouse_tracking_and_bracketed_paste(self):
        self.assertTrue(hasattr(tuiapp_v2, "_reset_terminal_modes"))
        stream = io.StringIO()

        tuiapp_v2._reset_terminal_modes(stream)

        output = stream.getvalue()
        for sequence in (
            "\x1b[?9l",
            "\x1b[?1000l",
            "\x1b[?1002l",
            "\x1b[?1003l",
            "\x1b[?1005l",
            "\x1b[?1006l",
            "\x1b[?1015l",
            "\x1b[?1007l",
            "\x1b[?2004l",
            "\x1b[0m",
            "\x1b[?25h",
        ):
            self.assertIn(sequence, output)


if __name__ == "__main__":
    unittest.main()
