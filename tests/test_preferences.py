import unittest

from core.preferences import (
    VOICE_NAMES,
    _get_style_from_memory,
    _get_voice_from_memory,
    _normalize_mode,
    _normalize_voice,
)


class PreferenceTests(unittest.TestCase):

    def test_normalizes_mode_aliases_and_rejects_unknown_values(self):
        self.assertEqual(_normalize_mode("Crazy Friend"), "crazy_friend")
        self.assertEqual(_normalize_mode("romantic"), "girlfriend")
        self.assertEqual(_normalize_mode("not a mode"), "")

    def test_normalizes_voice_aliases_and_rejects_unknown_values(self):
        self.assertEqual(_normalize_voice("erkak"), "Charon")
        self.assertEqual(_normalize_voice("zephyr"), "Zephyr")
        self.assertEqual(_normalize_voice("not a voice"), "")
        self.assertIn("Aoede", VOICE_NAMES)

    def test_reads_saved_preferences_and_uses_defaults(self):
        memory = {
            "preferences": {
                "assistant_mode": {"value": "butler"},
                "assistant_mood": "playful",
                "assistant_voice": {"value": "Kore"},
            }
        }

        self.assertEqual(_get_style_from_memory(memory), ("butler", "playful"))
        self.assertEqual(_get_voice_from_memory(memory), "Kore")
        self.assertEqual(_get_style_from_memory(None), ("normal", "calm"))
        self.assertEqual(_get_voice_from_memory(None), "Aoede")


if __name__ == "__main__":
    unittest.main()
