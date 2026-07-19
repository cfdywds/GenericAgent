import io
import sys
import unittest
from unittest import mock

from plugins import hooks


class _StreamWithEncoding(io.StringIO):
    def __init__(self, encoding="utf-8"):
        super().__init__()
        self._encoding = encoding

    @property
    def encoding(self):
        return self._encoding


class HooksSafeStderrTests(unittest.TestCase):
    def setUp(self):
        hooks.clear()

    def tearDown(self):
        hooks.clear()

    def test_trigger_swallows_callback_errors(self):
        @hooks.register("unit_test_event")
        def boom(_ctx):
            raise RuntimeError("callback blew up")

        out = hooks.trigger("unit_test_event", {"ok": True})
        self.assertEqual(out, {"ok": True})

    def test_trigger_survives_broken_stderr_write(self):
        """Regression: OSError errno 22 from sys.stderr.write must not escape trigger()."""

        @hooks.register("unit_test_event")
        def boom(_ctx):
            raise ValueError("inner hook failure")

        class BrokenStderr:
            encoding = "utf-8"

            def write(self, _s):
                raise OSError(22, "Invalid argument")

            def flush(self):
                raise OSError(22, "Invalid argument")

        old = sys.stderr
        sys.stderr = BrokenStderr()
        try:
            out = hooks.trigger("unit_test_event", {"x": 1})
        finally:
            sys.stderr = old

        self.assertEqual(out, {"x": 1})

    def test_trigger_survives_none_stderr(self):
        @hooks.register("unit_test_event")
        def boom(_ctx):
            raise RuntimeError("fail")

        old = sys.stderr
        sys.stderr = None
        try:
            out = hooks.trigger("unit_test_event", {"a": 2})
        finally:
            sys.stderr = old

        self.assertEqual(out, {"a": 2})

    def test_load_failure_does_not_raise_on_broken_stderr(self):
        class BrokenStderr:
            encoding = "utf-8"

            def write(self, _s):
                raise OSError(22, "Invalid argument")

            def flush(self):
                pass

        old = sys.stderr
        sys.stderr = BrokenStderr()
        try:
            with mock.patch("importlib.import_module", side_effect=ImportError("nope")):
                ok = hooks.load("definitely_missing_plugin_xyz")
        finally:
            sys.stderr = old

        self.assertFalse(ok)

    def test_safe_stderr_replaces_unencodable_chars(self):
        buf = _StreamWithEncoding("ascii")
        old = sys.stderr
        sys.stderr = buf
        try:
            hooks._safe_stderr("hello \u2603 snowman\n")
        finally:
            sys.stderr = old
        self.assertIn("hello", buf.getvalue())
        self.assertNotIn("\u2603", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
