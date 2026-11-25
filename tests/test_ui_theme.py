import json
import tempfile
import unittest
from pathlib import Path

from ui_theme import (
    DEFAULT_BRAND,
    load_brand,
    load_theme_name,
    save_theme_name,
)


class UIThemeTests(unittest.TestCase):

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
        self.assertNotIn("unknown", brand)
        self.assertEqual(brand["panels"], DEFAULT_BRAND["panels"])


if __name__ == "__main__":
    unittest.main()
