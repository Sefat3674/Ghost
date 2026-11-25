import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from main import GHOSTLive


class LiveAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_output_transcription_does_not_mark_audio_as_playing(self):
        response = SimpleNamespace(
            server_content=SimpleNamespace(
                output_transcription=SimpleNamespace(text="Hello."),
                model_turn=SimpleNamespace(parts=[]),
                input_transcription=SimpleNamespace(text=""),
                turn_complete=True,
            ),
            data=None,
            tool_call=None,
        )

        class FakeSession:
            async def receive(self):
                yield response
                raise asyncio.CancelledError

        live = object.__new__(GHOSTLive)
        live.session = FakeSession()
        live.ui = SimpleNamespace(
            silent_mode=False,
            write_log=MagicMock(),
        )
        live.audio_in_queue = asyncio.Queue()
        live._suppress_confirmation_followup = False
        live._awaiting_human_confirmation = False
        live._turn_complete = False
        live._phase_lock = threading.Lock()
        live._roll_turns = 0
        live._update_rolling = MagicMock()
        live._persist_rolling_summary = MagicMock()
        live.set_speaking = MagicMock()

        with self.assertRaises(asyncio.CancelledError):
            await live._receive_audio()

        live.set_speaking.assert_not_called()
        live.ui.write_log.assert_called_once_with("GHOST: Hello.")
