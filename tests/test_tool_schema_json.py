import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ToolSchemaJsonTests(unittest.TestCase):
    def test_all_tool_schema_files_are_valid_json(self):
        for schema_path in sorted((ROOT / "assets").glob("tools_schema*.json")):
            with self.subTest(schema=schema_path.name):
                raw = schema_path.read_text(encoding="utf-8")
                json.loads(raw)

    def test_non_windows_shell_replacement_keeps_default_schema_valid(self):
        raw = (ROOT / "assets" / "tools_schema.json").read_text(encoding="utf-8")
        json.loads(raw.replace("powershell", "bash"))

    def test_web_search_is_exposed_in_all_tool_schemas(self):
        for schema_path in (ROOT / "assets" / "tools_schema.json", ROOT / "assets" / "tools_schema_cn.json"):
            with self.subTest(schema=schema_path.name):
                tools = json.loads(schema_path.read_text(encoding="utf-8"))
                names = {tool["function"]["name"] for tool in tools}

                self.assertIn("web_search", names)


if __name__ == "__main__":
    unittest.main()
