"""Tests for production hardening, audio resilience, human confirmation gate, and security."""
import unittest
import asyncio
from unittest.mock import MagicMock, patch

from actions import desktop
from safety import needs_confirmation, issue_confirmation_token, Risk, classify


class ProductionSafetyTest(unittest.TestCase):
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

        async def run():
            # First call creates the pending fingerprint and token.
            first = await live._dispatch_tool(
                "cmd_control", {"command": "dir"}
            )
            token = self._extract_token(first)

            # Simulate the user saying yes inside Ghost.
            live._handle_confirmation_text("yes")

            with patch.dict(
                live._tool_handlers,
                {"cmd_control": (lambda a: "Success", 10)}
            ):
                result = await live._dispatch_tool(
                    "cmd_control",
                    {
                        "command": "dir",
                        "confirm": True,
                        "confirm_token": token
                    }
                )
                self.assertEqual(result.content, "Success")

        asyncio.run(run())

    def test_two_pending_requests_approve_one_other_remains_blocked(self):
        import main
        live = main.GHOSTLive(MagicMock())
        executed = []

        handlers = {
            "cmd_control": (lambda a: executed.append("A") or "Ran A", 10),
            "file_controller": (
                lambda a: executed.append("B") or "Ran B", 10
            ),
        }

        async def run():
            with patch.dict(live._tool_handlers, handlers):
                # Request A and capture its token.
                first_a = await live._dispatch_tool(
                    "cmd_control", {"command": "dir"}
                )
                token_a = self._extract_token(first_a)

                # Approve A locally and execute exactly A.
                live._handle_confirmation_text("yes")
                result_a = await live._dispatch_tool(
                    "cmd_control",
                    {
                        "command": "dir",
                        "confirm": True,
                        "confirm_token": token_a
                    }
                )
                self.assertEqual(result_a.content, "Ran A")
                self.assertEqual(executed, ["A"])

                # Request B. It must not inherit approval for A.
                first_b = await live._dispatch_tool(
                    "file_controller",
                    {"action": "delete", "path": "test.txt"}
                )
                token_b = self._extract_token(first_b)

                # Even with B's valid token, no local yes was given for B.
                result_b = await live._dispatch_tool(
                    "file_controller",
                    {
                        "action": "delete",
                        "path": "test.txt",
                        "confirm": True,
                        "confirm_token": token_b
                    }
                )
                self.assertIn(
                    "human user has not verbally approved",
                    str(result_b.content)
                )
                self.assertEqual(executed, ["A"])

                # Replaying A's consumed token against B must also fail.
                replay = await live._dispatch_tool(
                    "file_controller",
                    {
                        "action": "delete",
                        "path": "test.txt",
                        "confirm": True,
                        "confirm_token": token_a
                    }
                )
                self.assertIn("permission", str(replay.content).lower())
                self.assertEqual(executed, ["A"])

        asyncio.run(run())

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
