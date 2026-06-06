import pathlib
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_declares_psutil_for_cli_status_and_tui_process_features(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = data["project"]["dependencies"]
        ui_dependencies = data["project"]["optional-dependencies"]["ui"]
        all_declared = "\n".join(dependencies + ui_dependencies).lower()

        self.assertIn("psutil", all_declared)


if __name__ == "__main__":
    unittest.main()
