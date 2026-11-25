import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import main
from integrations import personal_outlook_mcp


class OutlookSentVerificationTests(unittest.TestCase):

    def test_sent_timestamp_must_be_recent_and_parseable(self):
        started_at = datetime.now(timezone.utc).timestamp()

        self.assertTrue(
            main.GHOSTLive._outlook_sent_timestamp_matches(
                datetime.fromtimestamp(started_at, timezone.utc).isoformat(),
                started_at,
            )
        )
        self.assertFalse(
            main.GHOSTLive._outlook_sent_timestamp_matches(
                (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
                started_at,
            )
        )
        self.assertFalse(
            main.GHOSTLive._outlook_sent_timestamp_matches(
                "not-a-timestamp",
                started_at,
            )
        )
        self.assertFalse(
            main.GHOSTLive._outlook_sent_timestamp_matches(None, started_at)
        )

    def test_empty_initial_search_retries_read_only_and_confirms_sent_message(self):
        live = main.GHOSTLive(MagicMock())
        snapshot = {
            "id": "draft-1",
            "is_draft": True,
            "is_draft_available": True,
            "subject": "Verification test",
            "body": "Test body",
            "to_available": True,
            "cc_available": True,
            "bcc_available": True,
            "to": [{"email": "recipient@example.com"}],
            "cc": [],
            "bcc": [],
        }
        live._remember_reviewed_outlook_draft("draft-1", snapshot)
        live._pending_human_action = {
            "name": "personal_outlook",
            "args": {
                "tool_name": "outlook_send_draft",
                "arguments": {"draft_id": "draft-1"},
            },
        }
        live._pending_confirmation_token = "test-token"

        live._execute_tool = AsyncMock(
            return_value=SimpleNamespace(
                response={"result": json.dumps({"status": "sent"})}
            )
        )

        sent_message = {
            "id": "sent-1",
            "subject": "Verification test",
            "to": [{"email": "recipient@example.com"}],
            "cc": [],
            "bcc": [],
            "sent": datetime.now(timezone.utc).isoformat(),
            "is_draft": False,
        }
        search_responses = iter((
            {"messages": [], "has_more": False},
            {"messages": [{"id": "sent-1"}], "has_more": False},
        ))
        calls = []

        def mock_outlook_action(args):
            tool_name = args["tool_name"]
            calls.append(tool_name)
            if tool_name == "outlook_read_message":
                message_id = args["arguments"]["message_id"]
                if message_id == "draft-1":
                    return json.dumps(snapshot)
                return json.dumps(sent_message)
            if tool_name == "outlook_search_mail":
                return json.dumps(next(search_responses))
            raise AssertionError(f"Unexpected Outlook tool: {tool_name}")

        async def mock_to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        async def run():
            with (
                patch.object(
                    personal_outlook_mcp,
                    "personal_outlook_action",
                    side_effect=mock_outlook_action,
                ),
                patch.object(main.asyncio, "to_thread", side_effect=mock_to_thread),
                patch.object(main.asyncio, "sleep", new=AsyncMock()),
            ):
                await live._run_approved_pending_action()

        asyncio.run(run())

        logged_result = live.ui.write_log.call_args.args[0]
        self.assertIn("Verified:", logged_result)
        self.assertIn("recent sent timestamp", logged_result)
        self.assertEqual(calls.count("outlook_search_mail"), 2)
        self.assertEqual(calls.count("outlook_read_message"), 2)
        live._execute_tool.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
