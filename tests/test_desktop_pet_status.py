import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from plugins import desktop_pet_status as pet_status


ROOT = Path(__file__).resolve().parents[1]


class DesktopPetStatusTests(unittest.TestCase):
    def test_tool_action_mapping_covers_expected_ga_tools(self):
        expected = {
            "web_search": "search",
            "web_scan": "browse",
            "web_execute_js": "browse",
            "code_run": "code",
            "file_read": "read",
            "file_write": "write",
            "file_patch": "write",
            "ask_user": "ask",
            "update_working_checkpoint": "memory",
            "start_long_term_update": "memory",
            "restore_quarantine": "fix",
        }
        for tool, action in expected.items():
            self.assertEqual(pet_status.TOOL_ACTIONS[tool], action)

    def test_outcome_status_detects_error_like_results(self):
        self.assertEqual(pet_status._outcome_status(SimpleNamespace(data={"status": "success"})), "success")
        self.assertEqual(pet_status._outcome_status(SimpleNamespace(data={"status": "error"})), "error")
        self.assertEqual(pet_status._outcome_status(SimpleNamespace(data='{"status":"blocked"}')), "error")

    def test_memory_messages_are_specific(self):
        self.assertEqual(pet_status._tool_message("update_working_checkpoint", {}), "写入工作记忆")
        self.assertEqual(pet_status._tool_message("start_long_term_update", {}), "整理长期记忆")

    def test_ameath_registers_action_sprites(self):
        skin_path = ROOT / "frontends" / "skins" / "ameath" / "skin.json"
        skin = json.loads(skin_path.read_text(encoding="utf-8"))
        animations = skin["animations"]
        for action in (
            "thinking",
            "search",
            "browse",
            "code",
            "read",
            "write",
            "memory",
            "ask",
            "fix",
            "success",
            "error",
            "done",
            "cancelled",
        ):
            with self.subTest(action=action):
                entry = animations[action]
                image_path = skin_path.parent / entry["file"]
                self.assertTrue(image_path.is_file())
                sprite = entry["sprite"]
                self.assertGreater(sprite["frameCount"], 0)
                with Image.open(image_path) as image:
                    rows = (sprite["startFrame"] + sprite["frameCount"] + sprite["columns"] - 1) // sprite["columns"]
                    self.assertGreaterEqual(image.size[0], sprite["frameWidth"] * sprite["columns"])
                    self.assertGreaterEqual(image.size[1], sprite["frameHeight"] * rows)


if __name__ == "__main__":
    unittest.main()
