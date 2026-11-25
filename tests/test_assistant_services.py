import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import assistant_services


class AssistantServicesTests(unittest.TestCase):

    def setUp(self):
        self.previous_input = assistant_services._last_memory_input
        self.previous_running = assistant_services._memory_running
        assistant_services._last_memory_input = ""
        assistant_services._memory_running = False

    def tearDown(self):
        assistant_services._last_memory_input = self.previous_input
        assistant_services._memory_running = self.previous_running

    def test_loads_prompt_and_uses_fallback_when_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt_path = Path(directory) / "prompt.txt"
            prompt_path.write_text("Test prompt", encoding="utf-8")
            self.assertEqual(
                assistant_services.load_system_prompt(prompt_path),
                "Test prompt",
            )

        fallback = assistant_services.load_system_prompt(
            Path(directory) / "missing.txt"
        )
        self.assertIn("You are GHOST", fallback)

    def test_memory_extraction_saves_detected_data(self):
        memory_data = {"preferences": {"assistant_mode": "friendly"}}
        with (
            patch.object(assistant_services, "get_api_key", return_value="key"),
            patch.object(
                assistant_services,
                "should_extract_memory",
                return_value=True,
            ) as detect,
            patch.object(
                assistant_services,
                "extract_memory",
                return_value=memory_data,
            ) as extract,
            patch.object(assistant_services, "update_memory") as save,
        ):
            assistant_services.update_memory_async(
                "I prefer friendly responses",
                "I will remember that.",
            )

        detect.assert_called_once_with(
            "I prefer friendly responses",
            "I will remember that.",
            "key",
        )
        extract.assert_called_once_with(
            "I prefer friendly responses",
            "I will remember that.",
            "key",
        )
        save.assert_called_once_with(memory_data)
        self.assertFalse(assistant_services._memory_running)

    def test_skips_short_and_duplicate_memory_inputs(self):
        assistant_services._last_memory_input = "Repeated user statement"

        with patch.object(assistant_services, "should_extract_memory") as detect:
            assistant_services.update_memory_async("hey", "response")
            assistant_services.update_memory_async(
                "Repeated user statement",
                "response",
            )

        detect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
