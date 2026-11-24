"""Offline tests for the Ghost Outlook v4 module (no network, no Microsoft login)."""
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("MICROSOFT_CLIENT_ID", "test-client")
sys.modules.setdefault("api_keys", types.SimpleNamespace(
    get_gemini_key=lambda *a, **k: "", get_api_key=lambda *a, **k: ""))

from outlook.services import graph_client as gc            # noqa: E402
from outlook.services.graph_client import GraphClient, GraphAPIError  # noqa: E402
from outlook.services.email_service import EmailService    # noqa: E402
import actions.outlook as ol                                # noqa: E402
from agent.outlook_approval import OUTLOOK_APPROVAL_CAPABILITY  # noqa: E402


class FakeResp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body = status, body if body is not None else {}
        self.headers, self.ok = headers or {}, 200 <= status < 300
        self.content = b"x" if body is not None else b""
        self.text = str(body)

    def json(self):
        return self._body


class GraphClientTests(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.patch.object(gc.time, "sleep", lambda *_: None)
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def test_retries_on_429_then_succeeds(self):
        g = GraphClient("tok")
        g._session.request = mock.Mock(side_effect=[
            FakeResp(429, {}, {"Retry-After": "1"}), FakeResp(200, {"ok": 1})])
        self.assertEqual(g.get("me"), {"ok": 1})
        self.assertEqual(g._session.request.call_count, 2)

    def test_refreshes_token_on_401(self):
        tokens = iter(["old", "new"])
        g = GraphClient(token_provider=lambda: next(tokens))
        g._session.request = mock.Mock(side_effect=[FakeResp(401, {}), FakeResp(200, {"a": 1})])
        self.assertEqual(g.get("me"), {"a": 1})
        self.assertEqual(g.access_token, "new")

    def test_post_timeout_is_not_retried(self):
        g = GraphClient("tok")
        g._session.request = mock.Mock(
            side_effect=gc.requests.exceptions.Timeout()
        )

        with self.assertRaises(GraphAPIError):
            g.post("me/messages/id/reply", {"comment": "reviewed reply"})

        self.assertEqual(g._session.request.call_count, 1)

    def test_post_503_is_not_retried(self):
        g = GraphClient("tok")
        g._session.request = mock.Mock(return_value=FakeResp(
            503, {"error": {"code": "ServiceUnavailable", "message": "temporary"}}
        ))

        with self.assertRaises(GraphAPIError) as cm:
            g.post("me/messages/id/reply", {"comment": "reviewed reply"})

        self.assertEqual(cm.exception.status, 503)
        self.assertEqual(g._session.request.call_count, 1)

    def test_post_401_does_not_refresh_or_retry(self):
        provider_calls = []

        def provider():
            provider_calls.append("called")
            return "old-token"

        g = GraphClient(token_provider=provider)
        g._session.request = mock.Mock(return_value=FakeResp(401, {}))

        with self.assertRaises(GraphAPIError) as cm:
            g.post("me/messages/id/reply", {"comment": "reviewed reply"})

        self.assertEqual(cm.exception.status, 401)
        self.assertEqual(g._session.request.call_count, 1)
        self.assertEqual(len(provider_calls), 1)
        self.assertEqual(g.access_token, "old-token")

    def test_pagination(self):
        g = GraphClient("tok")
        g._session.request = mock.Mock(side_effect=[
            FakeResp(200, {"value": [1, 2], "@odata.nextLink": "https://graph.microsoft.com/next"}),
            FakeResp(200, {"value": [3]})])
        self.assertEqual(g.get_all("me/messages"), [1, 2, 3])

    def test_error_is_structured(self):
        g = GraphClient("tok")
        g._session.request = mock.Mock(return_value=FakeResp(
            404, {"error": {"code": "ErrorItemNotFound", "message": "gone"}}))
        with self.assertRaises(GraphAPIError) as cm:
            g.get("me/messages/x")
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(cm.exception.code, "ErrorItemNotFound")

    def test_batch_chunks_by_20(self):
        g = GraphClient("tok")
        g.post = mock.Mock(side_effect=lambda ep, data: {"responses": [
            {"id": r["id"], "status": 200} for r in data["requests"]]})
        out = g.batch([{"method": "POST", "url": f"/me/messages/{i}/move", "body": {}}
                       for i in range(45)])
        self.assertEqual(len(out), 45)
        self.assertEqual(g.post.call_count, 3)


class EmailServiceTests(unittest.TestCase):
    def test_unread_falls_back_on_inefficient_filter(self):
        graph = mock.Mock()
        calls = []

        def get_all(endpoint, params=None, **kw):
            calls.append(params)
            if params and "$filter" in params:
                raise GraphAPIError("x", status=400, code="InefficientFilter")
            return [{"id": "1", "isRead": False}, {"id": "2", "isRead": True}]
        graph.get_all = get_all
        svc = EmailService(graph)
        self.assertEqual([m["id"] for m in svc.get_unread_emails(5)], ["1"])

    def test_search_strips_quotes(self):
        graph = mock.Mock()
        graph.get_all.return_value = []
        EmailService(graph).search_emails('say "hi" now')
        self.assertEqual(graph.get_all.call_args.kwargs["params"]["$search"], '"say  hi  now"')

    def test_bulk_move_reports_partial_failure(self):
        graph = mock.Mock()
        graph.batch.return_value = [
            {"status": 201}, {"status": 404, "body": {"error": {"message": "missing"}}}]
        moved, failed = EmailService(graph).bulk_move(["a", "b"], "archive")
        self.assertEqual(moved, ["a"])
        self.assertEqual(failed[0]["id"], "b")


def _run(params, **services):
    """Invoke outlook_action with fake auth and fake services."""
    auth = mock.Mock()
    auth.get_access_token.return_value = "tok"
    emails = services.get("emails") or mock.Mock()
    with mock.patch.object(ol, "get_auth", return_value=auth), \
         mock.patch.object(ol, "GraphClient", return_value=mock.Mock()), \
         mock.patch.object(ol, "EmailService", return_value=emails), \
         mock.patch.object(ol, "FolderService", return_value=services.get("folders", mock.Mock())), \
         mock.patch.object(ol, "CalendarService", return_value=services.get("calendar", mock.Mock())), \
         mock.patch.object(ol, "ContactService", return_value=mock.Mock()), \
         mock.patch.object(ol, "AttachmentService", return_value=mock.Mock()), \
         mock.patch.object(ol, "MailboxService", return_value=mock.Mock()):
        return ol.outlook_action(params), emails


class DispatcherTests(unittest.TestCase):
    def test_unknown_action(self):
        out, _ = _run({"action": "format_disk"})
        self.assertIn("not available", out)

    def test_every_gated_action_has_a_handler(self):
        self.assertTrue(ol.APPROVAL_REQUIRED <= set(ol._HANDLERS))

    def test_send_email_blocked_without_approval(self):
        out, emails = _run({"action": "send_email", "to": "a@b.com", "subject": "s", "body": "b"})
        self.assertIn("requires explicit user confirmation", out)
        emails.send_email.assert_not_called()

    def test_send_email_runs_when_approved(self):
        out, emails = _run({"action": "send_email", "to": "a@b.com", "subject": "s",
                            "body": "b", "_ghost_safety_approved": OUTLOOK_APPROVAL_CAPABILITY})
        self.assertIn("Email sent", out)
        emails.send_email.assert_called_once()

    def test_send_email_rejects_invalid_importance(self):
        emails = mock.Mock()

        out, _ = _run(
            {
                "action": "send_email",
                "to": "a@b.com",
                "subject": "Diagnostic test",
                "body": "Mock-only test",
                "importance": "urgent",
                "_ghost_safety_approved": OUTLOOK_APPROVAL_CAPABILITY,
            },
            emails=emails,
        )

        self.assertIn("importance", out.lower())
        emails.send_email.assert_not_called()

    def test_send_email_timeout_is_not_reported_as_success(self):
        emails = mock.Mock()
        emails.send_email.side_effect = TimeoutError("simulated timeout")

        out, _ = _run(
            {
                "action": "send_email",
                "to": "a@b.com",
                "subject": "Diagnostic test",
                "body": "Mock-only test",
                "_ghost_safety_approved": OUTLOOK_APPROVAL_CAPABILITY,
            },
            emails=emails,
        )

        self.assertIn("couldn't complete", out.lower())
        self.assertNotIn("email sent", out.lower())
        emails.send_email.assert_called_once()

    def test_invalid_recipient_rejected(self):
        out, emails = _run({"action": "send_email", "to": "not-an-email",
                            "_ghost_safety_approved": OUTLOOK_APPROVAL_CAPABILITY})
        self.assertIn("Invalid recipient", out)
        emails.send_email.assert_not_called()

    def test_delete_requires_approval_and_is_recoverable(self):
        out, emails = _run({"action": "delete_email", "message_id": "AAMk123="})
        self.assertIn("requires explicit", out)
        out, emails = _run({"action": "delete_email", "message_id": "AAMk123=",
                            "_ghost_safety_approved": OUTLOOK_APPROVAL_CAPABILITY})
        emails.delete_email.assert_called_once_with("AAMk123=")
        emails.permanently_delete_email.assert_not_called()

    def test_path_injection_in_id_rejected(self):
        out, emails = _run({"action": "mark_read", "message_id": "../me/messages"})
        self.assertIn("looks invalid", out)
        emails.mark_as_read.assert_not_called()

    def test_bulk_organize_confirmation_gate(self):
        folders = mock.Mock()
        folders.resolve.return_value = ("fid", "Projects")
        out, emails = _run({"action": "bulk_organize", "message_ids": ["a", "b", "a"],
                            "destination_folder": "Projects"}, folders=folders)
        self.assertIn("CONFIRMATION REQUIRED", out)
        self.assertIn("Emails selected: 2", out)          # duplicates removed
        emails.bulk_move.assert_not_called()

    def test_bulk_organize_limit(self):
        out, _ = _run({"action": "bulk_organize", "message_ids": [str(i) for i in range(26)],
                       "destination_folder": "X"})
        self.assertIn("limited to 25", out)

    def test_calendar_invite_needs_approval_only_with_attendees(self):
        cal = mock.Mock()
        cal.create_event.return_value = {"id": "E1"}
        out, _ = _run({"action": "create_event", "subject": "Sync", "start": "2026-12-01T10:00:00",
                       "end": "2026-12-01T11:00:00"}, calendar=cal)
        self.assertIn("CALENDAR EVENT CREATED", out)
        out, _ = _run({"action": "create_event", "subject": "Sync", "start": "2026-12-01T10:00:00",
                       "end": "2026-12-01T11:00:00", "attendees": "x@y.com"}, calendar=cal)
        self.assertIn("requires explicit", out)


class DraftWorkflowTests(unittest.TestCase):
    def setUp(self):
        ol._PENDING_REPLY_DRAFTS.clear()
        self._save = mock.patch.object(ol, "_save_pending_drafts", lambda: None)
        self._save.start()
        self.addCleanup(self._save.stop)
        self.email = {"id": "m1", "subject": "Review", "sender_name": "Rahim",
                      "sender_email": "r@x.com", "body": "Please review the deployment.",
                      "body_type": "text"}

    def test_draft_hash_gate_and_expiry(self):
        emails = mock.Mock()
        emails.get_email.return_value = self.email
        out, _ = _run({"action": "draft_reply", "message_id": "m1", "local_only": True},
                      emails=emails)
        self.assertIn("NOT SENT", out)
        draft_id = out.split("Draft ID: ")[1].split("\n")[0]
        draft = ol._PENDING_REPLY_DRAFTS[draft_id]

        out, e2 = _run({"action": "send_reply", "draft_id": draft_id, "draft_hash": "wrong"},
                       emails=emails)
        self.assertIn("mismatch", out)
        emails.reply_email.assert_not_called()

        out, _ = _run({"action": "send_reply", "draft_id": draft_id,
                       "draft_hash": draft["draft_hash"]}, emails=emails)
        self.assertIn("requires explicit user confirmation", out)
        emails.reply_email.assert_not_called()
        self.assertIn(draft_id, ol._PENDING_REPLY_DRAFTS)

        out, _ = _run({"action": "send_reply", "draft_id": draft_id,
                       "draft_hash": draft["draft_hash"],
                       "_ghost_safety_approved": OUTLOOK_APPROVAL_CAPABILITY}, emails=emails)
        self.assertIn("sent successfully", out)
        emails.reply_email.assert_called_once()
        self.assertNotIn(draft_id, ol._PENDING_REPLY_DRAFTS)

    def test_reply_timeout_preserves_draft_without_retry(self):
        emails = mock.Mock()
        emails.get_email.return_value = self.email

        out, _ = _run(
            {"action": "draft_reply", "message_id": "m1", "local_only": True},
            emails=emails,
        )
        draft_id = out.split("Draft ID: ")[1].split("\n")[0]
        draft = ol._PENDING_REPLY_DRAFTS[draft_id]

        emails.reply_email.side_effect = TimeoutError("simulated timeout")

        out, _ = _run(
            {
                "action": "send_reply",
                "draft_id": draft_id,
                "draft_hash": draft["draft_hash"],
                "_ghost_safety_approved": OUTLOOK_APPROVAL_CAPABILITY,
            },
            emails=emails,
        )

        self.assertIn("couldn't complete", out.lower())
        self.assertNotIn("sent successfully", out.lower())
        emails.reply_email.assert_called_once()
        self.assertIn(draft_id, ol._PENDING_REPLY_DRAFTS)

    def test_expired_draft_is_purged(self):
        ol._PENDING_REPLY_DRAFTS["old"] = {"created_at": 0, "body": "x", "draft_hash": "h"}
        out, _ = _run({"action": "show_draft", "draft_id": "old"})
        self.assertIn("not found or expired", out)

    def test_bangla_local_reply_is_real_bangla(self):
        text = ol._generate_local_reply(self.email, "Bangla")
        self.assertNotIn("?", text)
        self.assertIn("ধন্যবাদ", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
