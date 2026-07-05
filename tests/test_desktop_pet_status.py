import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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

    def test_llm_before_uses_write_action_for_language_generation(self):
        with mock.patch.object(pet_status, "_send") as send:
            pet_status._on_llm_before({})

        send.assert_called_once_with("write", "组织语言中")

    def test_tool_after_returns_to_write_when_another_llm_turn_follows(self):
        ret = SimpleNamespace(data={"status": "success"}, next_prompt="continue", should_exit=False)

        with mock.patch.object(pet_status, "_send") as send, \
                mock.patch.object(pet_status, "_send_later") as send_later:
            pet_status._on_tool_after({"tool_name": "web_search", "ret": ret})

        send.assert_called_once_with("success", "完成")
        send_later.assert_called_once_with(1.2, "write", "组织语言中")

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

    def test_ameath_write_task_shadow_stays_clear_of_task_prop(self):
        image_path = ROOT / "frontends" / "skins" / "ameath" / "action_write.png"
        frame_width = 164
        shadow_box = (100, 134, 139, 163)
        max_shadow_pixels = 8

        with Image.open(image_path) as image:
            image = image.convert("RGBA")
            for frame_index in range(8):
                left, top, right, bottom = shadow_box
                x_offset = frame_index * frame_width
                shadow_pixels = 0
                for y in range(top, bottom):
                    for x in range(x_offset + left, x_offset + right):
                        red, green, blue, alpha = image.getpixel((x, y))
                        if 120 < alpha <= 235 and red < 85 and green < 95 and blue < 120:
                            shadow_pixels += 1

                with self.subTest(frame=frame_index):
                    self.assertLessEqual(shadow_pixels, max_shadow_pixels)

    def test_ameath_semantic_actions_change_character_pose_not_only_props(self):
        skin_path = ROOT / "frontends" / "skins" / "ameath"
        frame_width = 164
        frame_height = 198
        top_pose_box = (0, 0, frame_width, 110)
        min_changed_pixels = 600

        with Image.open(skin_path / "skin.png") as skin_image:
            skin_image = skin_image.convert("RGBA")
            idle_frames = [
                skin_image.crop((i * frame_width, 0, (i + 1) * frame_width, frame_height))
                for i in range(6)
            ]

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
            with Image.open(skin_path / f"action_{action}.png") as action_image:
                action_image = action_image.convert("RGBA")
                changed_counts = []
                for frame_index in range(4):
                    action_frame = action_image.crop((
                        frame_index * frame_width,
                        0,
                        (frame_index + 1) * frame_width,
                        frame_height,
                    ))
                    idle_frame = idle_frames[frame_index % len(idle_frames)]
                    changed = 0
                    left, top, right, bottom = top_pose_box
                    for y in range(top, bottom):
                        for x in range(left, right):
                            aa = action_frame.getpixel((x, y))[3]
                            ia = idle_frame.getpixel((x, y))[3]
                            if (aa > 20) != (ia > 20):
                                changed += 1
                    changed_counts.append(changed)

                with self.subTest(action=action):
                    self.assertGreaterEqual(max(changed_counts), min_changed_pixels)


if __name__ == "__main__":
    unittest.main()
