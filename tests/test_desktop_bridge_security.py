import asyncio
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

import desktop_bridge


class FakeJsonRequest:
    can_read_body = True

    def __init__(self, data, *, query=None, match_info=None):
        self._data = data
        self.query = query or {}
        self.match_info = match_info or {}

    async def json(self):
        return self._data


class FakeCorsRequest:
    def __init__(self, method="POST", origin="https://evil.example", token=None):
        self.method = method
        self.headers = {"Origin": origin}
        if token is not None:
            self.headers["X-GA-Bridge-Token"] = token


def json_from_response(response):
    return json.loads(response.text)


class DesktopBridgeSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_cors_headers_do_not_allow_arbitrary_origins(self):
        headers = desktop_bridge.cors_headers()

        self.assertNotEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_bridge_bind_host_refuses_public_interfaces_by_default(self):
        with mock.patch.dict(os.environ, {"BRIDGE_HOST": "0.0.0.0"}):
            self.assertEqual(desktop_bridge._bridge_bind_host(), "127.0.0.1")

        with mock.patch.dict(os.environ, {"BRIDGE_HOST": "::"}):
            self.assertEqual(desktop_bridge._bridge_bind_host(), "127.0.0.1")

    async def test_cors_middleware_rejects_cross_origin_state_change(self):
        handler = mock.AsyncMock()

        response = await desktop_bridge.cors_middleware(FakeCorsRequest(), handler)

        self.assertEqual(response.status, 403)
        handler.assert_not_called()

    async def test_status_does_not_expose_bridge_token(self):
        response = await desktop_bridge.status_handler(FakeJsonRequest({}))
        data = json_from_response(response)

        self.assertNotIn("bridgeToken", data)

    async def test_cors_middleware_rejects_state_change_without_bridge_token(self):
        handler = mock.AsyncMock()
        request = FakeCorsRequest(origin=desktop_bridge._default_allowed_origin())

        response = await desktop_bridge.cors_middleware(request, handler)

        self.assertEqual(response.status, 403)
        handler.assert_not_called()

    async def test_cors_middleware_allows_state_change_with_bridge_token(self):
        handler = mock.AsyncMock(return_value=desktop_bridge.json_ok({"ok": True}))
        request = FakeCorsRequest(
            origin=desktop_bridge._default_allowed_origin(),
            token=desktop_bridge.manager.bridge_token,
        )

        response = await desktop_bridge.cors_middleware(request, handler)

        self.assertEqual(response.status, 200)
        handler.assert_called_once()

    async def test_new_session_rejects_cwd_outside_ga_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            root.mkdir()
            outside = pathlib.Path(tmp) / "outside"
            outside.mkdir()
            original_root = desktop_bridge.manager.ga_root
            desktop_bridge.manager.ga_root = str(root)
            self.addCleanup(setattr, desktop_bridge.manager, "ga_root", original_root)

            with mock.patch.object(desktop_bridge.manager, "create_session") as create_session:
                response = await desktop_bridge.new_session_handler(FakeJsonRequest({"cwd": str(outside)}))

            self.assertEqual(response.status, 403)
            create_session.assert_not_called()

    async def test_messages_rejects_invalid_query_params(self):
        request = FakeJsonRequest(
            {},
            query={"after": "not-a-number", "limit": "200"},
            match_info={"sid": "sess-test"},
        )

        with mock.patch.object(desktop_bridge.manager, "messages") as messages:
            response = await desktop_bridge.messages_handler(request)

        self.assertEqual(response.status, 400)
        messages.assert_not_called()

    async def test_messages_rejects_negative_query_params(self):
        request = FakeJsonRequest(
            {},
            query={"after": "-1", "limit": "0"},
            match_info={"sid": "sess-test"},
        )

        with mock.patch.object(desktop_bridge.manager, "messages") as messages:
            response = await desktop_bridge.messages_handler(request)

        self.assertEqual(response.status, 400)
        messages.assert_not_called()

    async def test_path_open_rejects_paths_outside_ga_root_before_opening(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            root.mkdir()
            outside = pathlib.Path(tmp) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            original_root = desktop_bridge.manager.ga_root
            desktop_bridge.manager.ga_root = str(root)
            self.addCleanup(setattr, desktop_bridge.manager, "ga_root", original_root)

            with mock.patch("os.startfile", create=True) as startfile:
                response = await desktop_bridge.path_open_handler(FakeJsonRequest({"path": str(outside)}))

            self.assertEqual(response.status, 403)
            startfile.assert_not_called()

    async def test_path_open_mykey_template_opens_template_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            root.mkdir()
            template = root / "mykey_template.py"
            template.write_text("template", encoding="utf-8")
            original_root = desktop_bridge.manager.ga_root
            desktop_bridge.manager.ga_root = str(root)
            self.addCleanup(setattr, desktop_bridge.manager, "ga_root", original_root)

            with mock.patch("os.startfile", create=True) as startfile:
                response = await desktop_bridge.path_open_handler(FakeJsonRequest({"kind": "mykeyTemplate"}))

            self.assertEqual(response.status, 200)
            startfile.assert_called_once_with(str(template.resolve()))


if __name__ == "__main__":
    unittest.main()
