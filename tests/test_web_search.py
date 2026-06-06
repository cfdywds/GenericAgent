import json
import types
import unittest
from unittest import mock


class WebSearchTests(unittest.TestCase):
    def test_web_search_uses_configured_grok2api_endpoint_and_key(self):
        import ga
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "model": "grok-test",
                    "choices": [{"message": {"content": "answer", "annotations": []}}],
                }).encode("utf-8")

        def fake_urlopen(req, timeout=None, context=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResponse()

        handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=".")
        config = {
            "grok2api_search_config": {
                "apikey": "search-key",
                "apibase": "https://search.example/v1",
                "model": "grok-search-model",
            }
        }

        with mock.patch("llmcore.reload_mykeys", return_value=(config, True)), \
             mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            outcome = handler.do_web_search({"query": "latest news", "max_results": 3}, types.SimpleNamespace(content=""))

        self.assertEqual(outcome.data["status"], "success")
        self.assertEqual(outcome.data["channel"], "grok")
        self.assertEqual(captured["url"], "https://search.example/v1/chat/completions")
        self.assertEqual(captured["headers"].get("Authorization"), "Bearer search-key")
        self.assertEqual(captured["body"]["model"], "grok-search-model")
        self.assertEqual(captured["body"]["search_parameters"], {"mode": "auto"})

    def test_web_search_returns_grok2api_config_hint_when_all_paths_fail(self):
        import ga

        handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=".")

        with mock.patch("llmcore.reload_mykeys", return_value=({}, True)), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("forbidden")), \
             mock.patch.object(ga, "web_execute_js", side_effect=RuntimeError("browser unavailable")):
            outcome = handler.do_web_search({"query": "latest news"}, types.SimpleNamespace(content=""))

        self.assertEqual(outcome.data["status"], "error")
        self.assertIn("grok2api_search_config", outcome.data["grok_config_hint"])
        self.assertIn("GROK2API_API_KEY", outcome.data["grok_config_hint"])

    def test_web_search_falls_back_to_original_google_search_when_grok2api_fails(self):
        import ga

        handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=".")
        executed = []

        def fake_execute_js(script):
            executed.append(script)
            return {"status": "success"}

        def fake_web_scan(text_only=False):
            return {"status": "success", "content": "Result title\nUseful search result snippet with enough length"}

        with mock.patch("llmcore.reload_mykeys", return_value=({}, True)), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("grok2api unavailable")), \
             mock.patch.object(ga, "web_execute_js", side_effect=fake_execute_js), \
             mock.patch.object(ga, "web_scan", side_effect=fake_web_scan), \
             mock.patch.object(ga.time, "sleep", return_value=None):
            outcome = handler.do_web_search({"query": "latest news", "max_results": 2}, types.SimpleNamespace(content=""))

        self.assertEqual(outcome.data["status"], "success")
        self.assertEqual(outcome.data["channel"], "google_fallback")
        self.assertIn("Useful search result", outcome.data["answer"])
        self.assertEqual(len(executed), 1)
        self.assertIn("https://www.google.com/search?q=latest%20news", executed[0])


if __name__ == "__main__":
    unittest.main()
