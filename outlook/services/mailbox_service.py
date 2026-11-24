"""Mailbox settings (auto-reply, timezone) and master categories."""


class MailboxService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def get_settings(self):
        return self.graph.get("me/mailboxSettings")

    def get_auto_reply(self):
        return self.get_settings().get("automaticRepliesSetting", {})

    def set_auto_reply(self, enabled, internal_message="", external_message=None,
                       start=None, end=None, tz="UTC", external_audience="all"):
        setting = {
            "status": ("scheduled" if (enabled and start and end)
                       else "alwaysEnabled" if enabled else "disabled"),
            "externalAudience": external_audience,
            "internalReplyMessage": internal_message,
            "externalReplyMessage": (external_message
                                     if external_message is not None else internal_message),
        }
        if enabled and start and end:
            setting["scheduledStartDateTime"] = {"dateTime": start, "timeZone": tz}
            setting["scheduledEndDateTime"] = {"dateTime": end, "timeZone": tz}
        return self.graph.patch("me/mailboxSettings", {"automaticRepliesSetting": setting})

    def list_categories(self):
        return self.graph.get("me/outlook/masterCategories").get("value", [])

    def create_category(self, name, color="preset0"):
        return self.graph.post("me/outlook/masterCategories",
                               {"displayName": name, "color": color})

    def delete_category(self, category_id):
        return self.graph.delete(f"me/outlook/masterCategories/{category_id}")
