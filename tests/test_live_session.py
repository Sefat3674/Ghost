import unittest

from google.genai.errors import APIError

from main import GHOSTLive


class LiveSessionTests(unittest.TestCase):
    def test_normal_close_in_task_group_is_recognized(self):
        error = ExceptionGroup(
            "task group failed",
            [APIError(1000, None, None)],
        )

        self.assertTrue(GHOSTLive._is_normal_live_session_close(error))

    def test_unexpected_or_mixed_task_group_errors_are_not_suppressed(self):
        unexpected_close = ExceptionGroup(
            "task group failed",
            [APIError(1006, None, None)],
        )
        mixed = ExceptionGroup(
            "task group failed",
            [APIError(1000, None, None), RuntimeError("unexpected failure")],
        )

        self.assertFalse(
            GHOSTLive._is_normal_live_session_close(unexpected_close)
        )
        self.assertFalse(GHOSTLive._is_normal_live_session_close(mixed))
