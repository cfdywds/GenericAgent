import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from plugins import desktop_pet_status as pet_status


ROOT = Path(__file__).resolve().parents[1]


def _alpha_values(image):
    alpha = image.getchannel("A")
    if hasattr(alpha, "get_flattened_data"):
        return alpha.get_flattened_data()
    return alpha.getdata()


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


    def test_llm_before_uses_thinking_action_for_language_generation(self):
        with mock.patch.object(pet_status, "_send") as send:
            pet_status._on_llm_before({})

        send.assert_called_once_with("thinking", "思考中")

    def test_tool_after_returns_to_thinking_when_another_llm_turn_follows(self):
        ret = SimpleNamespace(data={"status": "success"}, next_prompt="continue", should_exit=False)

        with mock.patch.object(pet_status, "_send") as send, \
                mock.patch.object(pet_status, "_send_later") as send_later:
            pet_status._on_tool_after({"tool_name": "web_search", "ret": ret})

        send.assert_called_once_with("success", "完成")
        send_later.assert_called_once_with(1.2, "thinking", "思考中")

    def test_send_includes_text_hint_without_breaking_action_query(self):
        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target
                self.daemon = daemon

            def start(self):
                self.target()

        with mock.patch.object(pet_status.threading, "Thread", ImmediateThread), \
                mock.patch.object(pet_status.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.read.return_value = b"ok"
            pet_status._send("search", "legacy message")

        url = urlopen.call_args.args[0]
        self.assertIn("action=search", url)
        self.assertIn("msg=legacy+message", url)

    def test_set_action_updates_character_state_and_shows_text_hint(self):
        module_path = ROOT / "frontends" / "desktop_pet_v2.pyw"
        try:
            loader = importlib.machinery.SourceFileLoader("desktop_pet_v2_under_test", str(module_path))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            pet_module = importlib.util.module_from_spec(spec)
            loader.exec_module(pet_module)
        except ModuleNotFoundError as exc:
            self.skipTest(f"desktop pet GUI dependency is unavailable: {exc.name}")

        class DummyPet(pet_module.PetBase):
            def __init__(self):
                self.animations = {"idle": {}, "search": {}}
                self.state = None
                self.toast_messages = []

            def _schedule_main(self, fn):
                fn()

            def set_state(self, state):
                self.state = state

            def show_toast(self, message):
                self.toast_messages.append(message)

        pet = DummyPet()
        pet.set_action("search", "legacy message")
        pet.show_toast_safe("direct message")

        self.assertEqual(pet.state, "search")
        self.assertEqual(pet.toast_messages, ["legacy message", "direct message"])

    def test_status_bubble_image_uses_asset_style_and_tail_anchor(self):
        module_path = ROOT / "frontends" / "desktop_pet_v2.pyw"
        try:
            loader = importlib.machinery.SourceFileLoader("desktop_pet_v2_under_test", str(module_path))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            pet_module = importlib.util.module_from_spec(spec)
            loader.exec_module(pet_module)
        except ModuleNotFoundError as exc:
            self.skipTest(f"desktop pet GUI dependency is unavailable: {exc.name}")

        info = pet_module.build_bubble_image("搜索中", max_width=256)
        image = info["image"]
        alpha_values = list(_alpha_values(image))
        opaque_pixels = sum(1 for alpha in alpha_values if alpha > 200)
        transparent_pixels = sum(1 for alpha in alpha_values if alpha == 0)
        tail_x, tail_y = info["tail_tip"]

        self.assertGreaterEqual(image.size[1], 64)
        self.assertGreater(opaque_pixels, image.size[0] * image.size[1] // 4)
        self.assertGreater(transparent_pixels, 0)
        self.assertGreaterEqual(tail_y, image.size[1] - 3)
        self.assertGreaterEqual(tail_x, 0)
        self.assertLess(tail_x, image.size[0])
        self.assertGreaterEqual(pet_module.TOAST_DISPLAY_SECONDS, 8)
        self.assertEqual(pet_module.TOAST_DISPLAY_MS, int(pet_module.TOAST_DISPLAY_SECONDS * 1000))

    def test_agent_done_action_uses_character_states_for_terminal_status(self):
        self.assertEqual(pet_status._agent_done_action({}, maxed=True), "ask")
        self.assertEqual(pet_status._agent_done_action({"result": "MAX_TURNS_EXCEEDED"}), "ask")
        self.assertEqual(pet_status._agent_done_action({"result": "CANCELLED"}), "cancelled")
        self.assertEqual(pet_status._agent_done_action({"result": "ERROR"}), "error")
        self.assertEqual(pet_status._agent_done_action({"result": "DONE"}), "done")

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

    def test_ameath_action_sprites_stay_within_character_frame_budget(self):
        skin_path = ROOT / "frontends" / "skins" / "ameath"
        frame_width = 164
        frame_height = 198
        min_character_pixels = 7000

        with Image.open(skin_path / "skin.png") as skin_image:
            skin_image = skin_image.convert("RGBA")
            base_counts = []
            for frame_index in range(32):
                frame = skin_image.crop((
                    (frame_index % 8) * frame_width,
                    (frame_index // 8) * frame_height,
                    (frame_index % 8 + 1) * frame_width,
                    (frame_index // 8 + 1) * frame_height,
                ))
                count = sum(1 for alpha in _alpha_values(frame) if alpha > 20)
                if count:
                    base_counts.append(count)

        max_character_pixels = max(base_counts) + 500
        skin_config = json.loads((skin_path / "skin.json").read_text(encoding="utf-8"))

        for action, entry in skin_config["animations"].items():
            if action in {"idle", "walk", "run", "sprint"}:
                continue
            sprite = entry["sprite"]
            with Image.open(skin_path / entry["file"]) as image:
                image = image.convert("RGBA")
                for frame_index in range(sprite["frameCount"]):
                    frame = image.crop((
                        (frame_index % sprite["columns"]) * frame_width,
                        (frame_index // sprite["columns"]) * frame_height,
                        (frame_index % sprite["columns"] + 1) * frame_width,
                        (frame_index // sprite["columns"] + 1) * frame_height,
                    ))
                    count = sum(1 for alpha in _alpha_values(frame) if alpha > 20)

                    with self.subTest(action=action, frame=frame_index):
                        self.assertGreaterEqual(count, min_character_pixels)
                        self.assertLessEqual(count, max_character_pixels)

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


    def _raw_agent_frame_without_edge_background(self, raw_image, frame_index):
        raw_columns = 4
        raw_width = 292
        raw_height = 196
        frame = raw_image.crop((
            (frame_index % raw_columns) * raw_width,
            (frame_index // raw_columns) * raw_height,
            (frame_index % raw_columns + 1) * raw_width,
            (frame_index // raw_columns + 1) * raw_height,
        )).convert("RGBA")
        pixels = frame.load()
        output = frame.copy()
        out_pixels = output.load()
        seen = set()
        stack = []

        def is_background(pixel):
            red, green, blue, alpha = pixel
            return alpha == 0 or (min(red, green, blue) >= 218 and max(red, green, blue) - min(red, green, blue) <= 32)

        for x in range(raw_width):
            for y in (0, raw_height - 1):
                if is_background(pixels[x, y]) and (x, y) not in seen:
                    seen.add((x, y))
                    stack.append((x, y))
        for y in range(raw_height):
            for x in (0, raw_width - 1):
                if is_background(pixels[x, y]) and (x, y) not in seen:
                    seen.add((x, y))
                    stack.append((x, y))

        while stack:
            x, y = stack.pop()
            out_pixels[x, y] = (0, 0, 0, 0)
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < raw_width and 0 <= ny < raw_height and (nx, ny) not in seen and is_background(pixels[nx, ny]):
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return output

    def _fit_raw_agent_frame_to_runtime_canvas(self, raw_frame):
        expected = Image.new("RGBA", (164, 198), (0, 0, 0, 0))
        alpha = raw_frame.getchannel("A")
        pixels = alpha.load()
        width, height = raw_frame.size
        seen = set()
        largest_bbox = None
        largest_count = 0

        for y in range(height):
            for x in range(width):
                if pixels[x, y] <= 20 or (x, y) in seen:
                    continue
                stack = [(x, y)]
                seen.add((x, y))
                count = 0
                min_x = max_x = x
                min_y = max_y = y
                while stack:
                    cx, cy = stack.pop()
                    count += 1
                    min_x = min(min_x, cx)
                    max_x = max(max_x, cx)
                    min_y = min(min_y, cy)
                    max_y = max(max_y, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < width and 0 <= ny < height and pixels[nx, ny] > 20 and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                if count > largest_count:
                    largest_count = count
                    largest_bbox = (min_x, min_y, max_x + 1, max_y + 1)

        if largest_bbox is None:
            return expected

        left, top, right, bottom = largest_bbox
        top = max(0, top - 6)
        crop_height = bottom - top
        crop_width = min(width, max(1, round(crop_height * 164 / 198)))
        center_x = round((left + right) / 2)
        crop_left = max(0, min(width - crop_width, center_x - crop_width // 2))
        raw_frame = raw_frame.crop((crop_left, top, crop_left + crop_width, bottom))

        scale = min(164 / raw_frame.size[0], 198 / raw_frame.size[1])
        fitted_size = (
            max(1, round(raw_frame.size[0] * scale)),
            max(1, round(raw_frame.size[1] * scale)),
        )
        fitted = raw_frame.resize(fitted_size, Image.NEAREST)
        expected.alpha_composite(fitted, ((164 - fitted_size[0]) // 2, 198 - fitted_size[1]))
        return expected

    def _assert_frame_matches_raw_canvas(self, generated_frame, raw_frame):
        expected = self._fit_raw_agent_frame_to_runtime_canvas(raw_frame)
        self.assertEqual(generated_frame.tobytes(), expected.tobytes())

    def _assert_generated_agent_frames_match_ameath_budget(self, skin_name):
        skin_path = ROOT / "frontends" / "skins" / skin_name
        skin_config = json.loads((skin_path / "skin.json").read_text(encoding="utf-8"))
        action_rows = {
            "thinking": 0,
            "read": 0,
            "write": 0,
            "memory": 0,
            "ask": 0,
            "success": 0,
            "error": 0,
            "done": 0,
            "cancelled": 0,
            "search": 1,
            "browse": 1,
            "code": 2,
            "fix": 3,
        }

        self.assertEqual(skin_config["size"], {"width": 128, "height": 156})

        with Image.open(skin_path / "grok_sprite_sheet_raw.png") as raw_image:
            raw_image = raw_image.convert("RGBA")
            self.assertEqual(raw_image.size, (1168, 784))
            for action, entry in skin_config["animations"].items():
                sprite = entry["sprite"]
                frame_width = sprite["frameWidth"]
                frame_height = sprite["frameHeight"]
                self.assertEqual((frame_width, frame_height), (164, 198))
                with Image.open(skin_path / entry["file"]) as image:
                    image = image.convert("RGBA")
                    rows = (sprite["startFrame"] + sprite["frameCount"] + sprite["columns"] - 1) // sprite["columns"]
                    self.assertGreaterEqual(image.size[0], frame_width * sprite["columns"])
                    self.assertGreaterEqual(image.size[1], frame_height * rows)
                    for frame_index in range(sprite["frameCount"]):
                        source_index = sprite["startFrame"] + frame_index
                        generated_frame = image.crop((
                            (source_index % sprite["columns"]) * frame_width,
                            (source_index // sprite["columns"]) * frame_height,
                            (source_index % sprite["columns"] + 1) * frame_width,
                            (source_index // sprite["columns"] + 1) * frame_height,
                        ))
                        if action in {"idle", "walk", "run", "sprint"}:
                            raw_index = (source_index // 8) * 4 + (source_index % 8) % 4
                        else:
                            raw_index = action_rows[action] * 4 + (frame_index % 4)
                        raw_frame = self._raw_agent_frame_without_edge_background(raw_image, raw_index)
                        runtime_frame = generated_frame.resize((128, 156), Image.NEAREST)
                        runtime_bbox = runtime_frame.getchannel("A").getbbox()

                        with self.subTest(skin=skin_name, action=action, frame=frame_index):
                            self._assert_frame_matches_raw_canvas(generated_frame, raw_frame)
                            self.assertIsNotNone(runtime_bbox)
                            self.assertGreaterEqual(runtime_bbox[2] - runtime_bbox[0], 85)
                            self.assertGreaterEqual(runtime_bbox[3] - runtime_bbox[1], 144)
                            self.assertLessEqual(runtime_bbox[2], 128)
                            self.assertLessEqual(runtime_bbox[3], 156)

    def test_generated_agent_frames_match_ameath_budget(self):
        for skin_name in ("asuka_agent", "rei_agent"):
            self._assert_generated_agent_frames_match_ameath_budget(skin_name)

if __name__ == "__main__":
    unittest.main()
