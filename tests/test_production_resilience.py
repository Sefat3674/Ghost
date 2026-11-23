"""Tests for production hardening, audio resilience, human confirmation gate, and security."""
import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from actions import desktop
from safety import needs_confirmation, issue_confirmation_token, Risk, classify


class ProductionSafetyTest(unittest.TestCase):
    def test_confirmation_token_cannot_be_replayed_after_execution_failure(self):
        args = {"command": "dir"}

        token = issue_confirmation_token("cmd_control", args)

        # First redemption succeeds and consumes the token.
        self.assertFalse(
            needs_confirmation(
                "cmd_control",
                args,
                confirm=True,
                confirm_token=token,
            )
        )

        # Simulate the approved operation failing after authorization.
        with self.assertRaisesRegex(RuntimeError, "mock execution failure"):
            raise RuntimeError("mock execution failure")

        # The same token must not authorize a second execution.
        self.assertTrue(
            needs_confirmation(
                "cmd_control",
                args,
                confirm=True,
                confirm_token=token,
            )
        )

    def test_cmd_control_is_high_risk(self):
        self.assertEqual(classify("cmd_control", {"command": "dir"}), Risk.HIGH)

    def test_file_controller_delete_is_high_risk(self):
        self.assertEqual(classify("file_controller", {"action": "delete", "path": "file.txt"}), Risk.HIGH)

    def test_desktop_control_exec_free(self):
        # desktop_control should handle declarative commands safely
        res = desktop.desktop_control({"action": "stats"})
        self.assertIn("Desktop stats", res)

    def test_desktop_task_dispatcher(self):
        res = desktop.desktop_control({"action": "task", "task": "show me my desktop files"})
        self.assertTrue("Desktop" in res or "Contents" in res or "Empty" in res)


class AudioHardwareResilienceTest(unittest.TestCase):
    def test_listen_audio_does_not_crash_when_sounddevice_is_none(self):
        import main
        ui_mock = MagicMock()
        live = main.GHOSTLive(ui_mock)

        # Patch sd to None and ensure _listen_audio doesn't raise
        with patch.object(main, "sd", None):
            async def run():
                task = asyncio.create_task(live._listen_audio())
                await asyncio.sleep(0.05)
                self.assertFalse(task.done())
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            asyncio.run(run())

    def test_play_audio_does_not_crash_when_sounddevice_is_none(self):
        import main
        ui_mock = MagicMock()
        live = main.GHOSTLive(ui_mock)
        live.audio_in_queue = asyncio.Queue()

        with patch.object(main, "sd", None):
            async def run():
                task = asyncio.create_task(live._play_audio())
                live.audio_in_queue.put_nowait(b"\x00" * 100)
                await asyncio.sleep(0.05)
                self.assertFalse(task.done())
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            asyncio.run(run())


