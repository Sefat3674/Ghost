import unittest
from unittest.mock import Mock, patch

from integrations import personal_outlook_mcp as outlook


class PersonalOutlookGuardTests(unittest.TestCase):

    def test_direct_bridge_send_is_blocked(self):
        bridge = outlook.PersonalOutlookBridge()
        bridge._request = Mock(return_value={"content": "sent"})

        with self.assertRaises(PermissionError):
            bridge.call_tool(
                "outlook_send_draft",
                {"draft_id": "MOCK_DRAFT_ID"},
            )

        bridge._request.assert_not_called()

    def test_direct_bridge_delete_is_blocked(self):
        bridge = outlook.PersonalOutlookBridge()
        bridge._request = Mock(return_value={"content": "deleted"})

        with self.assertRaises(PermissionError):
            bridge.call_tool(
                "outlook_delete_message",
                {"message_id": "MOCK_MESSAGE_ID"},
            )

        bridge._request.assert_not_called()

    def test_approved_bridge_send_uses_capability(self):
        bridge = outlook.PersonalOutlookBridge()
        bridge._request = Mock(return_value={"content": "mock-approved"})

        result = bridge.call_tool(
            "outlook_send_draft",
            {"draft_id": "MOCK_DRAFT_ID"},
            _approval_capability=(
                outlook._PERSONAL_OUTLOOK_APPROVAL_CAPABILITY
            ),
        )

        self.assertEqual(result, "mock-approved")
        bridge._request.assert_called_once()

    def test_read_only_call_does_not_need_capability(self):
        bridge = outlook.PersonalOutlookBridge()
        bridge._request = Mock(return_value={"content": "mock-read"})

        result = bridge.call_tool(
            "outlook_read_message",
            {"message_id": "MOCK_MESSAGE_ID"},
        )

        self.assertEqual(result, "mock-read")
        bridge._request.assert_called_once()

    def test_public_action_cannot_send_draft(self):
        with patch.object(
            outlook.personal_outlook,
            "_request",
        ) as mock_request:
            result = outlook.personal_outlook_action({
                "action": "call",
                "tool_name": "outlook_send_draft",
                "arguments": {"draft_id": "MOCK_DRAFT_ID"},
            })

        self.assertIn("PermissionError", result)
        mock_request.assert_not_called()

    def test_create_draft_keeps_existing_low_risk_behavior(self):
        bridge = outlook.PersonalOutlookBridge()
        bridge._request = Mock(return_value={"content": "mock-draft"})

        result = bridge.call_tool(
            "outlook_create_draft",
            {"subject": "Mock test"},
        )

        self.assertEqual(result, "mock-draft")
        bridge._request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
