import unittest
from unittest.mock import MagicMock, patch

from actions import screen_processor


class ScreenProcessorTests(unittest.TestCase):
    def test_screen_analysis_uses_the_available_flash_model_by_default(self):
        client = MagicMock()
        client.models.generate_content.return_value.text = "A mail compose window."

        with patch.object(
            screen_processor, "_get_api_key", return_value="test-key"
        ), patch.object(
            screen_processor.genai, "Client", return_value=client
        ):
            result = screen_processor._analyze_image_text(
                b"image", "image/png", "Where is the send button?"
            )

        self.assertEqual(result, "A mail compose window.")
        self.assertEqual(
            client.models.generate_content.call_args.kwargs["model"],
            "gemini-3.8-flash",
        )


if __name__ == "__main__":
    unittest.main()
