import importlib
import importlib.util
import hashlib
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))


class FilePolicyTests(unittest.TestCase):
    def test_denies_write_outside_repo_root(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            outside = root.parent / "outside.txt"

            decision = FilePolicy(root=root, cwd=cwd).evaluate("write", outside)

        self.assertEqual(decision.action, "deny")
        self.assertIn("outside", decision.reason.lower())

    def test_denies_overwrite_of_secret_file(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            secret = root / "mykey.py"
            secret.write_text("secret", encoding="utf-8")

            decision = FilePolicy(root=root, cwd=cwd).evaluate("overwrite", secret)

        self.assertEqual(decision.action, "deny")
        self.assertEqual(decision.risk, "critical")

    def test_denies_common_secret_file_patterns(self):
        from security.file_policy import FilePolicy

        secret_paths = [
            ".env.local",
            ".env.production",
            "server.pem",
            "private.key",
            "id_ed25519",
            "credentials.json",
            "service-account.json",
            ".ssh/config",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            policy = FilePolicy(root=root, cwd=cwd)

            decisions = [policy.evaluate("overwrite", root / path) for path in secret_paths]

        self.assertTrue(all(decision.action == "deny" for decision in decisions))

    def test_requires_confirmation_for_core_source_overwrite(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            source = root / "ga.py"
            source.write_text("print('old')", encoding="utf-8")

            decision = FilePolicy(root=root, cwd=cwd).evaluate("overwrite", source)

        self.assertEqual(decision.action, "confirm")
        self.assertEqual(decision.risk, "high")

    def test_allows_new_file_inside_temp(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)

            decision = FilePolicy(root=root, cwd=cwd).evaluate("write", cwd / "note.txt")

        self.assertEqual(decision.action, "allow")
        self.assertEqual(decision.risk, "low")

    def test_safe_delete_moves_non_temp_file_to_quarantine_and_audits(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            target = root / "notes.md"
            target.write_text("important", encoding="utf-8")

            result = FilePolicy(root=root, cwd=cwd).safe_delete(target, reason="unit test", actor="test")

            quarantine_path = pathlib.Path(result["quarantine_path"])
            audit_path = root / "temp" / "security_audit.jsonl"
            self.assertFalse(target.exists())
            self.assertTrue(quarantine_path.is_file())
            self.assertEqual(quarantine_path.read_text(encoding="utf-8"), "important")
            self.assertIn('"operation": "delete"', audit_path.read_text(encoding="utf-8"))

    def test_safe_delete_writes_manifest_and_restore_recovers_file(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            target = root / "docs" / "notes.md"
            target.parent.mkdir()
            target.write_text("important", encoding="utf-8")
            policy = FilePolicy(root=root, cwd=cwd)

            result = policy.safe_delete(target, reason="unit test", actor="test")
            restore_result = policy.restore_quarantine(result["quarantine_id"])

            manifest_text = (root / "temp" / "quarantine" / "manifest.jsonl").read_text(encoding="utf-8")
            self.assertEqual(restore_result["status"], "restored")
            self.assertEqual(target.read_text(encoding="utf-8"), "important")
            self.assertIn('"original_path"', manifest_text)
            self.assertIn(result["quarantine_id"], manifest_text)

    def test_restore_quarantine_rejects_hash_mismatch(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            target = root / "notes.md"
            target.write_text("important", encoding="utf-8")
            policy = FilePolicy(root=root, cwd=cwd)

            result = policy.safe_delete(target, reason="unit test", actor="test")
            pathlib.Path(result["quarantine_path"]).write_text("tampered", encoding="utf-8")
            restore_result = policy.restore_quarantine(result["quarantine_id"])

            self.assertEqual(restore_result["status"], "blocked")
            self.assertIn("integrity", restore_result["reason"])
            self.assertFalse(target.exists())

    def test_restore_quarantine_rejects_manifest_path_tampering(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            target = root / "notes.md"
            target.write_text("important", encoding="utf-8")
            policy = FilePolicy(root=root, cwd=cwd)

            result = policy.safe_delete(target, reason="unit test", actor="test")
            manifest = root / "temp" / "quarantine" / "manifest.jsonl"
            records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
            records[-1]["original_path"] = str(root / "malicious.md")
            manifest.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            restore_result = policy.restore_quarantine(result["quarantine_id"])

            self.assertEqual(restore_result["status"], "blocked")
            self.assertIn("integrity", restore_result["reason"])
            self.assertFalse((root / "malicious.md").exists())

    def test_restore_quarantine_rejects_forged_manifest_record(self):
        from security.file_policy import FilePolicy

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            quarantine_dir = root / "temp" / "quarantine"
            quarantine_dir.mkdir(parents=True)
            forged_source = quarantine_dir / "forged.txt"
            forged_source.write_text("payload", encoding="utf-8")
            target = root / "forged_restore.txt"
            forged_record = {
                "id": "forged123",
                "original_path": str(target),
                "quarantine_path": str(forged_source),
                "size": forged_source.stat().st_size,
                "sha256": hashlib.sha256(forged_source.read_bytes()).hexdigest(),
                "restored": False,
            }
            (quarantine_dir / "manifest.jsonl").write_text(json.dumps(forged_record) + "\n", encoding="utf-8")
            policy = FilePolicy(root=root, cwd=cwd)

            restore_result = policy.restore_quarantine("forged123")

            self.assertEqual(restore_result["status"], "blocked")
            self.assertIn("integrity", restore_result["reason"])
            self.assertFalse(target.exists())


class GenericAgentFileSafetyTests(unittest.TestCase):
    def test_file_write_denies_paths_outside_repo_root(self):
        ga = importlib.import_module("ga")
        exhaust = importlib.import_module("agent_loop").exhaust

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "outside.txt"
            handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=tmp)
            response = types.SimpleNamespace(content="<file_content>\nunsafe write\n</file_content>")
            outcome = exhaust(handler.do_file_write({"path": "outside.txt", "mode": "overwrite"}, response))

            self.assertEqual(outcome.data["status"], "blocked")
            self.assertFalse(target.exists())

    def test_file_write_rejects_invalid_mode(self):
        ga = importlib.import_module("ga")
        exhaust = importlib.import_module("agent_loop").exhaust
        original_script_dir = ga.script_dir

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            target = cwd / "notes.md"
            ga.script_dir = str(root)
            self.addCleanup(setattr, ga, "script_dir", original_script_dir)
            handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=str(cwd))
            response = types.SimpleNamespace(content="<file_content>\ncontent\n</file_content>")

            outcome = exhaust(handler.do_file_write({"path": "notes.md", "mode": "sideways"}, response))

            self.assertEqual(outcome.data["status"], "error")
            self.assertIn("Invalid mode", outcome.data["msg"])
            self.assertFalse(target.exists())

    def test_file_patch_allows_precise_patch_inside_repo(self):
        ga = importlib.import_module("ga")
        exhaust = importlib.import_module("agent_loop").exhaust
        original_script_dir = ga.script_dir

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            target = root / "notes.md"
            target.write_text("before\n", encoding="utf-8")
            ga.script_dir = str(root)
            self.addCleanup(setattr, ga, "script_dir", original_script_dir)
            handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=str(cwd))

            outcome = exhaust(handler.do_file_patch({"path": "../notes.md", "old_content": "before", "new_content": "after"}, types.SimpleNamespace(content="")))

            self.assertEqual(outcome.data["status"], "success")
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")

    def test_web_execute_js_save_to_file_denies_paths_outside_repo_root(self):
        ga = importlib.import_module("ga")
        exhaust = importlib.import_module("agent_loop").exhaust
        original_script_dir = ga.script_dir

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            outside = pathlib.Path(tmp) / "outside.txt"
            ga.script_dir = str(root)
            self.addCleanup(setattr, ga, "script_dir", original_script_dir)
            handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=str(cwd))

            with mock.patch.object(ga, "web_execute_js", return_value={"status": "success", "js_return": "unsafe"}):
                outcome = exhaust(handler.do_web_execute_js({"script": "return 1", "save_to_file": "../../outside.txt"}, types.SimpleNamespace(content="")))

            self.assertEqual(outcome.data["status"], "blocked")
            self.assertFalse(outside.exists())

    def test_restore_quarantine_tool_recovers_quarantined_file(self):
        ga = importlib.import_module("ga")
        exhaust = importlib.import_module("agent_loop").exhaust
        original_script_dir = ga.script_dir

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            cwd = root / "temp"
            cwd.mkdir(parents=True)
            target = root / "notes.md"
            target.write_text("important", encoding="utf-8")
            ga.script_dir = str(root)
            self.addCleanup(setattr, ga, "script_dir", original_script_dir)
            handler = ga.GenericAgentHandler(types.SimpleNamespace(task_dir=None, verbose=False), cwd=str(cwd))
            delete_result = handler._file_policy().safe_delete(target, reason="unit test", actor="test")

            outcome = exhaust(handler.do_restore_quarantine({"quarantine_id": delete_result["quarantine_id"]}, types.SimpleNamespace(content="")))

            self.assertEqual(outcome.data["status"], "restored")
            self.assertEqual(target.read_text(encoding="utf-8"), "important")


class ToolSchemaSafetyTests(unittest.TestCase):
    def test_restore_quarantine_is_exposed_in_tool_schemas(self):
        for schema_path in (ROOT / "assets" / "tools_schema.json", ROOT / "assets" / "tools_schema_cn.json"):
            tools = json.loads(schema_path.read_text(encoding="utf-8"))
            names = {tool["function"]["name"] for tool in tools}

            self.assertIn("restore_quarantine", names)

    def test_restore_quarantine_schema_requires_quarantine_id(self):
        for schema_path in (ROOT / "assets" / "tools_schema.json", ROOT / "assets" / "tools_schema_cn.json"):
            tools = json.loads(schema_path.read_text(encoding="utf-8"))
            restore = next(tool for tool in tools if tool["function"]["name"] == "restore_quarantine")
            params = restore["function"]["parameters"]

            self.assertIn("quarantine_id", params.get("required", []))
            self.assertFalse(params.get("additionalProperties", True))


class L4ArchiveSafetyTests(unittest.TestCase):
    def test_raw_log_delete_uses_file_policy_audit(self):
        spec = importlib.util.spec_from_file_location(
            "compress_session_under_test",
            ROOT / "memory" / "L4_raw_sessions" / "compress_session.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            raw_dir = root / "temp" / "model_responses"
            raw_dir.mkdir(parents=True)
            raw = raw_dir / "model_responses_1.txt"
            raw.write_text("raw", encoding="utf-8")

            deleted = module._delete_raw_files([str(raw)], repo_root=str(root))

            audit_path = root / "temp" / "security_audit.jsonl"
            self.assertEqual(deleted, 1)
            self.assertFalse(raw.exists())
            self.assertIn('"operation": "delete"', audit_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