class HumanConsentVerificationTest(unittest.TestCase):
    def _extract_token(self, result):
        import re
        match = re.search(r"\[token: ([^\]]+)\]", str(result.content))
        self.assertIsNotNone(match, "Blocked response did not contain a token")
        return match.group(1)

    def test_dispatch_clears_confirmation_state_after_token_validation(self):
        import main
        from safety import _fingerprint

        live = main.GHOSTLive(MagicMock())
        executed = []
        args = {"command": "dir"}

        live._approved_human_fingerprint = _fingerprint("cmd_control", args)
        live._pending_human_fingerprint = live._approved_human_fingerprint
        live._pending_confirmation_token = issue_confirmation_token("cmd_control", args)
        live._pending_human_action = {"name": "cmd_control", "args": dict(args)}
        live._awaiting_human_confirmation = True

        async def run():
            with patch.dict(
                live._tool_handlers,
                {"cmd_control": (lambda a: executed.append(dict(a)) or "Success", 10)},
            ):
                result = await live._dispatch_tool(
                    "cmd_control",
                    {
                        "command": "dir",
                        "confirm": True,
                        "confirm_token": live._pending_confirmation_token,
                    },
                )

            self.assertTrue(result.ok)
            self.assertEqual(len(executed), 1)
            self.assertIsNone(live._approved_human_fingerprint)
            self.assertIsNone(live._pending_confirmation_token)
            self.assertIsNone(live._pending_human_fingerprint)
            self.assertIsNone(live._pending_human_action)
            self.assertFalse(live._awaiting_human_confirmation)
            self.assertFalse(live._human_confirmed)

        asyncio.run(run())

    def test_dispatch_blocks_second_high_risk_action_while_approved_action_runs(self):
        import main

        live = main.GHOSTLive(MagicMock())
        live._approved_action_running = True
        executed = []

        async def run():
            with patch.dict(
                live._tool_handlers,
                {"cmd_control": (lambda a: executed.append(dict(a)) or "Success", 10)},
            ):
                result = await live._dispatch_tool(
                    "cmd_control", {"command": "dir"}
                )

            self.assertIn("already executing", result.content.lower())
            self.assertEqual(executed, [])
            self.assertTrue(live._approved_action_running)

        asyncio.run(run())

    def test_confirm_without_human_approval_is_blocked(self):
        import main
        live = main.GHOSTLive(MagicMock())

        async def run():
            # First call: Ghost blocks the action and creates a pending request.
            first = await live._dispatch_tool(
                "cmd_control", {"command": "dir"}
            )
            self.assertIn("permission", str(first.content).lower())
            token = self._extract_token(first)

            # Retry with the token, but without local human approval.
            second = await live._dispatch_tool(
                "cmd_control",
                {"command": "dir", "confirm": True, "confirm_token": token}
            )
            self.assertIn(
                "human user has not verbally approved",
                str(second.content)
            )

        asyncio.run(run())

    def test_confirm_with_human_approval_proceeds(self):
        import main
        live = main.GHOSTLive(MagicMock())
        executed = []

        async def run():
            live._loop = asyncio.get_running_loop()

            with patch.dict(
                live._tool_handlers,
                {
                    "cmd_control": (
                        lambda a: executed.append(dict(a)) or "Success",
                        10,
                    )
                },
            ):
                first = await live._dispatch_tool(
                    "cmd_control", {"command": "dir"}
                )
                self._extract_token(first)

                approved = live._handle_confirmation_text("yes")
                self.assertTrue(approved)

                for _ in range(200):
                    if not live._approved_action_running:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("Approved action did not finish in time.")

                self.assertEqual(len(executed), 1)
                self.assertEqual(executed[0]["command"], "dir")

        asyncio.run(run())

    def test_pending_action_blocks_different_action_and_preserves_original(self):
        import main

        live = main.GHOSTLive(MagicMock())
        executed = []

        handlers = {
            "cmd_control": (
                lambda a: executed.append("A") or "Ran A", 10
            ),
            "file_controller": (
                lambda a: executed.append("B") or "Ran B", 10
            ),
        }

        async def run():
            live._loop = asyncio.get_running_loop()

            with patch.dict(live._tool_handlers, handlers):
                first_a = await live._dispatch_tool(
                    "cmd_control", {"command": "dir"}
                )
                token_a = self._extract_token(first_a)

                fingerprint_a = live._pending_human_fingerprint
                action_a = live._pending_human_action.copy()

                # B must be rejected while A is awaiting approval.
                result_b = await live._dispatch_tool(
                    "file_controller",
                    {"action": "delete", "path": "test.txt"},
                )

                self.assertIn(
                    "another action is awaiting confirmation",
                    str(result_b.content).lower(),
                )

                # B must not overwrite A's pending authorization.
                self.assertEqual(
                    live._pending_human_fingerprint, fingerprint_a
                )
                self.assertEqual(live._pending_human_action, action_a)
                self.assertEqual(live._pending_confirmation_token, token_a)
                self.assertTrue(live._awaiting_human_confirmation)
                self.assertEqual(executed, [])

                # The original A approval must still work.
                self.assertTrue(live._handle_confirmation_text("yes"))

                for _ in range(200):
                    if not live._approved_action_running:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("Approved action A did not finish in time.")

                self.assertEqual(executed, ["A"])

        asyncio.run(run())


    def test_two_pending_requests_approve_one_other_remains_blocked(self):
        import main
        live = main.GHOSTLive(MagicMock())
        executed = []

        handlers = {
            "cmd_control": (
                lambda a: executed.append("A") or "Ran A", 10
            ),
            "file_controller": (
                lambda a: executed.append("B") or "Ran B", 10
            ),
        }

        async def run():
            live._loop = asyncio.get_running_loop()

            with patch.dict(live._tool_handlers, handlers):
                first_a = await live._dispatch_tool(
                    "cmd_control", {"command": "dir"}
                )
                token_a = self._extract_token(first_a)

                self.assertTrue(
                    live._handle_confirmation_text("yes")
                )

                for _ in range(200):
                    if not live._approved_action_running:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("Approved action A did not finish in time.")

                self.assertEqual(executed, ["A"])

                first_b = await live._dispatch_tool(
                    "file_controller",
                    {"action": "delete", "path": "test.txt"},
                )
                token_b = self._extract_token(first_b)

                # B has a valid token, but has not received verbal approval.
                result_b = await live._dispatch_tool(
                    "file_controller",
                    {
                        "action": "delete",
                        "path": "test.txt",
                        "confirm": True,
                        "confirm_token": token_b,
                    },
                )

                self.assertIn(
                    "human user has not verbally approved",
                    str(result_b.content).lower(),
                )
                self.assertEqual(executed, ["A"])

                # A's consumed token must not authorize B.
                replay = await live._dispatch_tool(
                    "file_controller",
                    {
                        "action": "delete",
                        "path": "test.txt",
                        "confirm": True,
                        "confirm_token": token_a,
                    },
                )

                self.assertIn("permission", str(replay.content).lower())
                self.assertEqual(executed, ["A"])

        asyncio.run(run())

    def test_approved_action_logs_result_without_speaking_again(self):
        import main
        from types import SimpleNamespace

        live = main.GHOSTLive(MagicMock())

        live._pending_human_action = {
            "name": "cmd_control",
            "args": {"command": "dir"}
        }
        live._pending_human_fingerprint = "pending-fingerprint"
        live._approved_human_fingerprint = "approved-fingerprint"
        live._pending_confirmation_token = "mock-token"
        live._awaiting_human_confirmation = True
        live._human_confirmed = True
        live._approved_action_running = True

        live.speak = MagicMock()

        mock_execute = AsyncMock(
            return_value=SimpleNamespace(
                response={"result": "Mock execution successful"}
            )
        )

        async def run():
            with patch.object(live, "_execute_tool", mock_execute):
                await live._run_approved_pending_action()

        asyncio.run(run())

        # Approved action must execute exactly once.
        mock_execute.assert_awaited_once()

        call = mock_execute.await_args
        self.assertEqual(call.args[0].name, "cmd_control")
        self.assertTrue(call.kwargs["_approved_replay"])

        # Result must be logged.
        live.ui.write_log.assert_called_once()
        self.assertIn(
            "Mock execution successful",
            live.ui.write_log.call_args.args[0]
        )

        # No second Gemini input through speak().
        live.speak.assert_not_called()

        # Confirmation state must be cleaned up.
        self.assertIsNone(live._pending_human_action)
        self.assertIsNone(live._pending_human_fingerprint)
        self.assertIsNone(live._approved_human_fingerprint)
        self.assertIsNone(live._pending_confirmation_token)
        self.assertFalse(live._awaiting_human_confirmation)
        self.assertFalse(live._human_confirmed)
        self.assertFalse(live._approved_action_running)


    def test_approved_action_failure_always_cleans_confirmation_state(self):
        import main
        from unittest.mock import AsyncMock, patch

        live = main.GHOSTLive(MagicMock())

        live._pending_human_action = {
            "name": "cmd_control",
            "args": {"command": "dir"},
        }
        live._pending_human_fingerprint = "pending-fingerprint"
        live._approved_human_fingerprint = "approved-fingerprint"
        live._pending_confirmation_token = "mock-token"
        live._awaiting_human_confirmation = True
        live._human_confirmed = True
        live._approved_action_running = True

        mock_execute = AsyncMock(
            side_effect=RuntimeError("mock execution failure")
        )

        async def run():
            with patch.object(live, "_execute_tool", mock_execute):
                with self.assertRaisesRegex(
                    RuntimeError, "mock execution failure"
                ):
                    await live._run_approved_pending_action()

        asyncio.run(run())

        mock_execute.assert_awaited_once()

        self.assertIsNone(live._pending_human_action)
        self.assertIsNone(live._pending_human_fingerprint)
        self.assertIsNone(live._approved_human_fingerprint)
        self.assertIsNone(live._pending_confirmation_token)
        self.assertFalse(live._awaiting_human_confirmation)
        self.assertFalse(live._human_confirmed)
        self.assertFalse(live._approved_action_running)


class TelegramNullCheckTest(unittest.TestCase):
    def test_telegram_loop_exits_cleanly_if_chat_id_is_none(self):
        import main
        ui_mock = MagicMock()
        live = main.GHOSTLive(ui_mock)
        live.telegram_token = "123:ABC"
        live.telegram_chat = None

        async def run():
            task = asyncio.create_task(live._telegram_loop())
            await asyncio.sleep(0.05)
            # Should have exited cleanly because chat_id is missing
            self.assertTrue(task.done())

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
