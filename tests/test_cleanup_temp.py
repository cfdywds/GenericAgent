import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cleanup_temp


class CleanupTempSafetyTests(unittest.TestCase):
    def test_security_artifacts_are_explicitly_protected(self):
        self.assertIn("quarantine", cleanup_temp.PROTECTED_TOP_DIRS)
        self.assertIn("file_backups", cleanup_temp.PROTECTED_TOP_DIRS)
        self.assertIn("security_audit.jsonl", cleanup_temp.PROTECTED_FILES)

    def test_refuses_project_directory_that_is_not_temp_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "repo"
            temp_dir = repo / "temp"
            docs_dir = repo / "docs"
            temp_dir.mkdir(parents=True)
            docs_dir.mkdir()

            with mock.patch.object(cleanup_temp, "ROOT", repo), mock.patch.object(
                cleanup_temp, "TEMP_DIR", temp_dir
            ), mock.patch.object(cleanup_temp, "CLIPBOARD_DIR", repo / "clipboard"), mock.patch.object(
                sys, "argv", ["cleanup_temp.py", "--temp-dir", str(docs_dir), "--dry-run"]
            ):
                result = cleanup_temp.main()

        self.assertEqual(result, 2)

    def test_build_plan_preserves_security_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "repo"
            temp_dir = repo / "temp"
            quarantine_dir = temp_dir / "quarantine"
            backup_dir = temp_dir / "file_backups"
            audit_file = temp_dir / "security_audit.jsonl"
            quarantine_dir.mkdir(parents=True)
            backup_dir.mkdir(parents=True)
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            audit_file.write_text("audit", encoding="utf-8")
            args = type("Args", (), {"temp_dir": str(temp_dir), "days": 0, "include_scripts": True})()

            plan = cleanup_temp.build_plan(args)
            planned = {item.path.resolve() for item in plan}

        self.assertNotIn(quarantine_dir.resolve(), planned)
        self.assertNotIn(backup_dir.resolve(), planned)
        self.assertNotIn(audit_file.resolve(), planned)


if __name__ == "__main__":
    unittest.main()
