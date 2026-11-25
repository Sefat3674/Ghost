import unittest
from unittest.mock import MagicMock

from main import GHOSTLive
from ui.email_client import (
    OutlookEmailClientMixin,
    build_send_request,
    format_recipients,
    is_email_client_command,
    parse_email_client_command,
    parse_recipients,
    plain_text_body,
)


class EmailClientHelperTests(unittest.TestCase):
    def test_open_commands_are_recognized_without_matching_send_requests(self):
        for phrase in (
            "open Outlook interface",
            "Open email",
            "interface open",
            "show inbox",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_email_client_command(phrase))

        self.assertFalse(is_email_client_command("I want to send a mail"))
        self.assertFalse(is_email_client_command("open the email draft"))

    def test_voice_commands_open_drafts_sent_items_or_compose(self):
        self.assertEqual(
            parse_email_client_command("Ghost, show my drafts"),
            {"action": "open", "folder": "drafts"},
        )
        self.assertEqual(
            parse_email_client_command("open Outlook sent items"),
            {"action": "open", "folder": "sentitems"},
        )
        self.assertEqual(
            parse_email_client_command("new email"),
            {"action": "compose"},
        )

    def test_main_routes_open_interface_before_live_session_is_ready(self):
        live = object.__new__(GHOSTLive)
        live._handle_confirmation_text = MagicMock(return_value=False)
        live.ui = MagicMock()

        self.assertTrue(live._on_text_command("open outlook mail"))

        live.ui.open_email_client.assert_called_once_with()
        live.ui.write_log.assert_called_once_with(
            "SYS: Outlook mail workspace opened."
        )

    def test_main_routes_voice_draft_and_compose_commands_to_mail_ui(self):
        live = object.__new__(GHOSTLive)
        live._handle_confirmation_text = MagicMock(return_value=False)
        live.ui = MagicMock()

        self.assertTrue(live._on_text_command("show my drafts"))
        live.ui.open_email_client.assert_called_once_with(folder="drafts")

        live.ui.reset_mock()
        self.assertTrue(live._on_text_command("new email"))
        live.ui.open_email_client.assert_called_once_with(compose=True)

    def test_main_does_not_consume_email_compose_requests_as_open_commands(self):
        live = object.__new__(GHOSTLive)
        live._handle_confirmation_text = MagicMock(return_value=False)
        live.ui = MagicMock()
        live._loop = None
        live.session = None
        live._send_lock = None

        self.assertFalse(live._on_text_command("I want to send a mail"))
        live.ui.open_email_client.assert_not_called()

    def test_recipient_parsing_handles_delimiters_and_display_names(self):
        self.assertEqual(
            parse_recipients("A <a@example.com>; b@example.com, None"),
            ["a@example.com", "b@example.com"],
        )
        self.assertEqual(
            format_recipients([{"name": "A", "email": "a@example.com"}]),
            "A <a@example.com>",
        )

    def test_html_body_is_rendered_as_readable_text(self):
        self.assertEqual(
            plain_text_body(
                {"contentType": "html", "content": "<p>Hello</p><p>World &amp; GHOST</p>"}
            ),
            "Hello\n\nWorld & GHOST",
        )

    def test_send_request_requires_explicit_approval_and_never_retries(self):
        request = build_send_request("draft-123")

        self.assertIn("draft-123", request)
        self.assertIn("separate explicit approval", request)
        self.assertIn("Do not send before approval", request)
        self.assertIn("or retry a send", request)
        with self.assertRaises(ValueError):
            build_send_request("")

    def test_compose_send_saves_draft_then_requests_ghost_approval(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._email_render_message = MagicMock()
        client._email_request_send = MagicMock()
        client._email_render_folders = MagicMock()
        client._email_load_messages = MagicMock()
        client._email_folders = []
        compose_window = MagicMock()
        snapshot = {"id": "draft-123", "is_draft": True}

        client._email_compose_saved(compose_window, snapshot, send_after_save=True)

        compose_window.destroy.assert_called_once_with()
        client._email_render_message.assert_called_once_with(snapshot)
        client._email_request_send.assert_called_once_with()
        self.assertEqual(client._email_current_folder, "drafts")
        client._email_load_messages.assert_called_once_with(reset=True)


if __name__ == "__main__":
    unittest.main()
