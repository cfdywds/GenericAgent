import json
import pathlib
import unittest

from PIL import Image


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIN_DIR = ROOT / "frontends" / "skins" / "hongkongdoll-3d"
CELL_SIZE = (192, 208)
USED_COLUMNS = (6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)


class HongkongdollSkinTests(unittest.TestCase):
    def test_manifest_and_atlases_follow_the_v2_contract(self):
        manifest = json.loads((SKIN_DIR / "pet.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["spriteVersionNumber"], 2)
        self.assertEqual(manifest["spritesheetPath"], "spritesheet.webp")

        for name in ("spritesheet.png", "spritesheet.webp"):
            with Image.open(SKIN_DIR / name) as atlas:
                self.assertEqual(atlas.size, (1536, 2288))
                rgba = atlas.convert("RGBA")
                for row, used_columns in enumerate(USED_COLUMNS):
                    for column in range(8):
                        cell = rgba.crop((
                            column * CELL_SIZE[0],
                            row * CELL_SIZE[1],
                            (column + 1) * CELL_SIZE[0],
                            (row + 1) * CELL_SIZE[1],
                        ))
                        has_pixels = cell.getchannel("A").getbbox() is not None
                        if column < used_columns:
                            self.assertTrue(has_pixels, f"{name} row {row} column {column} is empty")
                        else:
                            self.assertFalse(has_pixels, f"{name} row {row} column {column} is not transparent")


if __name__ == "__main__":
    unittest.main()
