import pathlib
import tempfile
import unittest


class LlmLogRedactionTests(unittest.TestCase):
    def test_write_llm_log_redacts_common_secret_fields(self):
        import llmcore

        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "model_responses_test.txt"
            llmcore._write_llm_log(
                "Prompt",
                "Authorization: Bearer sk-test-secret\n"
                "x-api-key: sk-ant-test-secret\n"
                "apikey='sk-test-secret-2'\n"
                "Cookie: sessionid=abc123; csrftoken=def456\n",
                str(log_path),
            )
            llmcore._write_llm_log(
                "Response",
                '{"api_key": "tp-json-secret", "Authorization": "Bearer relay-json-secret", "cookie": "sessionid=json-cookie"}',
                str(log_path),
            )

            text = log_path.read_text(encoding="utf-8")

        self.assertNotIn("sk-test-secret", text)
        self.assertNotIn("sk-ant-test-secret", text)
        self.assertNotIn("sk-test-secret-2", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("def456", text)
        self.assertNotIn("tp-json-secret", text)
        self.assertNotIn("relay-json-secret", text)
        self.assertNotIn("json-cookie", text)
        self.assertIn("[REDACTED]", text)

    def test_write_llm_log_redacts_extended_secret_patterns(self):
        import llmcore

        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "model_responses_test.txt"
            llmcore._write_llm_log(
                "Prompt",
                "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature\n"
                "github=ghp_1234567890abcdefghijklmnopqrstuvwxyzABCDEF\n"
                "aws=AKIAIOSFODNN7EXAMPLE\n"
                "url=https://example.test/cb?api_key=query-secret&token=token-secret&ok=1\n",
                str(log_path),
            )

            text = log_path.read_text(encoding="utf-8")

        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", text)
        self.assertNotIn("ghp_1234567890abcdefghijklmnopqrstuvwxyzABCDEF", text)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", text)
        self.assertNotIn("query-secret", text)
        self.assertNotIn("token-secret", text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
