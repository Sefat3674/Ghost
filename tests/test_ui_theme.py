import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ui
from ui import GHOSTUI, get_base_dir
from ui.theme import (
    DEFAULT_BRAND,
    load_brand,
    load_theme_name,
    save_theme_name,
)


class UIThemeTests(unittest.TestCase):

    def test_base_directory_is_project_root(self):
        self.assertEqual(get_base_dir(), Path(__file__).resolve().parents[1])

    def test_theme_loading_defaults_and_rejects_unknown_names(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory)
            theme_file = config_dir / "ui_theme.json"

            self.assertEqual(load_theme_name(theme_file), "pran")

            theme_file.write_text(
                json.dumps({"theme": "ocean"}),
                encoding="utf-8",
            )
            self.assertEqual(load_theme_name(theme_file), "ocean")

            theme_file.write_text(
                json.dumps({"theme": "unknown"}),
                encoding="utf-8",
            )
            self.assertEqual(load_theme_name(theme_file), "pran")

    def test_theme_saving_creates_config_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory) / "config"
            theme_file = config_dir / "ui_theme.json"

            save_theme_name("aurora", config_dir, theme_file)

            self.assertEqual(
                json.loads(theme_file.read_text(encoding="utf-8")),
                {"theme": "aurora"},
            )

    def test_brand_loading_overrides_known_values_and_validates_panels(self):
        with tempfile.TemporaryDirectory() as directory:
            brand_file = Path(directory) / "brand.json"
            brand_file.write_text(
                json.dumps({
                    "company": "Test Company",
                    "unknown": "ignored",
                    "panels": ["Only one"],
                }),
                encoding="utf-8",
            )

            brand = load_brand(brand_file)

        self.assertEqual(brand["company"], "Test Company")
        self.assertEqual(brand["division"], "")
        self.assertNotIn("unknown", brand)
        self.assertEqual(brand["panels"], DEFAULT_BRAND["panels"])

    def test_logo_loads_without_optional_pillow(self):
        class FakePhotoImage:
            def __init__(self, width=296, height=115):
                self._width = width
                self._height = height
                self.subsample_calls = []

            def width(self):
                return self._width

            def height(self):
                return self._height

            def subsample(self, x, y):
                self.subsample_calls.append((x, y))
                self._width = max(1, self._width // x)
                self._height = max(1, self._height // y)
                return self

        ghost_ui = object.__new__(GHOSTUI)
        ghost_ui.brand = {"logo": "assets/pran_rfl_logo.png"}
        ghost_ui.S = 1.0
        image = FakePhotoImage()

        with (
            patch.object(ui, "Image", None),
            patch.object(ui, "ImageTk", None),
            patch.object(ui.tk, "PhotoImage", return_value=image) as photo_image,
        ):
            ghost_ui._load_logo()

        photo_image.assert_called_once()
        self.assertIs(ghost_ui._logo, image)
        self.assertEqual(image.subsample_calls, [(3, 3)])
        self.assertEqual(ghost_ui._logo_w, 98)


if __name__ == "__main__":
    unittest.main()
