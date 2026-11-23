"""Tests for safety.py — risk classification, confirmation gate, sanitization.

Run: python -m unittest tests.test_safety -v
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import safety


class RiskClassificationTest(unittest.TestCase):

    def test_low_risk_read_only(self):
        self.assertEqual(safety.classify("web_search", {}), safety.Risk.LOW)
        self.assertEqual(safety.classify("system_status", {}), safety.Risk.LOW)

    def test_personal_outlook_preview_move_is_low(self):
        self.assertEqual(
            safety.classify(
                "personal_outlook",
                {"action": "preview_move"},
            ),
            safety.Risk.LOW,
        )

    def test_personal_outlook_mutation_stays_high(self):
        self.assertEqual(
            safety.classify(
                "personal_outlook",
                {
                    "action": "call",
                    "tool_name": "outlook_move_message",
                },
            ),
            safety.Risk.HIGH,
        )

    def test_file_delete_is_high(self):
        self.assertEqual(
            safety.classify("file_controller", {"action": "delete", "name": "x.txt"}),
            safety.Risk.HIGH,
        )

    def test_file_read_not_high(self):
        self.assertNotEqual(
            safety.classify("file_controller", {"action": "read", "name": "x.txt"}),
            safety.Risk.HIGH,
        )

    def test_terminal_is_high(self):
        self.assertEqual(safety.classify("cmd_control", {"command": "dir"}), safety.Risk.HIGH)

    def test_gmail_send_high_read_low(self):
        self.assertEqual(safety.classify("gmail", {"action": "send"}), safety.Risk.HIGH)
        self.assertEqual(safety.classify("gmail", {"action": "read"}), safety.Risk.LOW)

    def test_task_manager_kill_high(self):
        self.assertEqual(safety.classify("task_manager", {"action": "kill"}), safety.Risk.HIGH)

    def test_open_app_medium(self):
        self.assertEqual(safety.classify("open_app", {"app_name": "Chrome"}), safety.Risk.MEDIUM)

    def test_unknown_tool_defaults_to_medium(self):
        self.assertEqual(safety.classify("totally_unknown_tool", {}), safety.Risk.MEDIUM)


class ConfirmationTest(unittest.TestCase):

    def test_high_needs_confirmation(self):
        self.assertTrue(safety.needs_confirmation("cmd_control", {"command": "dir"}))

    def test_low_does_not_need_confirmation(self):
        self.assertFalse(safety.needs_confirmation("web_search", {"query": "x"}))

    def test_confirm_flag_alone_does_not_bypass(self):
        # confirm=true with no valid token no longer bypasses the gate.
        self.assertTrue(
            safety.needs_confirmation("cmd_control", {"command": "dir"}, confirm=True)
        )


class ConfirmationTokenTest(unittest.TestCase):
    """Technical enforcement: confirm=true alone is not enough; a one-time
    token issued for the exact blocked call is required."""

    def test_confirm_without_token_is_blocked(self):
        # confirm=true with no token must NOT bypass the gate.
        self.assertTrue(
            safety.needs_confirmation("cmd_control", {"command": "dir"},
                                      confirm=True, confirm_token="")
        )
        self.assertTrue(
            safety.needs_confirmation("cmd_control", {"command": "dir"},
                                      confirm=True, confirm_token="garbage")
        )

    def test_issued_token_works_once(self):
        tok = safety.issue_confirmation_token("cmd_control", {"command": "dir"})
        # First redeem succeeds (and consumes the token).
        self.assertFalse(
            safety.needs_confirmation("cmd_control", {"command": "dir"},
                                      confirm=True, confirm_token=tok)
        )
        # Second use fails — token is single-use.
        self.assertTrue(
            safety.needs_confirmation("cmd_control", {"command": "dir"},
                                      confirm=True, confirm_token=tok)
        )

    def test_token_bound_to_exact_call(self):
        tok = safety.issue_confirmation_token("cmd_control", {"command": "dir"})
        # Different args -> blocked.
        self.assertTrue(
            safety.needs_confirmation("cmd_control", {"command": "format c:"},
                                      confirm=True, confirm_token=tok)
        )
        # Different tool -> blocked.
        self.assertTrue(
            safety.needs_confirmation("desktop_control", {"action": "reset"},
                                      confirm=True, confirm_token=tok)
        )

    def test_low_risk_never_asks_for_token(self):
        self.assertFalse(
            safety.needs_confirmation("web_search", {"query": "x"},
                                      confirm=True, confirm_token="nope")
        )


    def test_expired_token_is_rejected(self):
        # Simulate a token that is 11 seconds old with a 10-second TTL.
        with patch.object(safety, "_TOKEN_TTL_SECONDS", 10):
            with patch.object(
                safety.time, "monotonic",
                side_effect=[100.0, 111.0]
            ):
                token = safety.issue_confirmation_token(
                    "cmd_control", {"command": "dir"}
                )

                self.assertFalse(
                    safety.redeem_confirmation_token(
                        "cmd_control", {"command": "dir"}, token
                    )
                )


    def test_concurrent_token_redemption_succeeds_exactly_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        token = safety.issue_confirmation_token(
            "cmd_control",
            {"command": "dir"},
        )

        barrier = Barrier(2)

        def redeem():
            barrier.wait(timeout=5)
            return safety.redeem_confirmation_token(
                "cmd_control",
                {"command": "dir"},
                token,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(redeem),
                executor.submit(redeem),
            ]
            results = [future.result(timeout=10) for future in futures]

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 1)



class DescribeTest(unittest.TestCase):

    def test_delete_description(self):
        desc = safety.describe("file_controller", {"action": "delete", "name": "notes.txt"})
        self.assertIn("delete notes.txt", desc)

    def test_command_description(self):
        desc = safety.describe("cmd_control", {"command": "dir"})
        self.assertIn("dir", desc)

    def test_outlook_send_draft_description_includes_exact_draft_id(self):
        draft_id = "AQMk_TEST_EXACT_DRAFT_ID_123"

        desc = safety.describe(
            "personal_outlook",
            {
                "action": "call",
                "tool_name": "outlook_send_draft",
                "arguments": {
                    "draft_id": draft_id,
                },
            },
        )

        self.assertIn("send the selected Personal Outlook draft", desc)
        self.assertIn(draft_id, desc)


class SanitizeTest(unittest.TestCase):

    def test_api_key_masked(self):
        out = safety.sanitize("api_add_key", {"key": "AIzaSyB-...", "note": "hi"})
        self.assertEqual(out["key"], "***")
        self.assertEqual(out["note"], "hi")

    def test_token_masked(self):
        out = safety.sanitize("any", {"access_token": "abc123", "path": "C:/x"})
        self.assertEqual(out["access_token"], "***")
        self.assertEqual(out["path"], "C:/x")


if __name__ == "__main__":
    unittest.main()

# PERSONAL_OUTLOOK_DRAFT_SAFETY_REGRESSION_TESTS
class PersonalOutlookDraftSafetyRegressionTest(unittest.TestCase):
    def test_listing_and_reading_drafts_are_low_risk(self):
        from safety import classify, Risk

        for tool_name in (
            "outlook_list_drafts",
            "outlook_read_message",
        ):
            with self.subTest(tool=tool_name):
                self.assertEqual(
                    classify(
                        "personal_outlook",
                        {"action": "call", "tool_name": tool_name, "arguments": {}},
                    ),
                    Risk.LOW,
                )

    def test_creating_draft_is_low_risk(self):
        from safety import classify, Risk

        self.assertEqual(
            classify(
                "personal_outlook",
                {
                    "action": "call",
                    "tool_name": "outlook_create_draft",
                    "arguments": {},
                },
            ),
            Risk.LOW,
        )

    def test_other_draft_mutations_are_high_risk(self):
        from safety import classify, Risk

        for tool_name in (
            "outlook_update_draft",
            "outlook_send_draft",
            "outlook_delete_draft",
            "outlook_attach_to_draft",
            "outlook_remove_draft_attachment",
        ):
            with self.subTest(tool=tool_name):
                self.assertEqual(
                    classify(
                        "personal_outlook",
                        {"action": "call", "tool_name": tool_name, "arguments": {}},
                    ),
                    Risk.HIGH,
                )
