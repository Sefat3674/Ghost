"""Email operations: read, search, drafts, send, reply, forward, organise."""
from outlook.services.folder_service import FolderService, WELL_KNOWN
from outlook.services.graph_client import GraphAPIError

_LIST_SELECT = (
    "id,conversationId,parentFolderId,subject,from,toRecipients,ccRecipients,"
    "receivedDateTime,sentDateTime,isRead,isDraft,importance,bodyPreview,"
    "hasAttachments,categories,flag,webLink"
)
_FULL_SELECT = _LIST_SELECT + ",body,internetMessageId"


def _recipients(value):
    if not value:
        return []
    if isinstance(value, str):
        value = [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]
    return [{"emailAddress": {"address": a}} for a in value]


class EmailService:

    def __init__(self, graph_client):
        self.graph = graph_client
        self.folders = FolderService(graph_client)

    # ------------------------------------------------------------------
    def _format_email(self, item):
        sender = (item.get("from") or {}).get("emailAddress", {})
        body = item.get("body") or {}

        def addrs(key):
            return [r.get("emailAddress", {}).get("address")
                    for r in item.get(key, []) or []
                    if r.get("emailAddress", {}).get("address")]

        return {
            "id": item.get("id"),
            "conversation_id": item.get("conversationId"),
            "parent_folder_id": item.get("parentFolderId"),
            "sent_at": item.get("sentDateTime"),
            "to_recipients": addrs("toRecipients"),
            "cc_recipients": addrs("ccRecipients"),
            "subject": item.get("subject") or "(No subject)",
            "sender_name": sender.get("name"),
            "sender_email": sender.get("address"),
            "received_at": item.get("receivedDateTime"),
            "is_read": item.get("isRead"),
            "is_draft": item.get("isDraft", False),
            "importance": item.get("importance"),
            "preview": item.get("bodyPreview"),
            "body": body.get("content", ""),
            "body_type": body.get("contentType"),
            "has_attachments": item.get("hasAttachments", False),
            "categories": item.get("categories", []),
            "flag_status": (item.get("flag") or {}).get("flagStatus"),
            "web_link": item.get("webLink"),
        }

    def _fmt_list(self, items):
        return [self._format_email(i) for i in items]

    def _folder_id(self, folder):
        fid, _ = self.folders.resolve(folder)
        if not fid:
            raise ValueError(f"Folder '{folder}' was not found.")
        return fid

    # ---- reading -----------------------------------------------------
    def list_messages(self, folder="inbox", limit=10, odata_filter=None,
                      order_by="receivedDateTime desc"):
        params = {"$top": min(limit, 50), "$select": _LIST_SELECT}
        if order_by:
            params["$orderby"] = order_by
        if odata_filter:
            params["$filter"] = odata_filter
        fid = self._folder_id(folder)
        endpoint = f"me/mailFolders/{fid}/messages"
        try:
            return self._fmt_list(self.graph.get_all(endpoint, params=params, max_items=limit))
        except GraphAPIError as exc:
            if exc.code != "InefficientFilter" or not odata_filter:
                raise
        # Graph rejects some filter + sort combinations (e.g. sender + date).
        # Retry without $orderby and sort locally, newest first.
        params.pop("$orderby", None)
        params["$top"] = 50
        items = self.graph.get_all(endpoint, params=params, max_items=max(limit * 4, 100))
        items.sort(key=lambda i: i.get("receivedDateTime") or i.get("sentDateTime") or "",
                   reverse=True)
        return self._fmt_list(items[:limit])

    def get_latest_emails(self, limit=10, folder="inbox"):
        params = {"$top": min(limit, 50), "$orderby": "receivedDateTime desc",
                  "$select": _FULL_SELECT}
        fid = self._folder_id(folder)
        return self._fmt_list(self.graph.get_all(
            f"me/mailFolders/{fid}/messages", params=params, max_items=limit))

    def get_recent_sent_emails(self, limit=20):
        return self._fmt_list(self.graph.get_all(
            "me/mailFolders/sentitems/messages",
            params={"$top": min(limit, 50), "$orderby": "sentDateTime desc",
                    "$select": _LIST_SELECT}, max_items=limit))

    def get_unread_emails(self, limit=20, folder="inbox"):
        fid = self._folder_id(folder)
        params = {"$filter": "isRead eq false", "$top": min(limit, 50),
                  "$orderby": "receivedDateTime desc", "$select": _LIST_SELECT}
        try:
            items = self.graph.get_all(f"me/mailFolders/{fid}/messages",
                                       params=params, max_items=limit)
        except GraphAPIError as exc:
            if exc.code != "InefficientFilter":
                raise
            # Graph sometimes rejects filter+orderby; filter locally instead.
            recent = self.graph.get_all(
                f"me/mailFolders/{fid}/messages",
                params={"$top": 50, "$orderby": "receivedDateTime desc",
                        "$select": _LIST_SELECT}, max_items=limit * 4)
            items = [i for i in recent if not i.get("isRead")][:limit]
        return self._fmt_list(items)

    def get_email(self, message_id):
        return self._format_email(
            self.graph.get(f"me/messages/{message_id}", params={"$select": _FULL_SELECT}))

    def get_thread(self, conversation_id, limit=25):
        safe = str(conversation_id).replace("'", "''")
        items = self.graph.get_all(
            "me/messages",
            params={"$filter": f"conversationId eq '{safe}'", "$top": min(limit, 50),
                    "$select": _LIST_SELECT}, max_items=limit)
        items.sort(key=lambda i: i.get("receivedDateTime") or i.get("sentDateTime") or "")
        return self._fmt_list(items)

    def search_emails(self, search_text, limit=20, folder=None):
        if not search_text or not search_text.strip():
            raise ValueError("Search text cannot be empty.")
        cleaned = search_text.strip().replace('"', " ")
        base = f"me/mailFolders/{self._folder_id(folder)}/messages" if folder else "me/messages"
        items = self.graph.get_all(
            base,
            params={"$search": f'"{cleaned}"', "$top": min(limit, 50),
                    "$select": _LIST_SELECT},
            extra_headers={"ConsistencyLevel": "eventual"}, max_items=limit)
        return self._fmt_list(items)

    def filter_emails(self, sender=None, since=None, until=None, unread_only=False,
                      has_attachments=None, importance=None, folder="inbox", limit=25):
        """Structured filter. since/until are ISO-8601 datetimes."""
        parts = []
        if sender:
            s = sender.replace("'", "''")
            parts.append(f"from/emailAddress/address eq '{s}'")
        if since:
            parts.append(f"receivedDateTime ge {since}")
        if until:
            parts.append(f"receivedDateTime le {until}")
        if unread_only:
            parts.append("isRead eq false")
        if has_attachments is not None:
            parts.append(f"hasAttachments eq {str(bool(has_attachments)).lower()}")
        if importance:
            parts.append(f"importance eq '{importance}'")
        return self.list_messages(folder, limit, " and ".join(parts) or None)

    # ---- state changes -----------------------------------------------
    def _patch(self, message_id, data):
        return self.graph.patch(f"me/messages/{message_id}", data)

    def mark_as_read(self, message_id):
        return self._patch(message_id, {"isRead": True})

    def mark_as_unread(self, message_id):
        return self._patch(message_id, {"isRead": False})

    def flag_email(self, message_id):
        return self._patch(message_id, {"flag": {"flagStatus": "flagged"}})

    def unflag_email(self, message_id):
        return self._patch(message_id, {"flag": {"flagStatus": "notFlagged"}})

    def complete_flag(self, message_id):
        return self._patch(message_id, {"flag": {"flagStatus": "complete"}})

    def set_importance(self, message_id, importance):
        if importance not in ("low", "normal", "high"):
            raise ValueError("importance must be low, normal or high.")
        return self._patch(message_id, {"importance": importance})

    def set_categories(self, message_id, categories):
        return self._patch(message_id, {"categories": list(categories or [])})

    # ---- moving / deleting ---------------------------------------------
    def move_email(self, message_id, destination_folder_id):
        if not message_id or not str(message_id).strip():
            raise ValueError("Message ID is required.")
        if not destination_folder_id or not str(destination_folder_id).strip():
            raise ValueError("Destination folder ID is required.")
        dest = WELL_KNOWN.get(str(destination_folder_id).casefold(), destination_folder_id)
        return self.graph.post(f"me/messages/{message_id}/move", {"destinationId": dest})

    def copy_email(self, message_id, destination_folder_id):
        dest = WELL_KNOWN.get(str(destination_folder_id).casefold(), destination_folder_id)
        return self.graph.post(f"me/messages/{message_id}/copy", {"destinationId": dest})

    def archive_email(self, message_id):
        return self.move_email(message_id, "archive")

    def delete_email(self, message_id):
        """Recoverable delete: moves to Deleted Items."""
        return self.move_email(message_id, "deleteditems")

    def permanently_delete_email(self, message_id):
        return self.graph.delete(f"me/messages/{message_id}")

    def bulk_move(self, message_ids, destination_folder_id):
        """Move many messages via Graph $batch. Returns (moved_ids, failures)."""
        dest = WELL_KNOWN.get(str(destination_folder_id).casefold(), destination_folder_id)
        reqs = [{"method": "POST", "url": f"/me/messages/{m}/move",
                 "body": {"destinationId": dest}} for m in message_ids]
        moved, failed = [], []
        for mid, res in zip(message_ids, self.graph.batch(reqs)):
            if 200 <= int(res.get("status", 500)) < 300:
                moved.append(mid)
            else:
                msg = (res.get("body") or {}).get("error", {}).get("message", "failed")
                failed.append({"id": mid, "error": msg})
        return moved, failed

    # ---- writing -------------------------------------------------------
    def _build_message(self, to, subject, body, cc=None, bcc=None, html=False,
                       importance=None):
        recipients = _recipients(to)
        message = {
            "subject": subject or "",
            "body": {"contentType": "HTML" if html else "Text", "content": body or ""},
            "toRecipients": recipients,
        }
        if cc:
            message["ccRecipients"] = _recipients(cc)
        if bcc:
            message["bccRecipients"] = _recipients(bcc)
        if importance:
            message["importance"] = importance
        return message

    def send_email(self, to, subject, body, cc=None, bcc=None, html=False,
                   importance=None):
        if not _recipients(to):
            raise ValueError("Recipient is required.")
        return self.graph.post("me/sendMail", {
            "message": self._build_message(to, subject, body, cc, bcc, html, importance),
            "saveToSentItems": True})

    def create_draft(self, to, subject, body, cc=None, bcc=None, html=False):
        return self.graph.post("me/messages",
                               self._build_message(to, subject, body, cc, bcc, html))

    def update_draft(self, draft_id, subject=None, body=None, to=None, cc=None,
                     bcc=None, html=False):
        data = {}
        if subject is not None:
            data["subject"] = subject
        if body is not None:
            data["body"] = {"contentType": "HTML" if html else "Text", "content": body}
        if to is not None:
            data["toRecipients"] = _recipients(to)
        if cc is not None:
            data["ccRecipients"] = _recipients(cc)
        if bcc is not None:
            data["bccRecipients"] = _recipients(bcc)
        return self._patch(draft_id, data)

    def send_draft(self, draft_id):
        return self.graph.post(f"me/messages/{draft_id}/send")

    def delete_draft(self, draft_id):
        return self.graph.delete(f"me/messages/{draft_id}")

    def list_drafts(self, limit=20):
        return self.list_messages("drafts", limit)

    def reply_email(self, message_id, comment, reply_all=False):
        action = "replyAll" if reply_all else "reply"
        return self.graph.post(f"me/messages/{message_id}/{action}", {"comment": comment})

    def create_reply_draft(self, message_id, comment="", reply_all=False):
        action = "createReplyAll" if reply_all else "createReply"
        return self.graph.post(f"me/messages/{message_id}/{action}", {"comment": comment})

    def forward_email(self, message_id, to, comment=""):
        if not _recipients(to):
            raise ValueError("Recipient is required.")
        return self.graph.post(f"me/messages/{message_id}/forward",
                               {"comment": comment, "toRecipients": _recipients(to)})
