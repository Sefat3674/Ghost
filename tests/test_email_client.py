import asyncio
import json
import threading
import unittest
from types import SimpleNamespace
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

        self.assertTrue(is_email_client_command("I want to send a mail"))
        self.assertFalse(is_email_client_command("open the email draft"))

    def test_voice_commands_open_drafts_sent_items_or_compose(self):
        self.assertEqual(
            parse_email_client_command("Ghost, show my drafts"),
            {"action": "open", "folder": "drafts"},
        )
        self.assertEqual(
            parse_email_client_command("show draft"),
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
        for phrase in (
            "I want to send a mail",
            "एक मेल भेजना होगा",
            "আমি একটা মেইল পাঠাতে চাই",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    parse_email_client_command(phrase),
                    {"action": "compose"},
                )
        self.assertEqual(
            parse_email_client_command("edit"),
            {"action": "edit"},
        )
        self.assertEqual(
            parse_email_client_command("send"),
            {"action": "send"},
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

    def test_main_routes_edit_and_send_voice_commands_to_open_mail_ui(self):
        live = object.__new__(GHOSTLive)
        live._handle_confirmation_text = MagicMock(return_value=False)
        live.ui = MagicMock()

        self.assertTrue(live._on_text_command("edit"))
        live.ui.handle_email_voice_command.assert_called_once_with("edit")

        live.ui.reset_mock()
        self.assertTrue(live._on_text_command("send"))
        live.ui.handle_email_voice_command.assert_called_once_with("send")

    def test_confirmation_gate_accepts_clear_bengali_and_hindi_approval(self):
        for phrase in ("হ্যাঁ, পাঠায় দাও", "हाँ भेज दो"):
            with self.subTest(phrase=phrase):
                live = object.__new__(GHOSTLive)
                live._awaiting_human_confirmation = True
                live._pending_human_fingerprint = "pending"
                live._pending_human_action = {
                    "name": "personal_outlook",
                    "args": {"tool_name": "outlook_send_draft"},
                }
                live._approved_human_fingerprint = None
                live._approved_action_running = False
                live._pending_confirmation_token = "one-time-token"
                live._mark_human_confirmed = MagicMock(return_value=True)

                self.assertTrue(live._handle_confirmation_text(phrase))
                live._mark_human_confirmed.assert_called_once_with()

    def test_send_approval_cannot_confirm_a_pending_draft_update(self):
        live = object.__new__(GHOSTLive)
        live._awaiting_human_confirmation = True
        live._pending_human_fingerprint = "update-fingerprint"
        live._pending_human_action = {
            "name": "personal_outlook",
            "args": {"tool_name": "outlook_update_draft"},
        }
        live._approved_human_fingerprint = None
        live._approved_action_running = False
        live._pending_confirmation_token = "update-token"
        live._mark_human_confirmed = MagicMock(return_value=True)
        live.ui = MagicMock()

        self.assertFalse(live._handle_confirmation_text("Yes. Send it."))

        live._mark_human_confirmed.assert_not_called()
        self.assertTrue(live._awaiting_human_confirmation)
        self.assertEqual(
            live._pending_human_fingerprint,
            "update-fingerprint",
        )
        self.assertIn(
            "pending confirmation is for a draft update",
            live.ui.write_log.call_args.args[0],
        )

    def test_update_specific_spoken_approval_confirms_pending_update(self):
        for phrase in ("করে দাও", "हाँ, कर सकते हो"):
            with self.subTest(phrase=phrase):
                live = object.__new__(GHOSTLive)
                live._awaiting_human_confirmation = True
                live._pending_human_fingerprint = "update-fingerprint"
                live._pending_human_action = {
                    "name": "personal_outlook",
                    "args": {"tool_name": "outlook_update_draft"},
                }
                live._approved_human_fingerprint = None
                live._approved_action_running = False
                live._pending_confirmation_token = "update-token"
                live._mark_human_confirmed = MagicMock(return_value=True)

                self.assertTrue(live._handle_confirmation_text(phrase))
                live._mark_human_confirmed.assert_called_once_with()

    def test_hum_is_not_send_approval(self):
        live = object.__new__(GHOSTLive)
        live._awaiting_human_confirmation = True
        live._pending_human_fingerprint = "send-fingerprint"
        live._pending_human_action = {
            "name": "personal_outlook",
            "args": {"tool_name": "outlook_send_draft"},
        }
        live._approved_human_fingerprint = None
        live._approved_action_running = False
        live._pending_confirmation_token = "send-token"
        live._mark_human_confirmed = MagicMock(return_value=True)

        self.assertFalse(live._handle_confirmation_text("Hum"))

        live._mark_human_confirmed.assert_not_called()
        self.assertTrue(live._awaiting_human_confirmation)

    def test_create_draft_blocks_a_mismatched_dictated_recipient(self):
        live = GHOSTLive(MagicMock())
        live._last_spoken_outlook_recipients = ("asifahmed3674@gmail.com",)
        call = SimpleNamespace(
            id="create-draft-call",
            name="personal_outlook",
            args={
                "action": "call",
                "tool_name": "outlook_create_draft",
                "arguments": {
                    "to": ["sifahmed3674@gmail.com"],
                    "subject": "Test",
                    "body": "Hello",
                },
            },
        )

        result = asyncio.run(live._execute_tool(call))

        self.assertIn("No draft was created", result.response["result"])
        self.assertIn("asifahmed3674@gmail.com", result.response["result"])
        self.assertIn("sifahmed3674@gmail.com", result.response["result"])

    def test_compose_population_blocks_a_mismatched_dictated_recipient(self):
        live = GHOSTLive(MagicMock())
        live._last_spoken_outlook_recipients = ("asifahmed3674@gmail.com",)
        call = SimpleNamespace(
            id="populate-call",
            name="outlook_mail_ui",
            args={
                "action": "populate",
                "to": "sifahmed3674@gmail.com",
                "subject": "Hello",
            },
        )

        result = asyncio.run(live._execute_tool(call))

        self.assertIn("No value was entered", result.response["result"])
        self.assertIn("asifahmed3674@gmail.com", result.response["result"])
        live.ui.update_open_compose_fields.assert_not_called()

    def test_confirmation_gate_accepts_bengali_cancellation(self):
        live = object.__new__(GHOSTLive)
        live._awaiting_human_confirmation = True
        live._pending_human_fingerprint = "pending"
        live._pending_human_action = {"name": "personal_outlook"}
        live._approved_human_fingerprint = None
        live._approved_action_running = False
        live._pending_confirmation_token = "one-time-token"
        live._human_confirmed = False
        live.ui = MagicMock()

        self.assertTrue(live._handle_confirmation_text("না, পাঠিও না"))

        self.assertFalse(live._awaiting_human_confirmation)
        self.assertIsNone(live._pending_human_action)
        self.assertIsNone(live._pending_human_fingerprint)

    def test_live_outlook_tool_opens_the_requested_folder(self):
        live = object.__new__(GHOSTLive)
        live.ui = MagicMock()
        handler = live._build_tool_handlers()["outlook_mail_ui"][0]

        result = handler({"action": "open", "folder": "drafts"})

        self.assertIn("drafts", result)
        live.ui.open_email_client.assert_called_once_with(folder="drafts")

    def test_live_outlook_tool_displays_the_exact_requested_draft(self):
        live = object.__new__(GHOSTLive)
        live.ui = MagicMock()
        handler = live._build_tool_handlers()["outlook_mail_ui"][0]

        result = handler({
            "action": "open",
            "folder": "drafts",
            "draft_id": "draft-123",
        })

        self.assertIn("exact selected draft", result)
        live.ui.open_outlook_draft_by_id.assert_called_once_with("draft-123")

    def test_live_outlook_tool_populates_the_visible_compose_form(self):
        live = object.__new__(GHOSTLive)
        live.ui = MagicMock()
        handler = live._build_tool_handlers()["outlook_mail_ui"][0]

        result = handler({
            "action": "populate",
            "to": "person@example.com",
            "subject": "Hello",
            "body": "Good morning",
        })

        self.assertIn("No draft was saved or sent", result)
        live.ui.update_open_compose_fields.assert_called_once_with({
            "to": "person@example.com",
            "subject": "Hello",
            "body": "Good morning",
        })

    def test_live_outlook_send_from_new_compose_saves_before_approval(self):
        live = object.__new__(GHOSTLive)
        live.ui = MagicMock()
        live.ui._email_compose_mode = "new"
        live.ui.handle_email_voice_command.return_value = True
        handler = live._build_tool_handlers()["outlook_mail_ui"][0]

        result = handler({"action": "send"})

        self.assertIn("No email has been sent yet", result)
        live.ui.handle_email_voice_command.assert_called_once_with("send")
        live.ui.open_outlook_draft_by_id.assert_not_called()

    def test_live_outlook_edit_targets_the_last_reviewed_draft(self):
        live = object.__new__(GHOSTLive)
        live.ui = MagicMock()
        live._last_reviewed_outlook_draft_id = "draft-123"
        live._reviewed_outlook_drafts = {"draft-123": ("verified",)}
        handler = live._build_tool_handlers()["outlook_mail_ui"][0]

        result = handler({"action": "edit"})

        self.assertIn("No changes have been saved or sent", result)
        live.ui.open_outlook_draft_for_edit.assert_called_once_with("draft-123")
        live.ui.handle_email_voice_command.assert_not_called()

    def test_live_outlook_send_requires_review_and_never_sends_directly(self):
        live = object.__new__(GHOSTLive)
        live.ui = MagicMock()
        live.ui._email_compose_mode = None
        snapshot = {
            "id": "draft-123",
            "is_draft": True,
            "subject": "Verification",
            "body": "Hello",
            "to_available": True,
            "to": [{"email": "recipient@example.com"}],
            "cc_available": True,
            "cc": [],
            "bcc_available": True,
            "bcc": [],
        }
        live.ui.get_selected_outlook_draft_snapshot.return_value = snapshot
        live._reviewed_outlook_drafts = {}
        handler = live._build_tool_handlers()["outlook_mail_ui"][0]

        result = handler({"action": "send"})

        self.assertIn("not been fully reviewed", result)
        live.ui.handle_email_voice_command.assert_not_called()
        live.ui.open_email_client.assert_not_called()

        live._reviewed_outlook_drafts["draft-123"] = (
            GHOSTLive._outlook_draft_review_signature(snapshot)
        )
        result = json.loads(handler({"action": "send"}))

        self.assertEqual(result["status"], "approval_required")
        self.assertEqual(result["draft_id"], "draft-123")
        self.assertIn("separate explicit approval", result["next_step"])
        live.ui.handle_email_voice_command.assert_not_called()
        live.ui.open_outlook_draft_by_id.assert_called_once_with("draft-123")

    def test_main_opens_new_composer_for_email_send_intent(self):
        live = object.__new__(GHOSTLive)
        live._handle_confirmation_text = MagicMock(return_value=False)
        live.ui = MagicMock()
        live._loop = None
        live.session = None
        live._send_lock = None

        self.assertTrue(live._on_text_command("I want to send a mail"))
        live.ui.open_email_client.assert_called_once_with(compose=True)

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

    def test_edit_save_requests_an_approved_update_without_sending(self):
        command = OutlookEmailClientMixin._email_build_update_command(
            "draft-123",
            ["recipient@example.com"],
            [],
            "Updated subject",
            "Updated body",
        )

        self.assertIn("outlook_update_draft", command)
        self.assertIn("draft_id='draft-123'", command)
        self.assertIn("Updated subject", command)
        self.assertIn("Updated body", command)
        self.assertIn("explicit approval gate", command)
        self.assertIn("Do not send it", command)

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

    def test_created_verified_draft_replaces_an_empty_new_compose(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        compose_window = MagicMock()
        client._email_compose_window = compose_window
        client._email_compose_mode = "new"
        client._email_compose_fields = {
            "to": MagicMock(get=MagicMock(return_value="")),
            "subject": MagicMock(get=MagicMock(return_value="")),
        }
        client._email_compose_body = MagicMock(
            get=MagicMock(return_value="")
        )
        client._email_close_compose = MagicMock()
        client.open_outlook_draft_by_id = MagicMock(return_value=True)

        self.assertTrue(client.show_created_outlook_draft("draft-123"))

        client._email_close_compose.assert_called_once_with(compose_window)
        client.open_outlook_draft_by_id.assert_called_once_with("draft-123")

    def test_created_verified_draft_preserves_nonempty_compose(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        client._email_compose_window = MagicMock()
        client._email_compose_mode = "new"
        client._email_compose_fields = {
            "to": MagicMock(get=MagicMock(return_value="keep@example.com")),
        }
        client._email_compose_body = MagicMock(
            get=MagicMock(return_value="")
        )
        client._email_close_compose = MagicMock()
        client._email_set_status = MagicMock()
        client.open_outlook_draft_by_id = MagicMock(return_value=True)

        self.assertFalse(client.show_created_outlook_draft("draft-123"))

        client._email_close_compose.assert_not_called()
        client.open_outlook_draft_by_id.assert_not_called()
        client._email_set_status.assert_called_once()

    def test_voice_values_are_written_into_open_new_compose(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        client._email_window_exists = MagicMock(return_value=True)
        client._email_compose_window = MagicMock()
        client._email_compose_window.winfo_exists.return_value = True
        client._email_compose_mode = "new"
        client._email_compose_fields = {
            "to": MagicMock(),
            "subject": MagicMock(),
        }
        client._email_compose_body = MagicMock()
        client._email_compose_status = MagicMock()

        self.assertTrue(client.update_open_compose_fields({
            "to": "person@example.com",
            "subject": "Voice test",
            "body": "Checking the panel",
        }))

        client._email_compose_fields["to"].delete.assert_called_once()
        client._email_compose_fields["to"].insert.assert_called_once_with(
            0, "person@example.com"
        )
        client._email_compose_fields["subject"].insert.assert_called_once_with(
            0, "Voice test"
        )
        client._email_compose_body.delete.assert_called_once_with("1.0", "end")
        client._email_compose_body.insert.assert_called_once_with(
            "1.0", "Checking the panel"
        )

    def test_loading_drafts_selects_and_opens_the_first_draft(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        rows = []
        client._email_tree = MagicMock()
        client._email_tree.get_children.side_effect = lambda: list(rows)
        client._email_tree.insert.side_effect = (
            lambda _parent, _index, iid, **_kwargs: rows.append(iid)
        )
        client._email_message_rows = {}
        client._email_current_folder = "drafts"
        client._email_current_label = "Drafts"
        client._email_search_query = ""
        client._email_next_cursor = None
        client._email_seen_cursors = set()
        client._email_more_button = MagicMock()
        client._email_list_title = MagicMock()
        client._email_render_message = MagicMock()
        client._email_select_message = MagicMock()
        client._email_set_status = MagicMock()

        client._email_messages_loaded({
            "messages": [{"id": "draft-123", "subject": "Verification"}],
            "has_more": False,
        })

        client._email_tree.selection_set.assert_called_once_with("0")
        client._email_select_message.assert_called_once_with()

    def test_loading_drafts_selects_the_requested_draft_id(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        rows = []
        client._email_tree = MagicMock()
        client._email_tree.get_children.side_effect = lambda: list(rows)
        client._email_tree.insert.side_effect = (
            lambda _parent, _index, iid, **_kwargs: rows.append(iid)
        )
        client._email_message_rows = {}
        client._email_current_folder = "drafts"
        client._email_current_label = "Drafts"
        client._email_search_query = ""
        client._email_next_cursor = None
        client._email_seen_cursors = set()
        client._email_open_after_list_id = "draft-456"
        client._email_more_button = MagicMock()
        client._email_list_title = MagicMock()
        client._email_render_message = MagicMock()
        client._email_select_message = MagicMock()
        client._email_set_status = MagicMock()

        client._email_messages_loaded({
            "messages": [
                {"id": "draft-123", "subject": "Other"},
                {"id": "draft-456", "subject": "Selected"},
            ],
            "has_more": False,
        })

        client._email_tree.selection_set.assert_called_once_with("1")
        client._email_select_message.assert_called_once_with()
        self.assertIsNone(client._email_open_after_list_id)

    def test_open_specific_draft_for_edit_queues_it_in_the_drafts_folder(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        client._email_window_exists = MagicMock(return_value=True)
        client._email_compose_window = None
        client._email_busy = False
        client._email_open_after_list_id = None
        client._email_pending_voice_action = None
        client.open_email_client = MagicMock()

        self.assertTrue(client.open_outlook_draft_for_edit("draft-456"))

        self.assertEqual(client._email_open_after_list_id, "draft-456")
        self.assertEqual(client._email_pending_voice_action, "edit")
        client.open_email_client.assert_called_once_with(folder="drafts")

    def test_open_specific_draft_by_id_displays_without_entering_edit_mode(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        client._email_window_exists = MagicMock(return_value=True)
        client._email_compose_window = None
        client._email_busy = False
        client._email_open_after_list_id = None
        client._email_pending_voice_action = None
        client.open_email_client = MagicMock()

        self.assertTrue(client.open_outlook_draft_by_id("draft-456"))

        self.assertEqual(client._email_open_after_list_id, "draft-456")
        self.assertIsNone(client._email_pending_voice_action)
        client.open_email_client.assert_called_once_with(folder="drafts")

    def test_open_specific_draft_while_busy_preserves_target_until_folder_switch(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        client._email_window_exists = MagicMock(return_value=True)
        client._email_compose_window = None
        client._email_busy = True
        client._email_open_after_list_id = None
        client._email_pending_voice_action = None
        client._email_pending_outlook_draft_id = None
        client._email_pending_folder = None
        client._email_select_folder = MagicMock()

        self.assertTrue(client.open_outlook_draft_for_edit("draft-456"))
        self.assertIsNone(client._email_open_after_list_id)

        client._email_busy = False
        client._email_apply_pending_folder()

        self.assertEqual(client._email_open_after_list_id, "draft-456")
        self.assertIsNone(client._email_pending_outlook_draft_id)
        client._email_select_folder.assert_called_once_with("drafts", "Drafts")

    def test_voice_send_uses_the_guarded_selected_draft_request(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        client._email_window_exists = MagicMock(return_value=True)
        client._email_compose_window = None
        client._email_busy = False
        client._email_current_message = {"id": "draft-123", "is_draft": True}
        client._email_request_send = MagicMock()

        self.assertTrue(client.handle_email_voice_command("send"))
        client._email_request_send.assert_called_once_with()

    def test_voice_send_from_compose_uses_save_then_approval_action(self):
        client = OutlookEmailClientMixin.__new__(OutlookEmailClientMixin)
        client._main_thread = threading.current_thread()
        client._email_window_exists = MagicMock(return_value=True)
        compose_window = MagicMock()
        compose_window.winfo_exists.return_value = True
        client._email_compose_window = compose_window
        client._email_compose_mode = "new"
        client._email_compose_send_action = MagicMock()
        client._email_busy = False

        self.assertTrue(client.handle_email_voice_command("send"))
        client._email_compose_send_action.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
