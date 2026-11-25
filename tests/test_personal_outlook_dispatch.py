import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import main
import safety
from integrations import personal_outlook_mcp as outlook
from safety import _fingerprint, issue_confirmation_token
from agent.outlook_approval import OUTLOOK_APPROVAL_CAPABILITY


class PersonalOutlookDispatchTests(unittest.TestCase):

    def _args(self):
        return {
            "action": "call",
            "tool_name": "outlook_send_draft",
            "arguments": {"draft_id": "MOCK_DRAFT_ID"},
        }

    def test_telegram_approved_action_uses_private_capability(self):
        live = main.GHOSTLive(MagicMock())
        args = self._args()

        fingerprint = _fingerprint("personal_outlook", args)
        token = issue_confirmation_token("personal_outlook", args)

        live._approved_human_fingerprint = fingerprint
        live._pending_confirmation_token = token

        async def run():
            with patch.object(
                outlook,
                "_personal_outlook_action_approved",
                return_value="mock-approved",
            ) as approved:
                result = await live._dispatch_tool(
                    "personal_outlook",
                    {
                        **args,
                        "confirm": True,
                        "confirm_token": token,
                    },
                )

            approved.assert_called_once()
            call = approved.call_args

            self.assertEqual(call.args[0]["tool_name"], "outlook_send_draft")
            self.assertIs(
                call.args[1],
                outlook._PERSONAL_OUTLOOK_APPROVAL_CAPABILITY,
            )
            self.assertTrue(result.ok)

        asyncio.run(run())

    def test_voice_approved_action_uses_private_capability(self):
        live = main.GHOSTLive(MagicMock())
        args = self._args()

        fingerprint = _fingerprint("personal_outlook", args)
        token = issue_confirmation_token("personal_outlook", args)

        live._approved_human_fingerprint = fingerprint
        live._pending_confirmation_token = token

        fc = SimpleNamespace(
            id="mock-call-id",
            name="personal_outlook",
            args={
                **args,
                "confirm": True,
                "confirm_token": token,
            },
        )

        async def run():
            with patch.object(
                outlook,
                "_personal_outlook_action_approved",
                return_value="mock-approved",
            ) as approved:
                result = await live._execute_tool(fc)

            approved.assert_called_once()
            call = approved.call_args

            self.assertEqual(call.args[0]["tool_name"], "outlook_send_draft")
            self.assertIs(
                call.args[1],
                outlook._PERSONAL_OUTLOOK_APPROVAL_CAPABILITY,
            )
            self.assertEqual(result.response["result"], "mock-approved")

        asyncio.run(run())

    def test_voice_without_approval_does_not_execute_outlook(self):
        live = main.GHOSTLive(MagicMock())

        fc = SimpleNamespace(
            id="mock-call-id",
            name="personal_outlook",
            args=self._args(),
        )

        async def run():
            with patch.object(
                outlook,
                "_personal_outlook_action_approved",
            ) as approved:
                result = await live._execute_tool(fc)

            approved.assert_not_called()
            self.assertIn(
                "requires your permission",
                result.response["result"].lower(),
            )
            self.assertIn("[token:", result.response["result"].lower())

        asyncio.run(run())


    def test_voice_blocks_dispatch_while_approved_action_running(self):
        live = main.GHOSTLive(MagicMock())
        live._approved_action_running = True

        fc = SimpleNamespace(
            id="voice-concurrency-test",
            name="personal_outlook",
            args={"action": "list_tools"},
        )

        async def run():
            with patch.object(
                outlook,
                "_personal_outlook_action_approved",
            ) as approved:
                result = await live._execute_tool(fc)

            approved.assert_not_called()
            self.assertIn(
                "already executing",
                result.response["result"].lower(),
            )

        asyncio.run(run())

    def test_voice_pending_action_blocks_different_outlook_action(self):
        live = main.GHOSTLive(MagicMock())

        args_a = self._args()

        args_b = {
            "action": "call",
            "tool_name": "outlook_delete_draft",
            "arguments": {"draft_id": "OTHER_MOCK_DRAFT_ID"},
        }

        fc_a = SimpleNamespace(
            id="voice-action-a",
            name="personal_outlook",
            args=args_a,
        )

        fc_b = SimpleNamespace(
            id="voice-action-b",
            name="personal_outlook",
            args=args_b,
        )

        async def run():
            # A requests approval first.
            result_a = await live._execute_tool(fc_a)

            self.assertIn(
                "requires your permission",
                result_a.response["result"].lower(),
            )

            original_fingerprint = live._pending_human_fingerprint
            original_action = live._pending_human_action.copy()
            original_token = live._pending_confirmation_token

            self.assertIsNotNone(original_token)
            self.assertTrue(live._awaiting_human_confirmation)

            # B must not replace or bypass A's pending approval.
            with patch.object(
                outlook,
                "_personal_outlook_action_approved",
            ) as approved:
                result_b = await live._execute_tool(fc_b)

                approved.assert_not_called()

            self.assertIn(
                "another action is awaiting confirmation",
                result_b.response["result"].lower(),
            )

            self.assertEqual(
                live._pending_human_fingerprint,
                original_fingerprint,
            )
            self.assertEqual(
                live._pending_human_action,
                original_action,
            )
            self.assertEqual(
                live._pending_confirmation_token,
                original_token,
            )
            self.assertTrue(live._awaiting_human_confirmation)
            self.assertIsNone(live._approved_human_fingerprint)

        asyncio.run(run())


    def test_telegram_pending_approval_blocks_different_voice_action(self):
        live = main.GHOSTLive(MagicMock())
        executed = []

        async def run():
            live._loop = asyncio.get_running_loop()

            with patch.dict(
                live._tool_handlers,
                {
                    "cmd_control": (
                        lambda a: executed.append(dict(a)) or "Executed",
                        10,
                    )
                },
            ):
                # Telegram requests Action A.
                telegram_result = await live._dispatch_tool(
                    "cmd_control",
                    {"command": "dir"},
                )

                self.assertIn(
                    "permission",
                    str(telegram_result.content).lower(),
                )

                original_fingerprint = live._pending_human_fingerprint
                original_action = live._pending_human_action.copy()
                original_token = live._pending_confirmation_token

                self.assertIsNotNone(original_token)
                self.assertTrue(live._awaiting_human_confirmation)

                # Voice requests a different Action B.
                voice_fc = SimpleNamespace(
                    id="cross-channel-voice",
                    name="cmd_control",
                    args={"command": "whoami"},
                )

                voice_result = await live._execute_tool(voice_fc)

                self.assertIn(
                    "another action is awaiting confirmation",
                    voice_result.response["result"].lower(),
                )

                # Telegram's original pending approval must survive.
                self.assertEqual(
                    live._pending_human_fingerprint,
                    original_fingerprint,
                )
                self.assertEqual(
                    live._pending_human_action,
                    original_action,
                )
                self.assertEqual(
                    live._pending_confirmation_token,
                    original_token,
                )
                self.assertTrue(live._awaiting_human_confirmation)
                self.assertEqual(executed, [])

        asyncio.run(run())


    def test_voice_expired_approval_cannot_execute_and_cleans_state(self):
        live = main.GHOSTLive(MagicMock())
        args = {"command": "dir"}
        fingerprint = _fingerprint("cmd_control", args)
        executed = []
        captured_responses = []

        live._pending_human_action = {
            "name": "cmd_control",
            "args": dict(args),
        }
        live._approved_human_fingerprint = fingerprint
        live._pending_human_fingerprint = None
        live._awaiting_human_confirmation = False
        live._human_confirmed = True
        live._approved_action_running = True

        async def run():
            live._loop = asyncio.get_running_loop()

            with patch.dict(
                live._tool_handlers,
                {
                    "cmd_control": (
                        lambda a: executed.append(dict(a)) or "Executed",
                        10,
                    )
                },
            ):
                original_execute = live._execute_tool

                async def capture_execute(*call_args, **call_kwargs):
                    response = await original_execute(
                        *call_args, **call_kwargs
                    )
                    captured_responses.append(response)
                    return response

                with patch.object(
                    safety.time,
                    "monotonic",
                    side_effect=[100.0, 701.0],
                ):
                    token = issue_confirmation_token(
                        "cmd_control", args
                    )
                    live._pending_confirmation_token = token

                    with patch.object(
                        live,
                        "_execute_tool",
                        side_effect=capture_execute,
                    ):
                        await live._run_approved_pending_action()

        asyncio.run(run())

        self.assertEqual(executed, [])
        self.assertEqual(len(captured_responses), 1)

        response_text = str(
            captured_responses[0].response.get("result", "")
        ).lower()

        self.assertIn("expired", response_text)

        self.assertIsNone(live._pending_human_action)
        self.assertIsNone(live._pending_human_fingerprint)
        self.assertIsNone(live._approved_human_fingerprint)
        self.assertIsNone(live._pending_confirmation_token)
        self.assertFalse(live._awaiting_human_confirmation)
        self.assertFalse(live._human_confirmed)
        self.assertFalse(live._approved_action_running)


    def test_expired_token_cannot_authorize_fresh_request(self):
        old_args = {"command": "old_action"}
        new_args = {"command": "new_action"}

        with patch.object(
            safety.time,
            "monotonic",
            side_effect=[100.0, 701.0, 702.0, 703.0],
        ):
            # First request receives its own token.
            old_token = issue_confirmation_token(
                "cmd_control", old_args
            )

            # Old token expires and is rejected.
            self.assertTrue(
                safety.needs_confirmation(
                    "cmd_control",
                    old_args,
                    confirm=True,
                    confirm_token=old_token,
                )
            )

            # A fresh request receives a different token.
            new_token = issue_confirmation_token(
                "cmd_control", new_args
            )

            self.assertNotEqual(old_token, new_token)

            # Replaying the old token cannot authorize the new action.
            self.assertTrue(
                safety.needs_confirmation(
                    "cmd_control",
                    new_args,
                    confirm=True,
                    confirm_token=old_token,
                )
            )

            # Only the fresh token authorizes the exact new action.
            self.assertFalse(
                safety.needs_confirmation(
                    "cmd_control",
                    new_args,
                    confirm=True,
                    confirm_token=new_token,
                )
            )


    def test_concurrent_voice_requests_preserve_single_pending_approval(self):
        live = main.GHOSTLive(MagicMock())

        args_a = self._args()
        args_b = {
            "action": "call",
            "tool_name": "outlook_delete_draft",
            "arguments": {"draft_id": "OTHER_MOCK_DRAFT_ID"},
        }

        fc_a = SimpleNamespace(
            id="concurrent-a",
            name="personal_outlook",
            args=args_a,
        )
        fc_b = SimpleNamespace(
            id="concurrent-b",
            name="personal_outlook",
            args=args_b,
        )

        async def run():
            # Both requests start together. The first coroutine to enter
            # the dispatcher establishes the pending approval.
            results = await asyncio.gather(
                live._execute_tool(fc_a),
                live._execute_tool(fc_b),
            )

            self.assertEqual(len(results), 2)

            pending_fingerprint = live._pending_human_fingerprint
            pending_action = live._pending_human_action
            pending_token = live._pending_confirmation_token

            self.assertIsNotNone(pending_fingerprint)
            self.assertIsNotNone(pending_action)
            self.assertIsNotNone(pending_token)

            # Exactly one request must own the pending approval.
            expected = [
                _fingerprint("personal_outlook", args_a),
                _fingerprint("personal_outlook", args_b),
            ]
            self.assertIn(pending_fingerprint, expected)

            self.assertEqual(
                pending_action["args"],
                args_a if pending_fingerprint == expected[0] else args_b,
            )

            self.assertTrue(live._awaiting_human_confirmation)

            # The competing request must not replace the original token.
            token_before = pending_token
            self.assertEqual(live._pending_confirmation_token, token_before)

            # No Outlook mutation may execute without human approval.
            self.assertIsNone(live._approved_human_fingerprint)

        with patch.object(
            outlook,
            "_personal_outlook_action_approved",
        ) as approved:
            asyncio.run(run())
            approved.assert_not_called()


    def test_telegram_legacy_send_reply_passes_approval_and_cleans_state(self):
        live = main.GHOSTLive(MagicMock())
        args = {
            "action": "send_reply",
            "draft_id": "MOCK_DRAFT_ID",
            "draft_hash": "mock-draft-hash",
        }

        fingerprint = _fingerprint("outlook", args)
        token = issue_confirmation_token("outlook", args)
        captured = []

        live._approved_human_fingerprint = fingerprint
        live._pending_human_fingerprint = fingerprint
        live._pending_confirmation_token = token
        live._pending_human_action = {
            "name": "outlook",
            "args": dict(args),
        }
        live._awaiting_human_confirmation = True
        live._human_confirmed = True

        def mock_outlook_handler(received_args):
            captured.append(dict(received_args))
            return "mock-handler-success"

        fc = SimpleNamespace(
            id="mock-legacy-send-reply",
            name="outlook",
            args={
                **args,
                "confirm": True,
                "confirm_token": token,
            },
        )

        async def run():
            with patch.dict(
                live._tool_handlers,
                {"outlook": (mock_outlook_handler, 10)},
            ):
                return await live._execute_tool(fc)

        result = asyncio.run(run())

        self.assertTrue(result.response["result"] == "mock-handler-success")
        self.assertEqual(len(captured), 1)
        self.assertIs(captured[0].get("_ghost_safety_approved"), OUTLOOK_APPROVAL_CAPABILITY)

        self.assertIsNone(live._approved_human_fingerprint)
        self.assertIsNone(live._pending_confirmation_token)
        self.assertIsNone(live._pending_human_fingerprint)
        self.assertIsNone(live._pending_human_action)
        self.assertFalse(live._awaiting_human_confirmation)
        self.assertFalse(live._human_confirmed)


