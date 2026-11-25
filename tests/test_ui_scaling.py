import os
import unittest
from unittest.mock import patch

from ui.scaling import HiDPICanvas, pick_scale, px, set_ui_scale


class UIScalingTests(unittest.TestCase):

    def test_px_scales_numbers_and_nested_sequences(self):
        set_ui_scale(2.0)
        try:
            self.assertEqual(px(3), 6)
            self.assertEqual(px((2, [3, 4])), (4, (6, 8)))
        finally:
            set_ui_scale(1.0)

    def test_pick_scale_honors_valid_environment_override(self):
        with patch.dict(os.environ, {"GHOST_UI_SCALE": "2.5"}):
            self.assertEqual(pick_scale(1920, 1080, 96), 2.5)

    def test_canvas_coordinates_are_scaled(self):
        class CanvasStub:
            _k = 2.0
            _scaled = HiDPICanvas._scaled

        self.assertEqual(
            CanvasStub()._scaled((10, (2, 3), "north")),
            [20.0, 4.0, 6.0, "north"],
        )


if __name__ == "__main__":
    unittest.main()