if __name__ == "__main__":
    unittest.main()
class ReviewedDraftBindingTests(unittest.TestCase):

    def _snapshot(self, **changes):
        snapshot = {
            "id": "draft-123",
            "is_draft": True,
            "is_draft_available": True,
            "subject": "Greetings",
            "body": "Good News",
            "to_available": True,
            "cc_available": True,
            "bcc_available": True,
            "to": [{"email": "sefatamed3674@gmail.com"}],
            "cc": [],
            "bcc": [],
        }
        snapshot.update(changes)
        return snapshot

    def test_remembers_only_complete_reviewed_draft(self):
        live = main.GHOSTLive(MagicMock())
        snapshot = self._snapshot()

        self.assertTrue(live._remember_reviewed_outlook_draft("draft-123", snapshot))
        self.assertEqual(
            live._reviewed_outlook_drafts["draft-123"],
            live._outlook_draft_review_signature(snapshot),
        )

    def test_rejects_incomplete_or_non_draft_review(self):
        live = main.GHOSTLive(MagicMock())
        self.assertFalse(live._remember_reviewed_outlook_draft("draft-1", {"is_draft": False}))
        self.assertFalse(live._remember_reviewed_outlook_draft("draft-2", self._snapshot(body=None)))
        self.assertEqual(live._reviewed_outlook_drafts, {})

    def test_signature_changes_for_recipient_subject_or_body(self):
        original = self._snapshot()
        signature = main.GHOSTLive._outlook_draft_review_signature(original)
        for changed in (
            self._snapshot(subject="Different subject"),
            self._snapshot(body="Different body"),
            self._snapshot(to=[{"email": "attacker@example.com"}]),
            self._snapshot(cc=[{"email": "copy@example.com"}]),
            self._snapshot(bcc=[{"email": "hidden@example.com"}]),
        ):
            self.assertNotEqual(
                signature,
                main.GHOSTLive._outlook_draft_review_signature(changed),
            )
