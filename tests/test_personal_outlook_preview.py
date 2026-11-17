import json
import unittest
from unittest.mock import patch

from integrations import personal_outlook_mcp as outlook


class PersonalOutlookPreviewTest(unittest.TestCase):

    def setUp(self):
        self.inbox_id = "folder-inbox"
        self.destination_id = "folder-destination"

        self.message_inbox = {
            "id": "message-1",
            "subject": "URGENT: Project Review",
            "from_email": "sender@example.com",
            "from_name": "Project Sender",
            "parent_folder_id": self.inbox_id,
            "received": "2026-11-16T10:00:00Z",
        }

        self.message_already_there = {
            "id": "message-2",
            "subject": "URGENT: Already Filed",
            "from_email": "other@example.com",
            "from_name": "Other Sender",
            "parent_folder_id": self.destination_id,
            "received": "2026-11-15T10:00:00Z",
        }

        self.destination_other = {
            "id": "message-3",
            "subject": "Normal email",
            "from_email": "third@example.com",
            "from_name": "Third Sender",
            "parent_folder_id": self.destination_id,
        }

    def fake_call_tool(self, tool_name, arguments):
        if tool_name == "outlook_list_folders":
            return json.dumps({
                "folders": [
                    {
                        "id": self.inbox_id,
                        "name": "Inbox",
                        "path": "Inbox",
                        "total": 1,
                    },
                    {
                        "id": self.destination_id,
                        "name": "Ghost_Test_Folder_Renamed",
                        "path": "Ghost_Test_Folder_Renamed",
                        "total": 2,
                    },
                    {
                        "id": "folder-empty",
                        "name": "Archive",
                        "path": "Archive",
                        "total": 0,
                    },
                ],
                "has_more": False,
                "cursor": None,
            })

        if tool_name == "outlook_search_mail":
            folder = arguments["folder"]

            if folder == "Inbox":
                messages = [self.message_inbox]
            elif folder == "Ghost_Test_Folder_Renamed":
                messages = [self.message_already_there]
            else:
                messages = []

            return json.dumps({
                "messages": messages,
                "count": len(messages),
                "has_more": False,
                "cursor": None,
            })

        if tool_name == "outlook_list_inbox":
            self.assertEqual(
                arguments["folder"],
                "Ghost_Test_Folder_Renamed",
            )
            return json.dumps({
                "messages": [
                    self.message_already_there,
                    self.destination_other,
                ],
                "count": 2,
                "has_more": False,
                "cursor": None,
            })

        raise AssertionError(
            f"Unexpected Outlook tool called: {tool_name}"
        )

    @patch.object(outlook.personal_outlook, "call_tool")
    def test_preview_separates_proposed_and_already_filed(self, mocked_call):
        mocked_call.side_effect = self.fake_call_tool

        result = json.loads(outlook.personal_outlook_action({
            "action": "preview_move",
        }))

        self.assertTrue(result["preview_only"])
        self.assertFalse(result["changes_made"])
        self.assertEqual(result["matching_count"], 2)
        self.assertEqual(result["proposed_move_count"], 1)
        self.assertEqual(result["already_in_destination_count"], 1)
        self.assertEqual(result["destination_existing_count"], 2)

        proposed = result["proposed_moves"][0]
        self.assertEqual(proposed["id"], "message-1")
        self.assertEqual(proposed["current_folder"], "Inbox")
        self.assertEqual(
            proposed["proposed_destination"],
            "Ghost_Test_Folder_Renamed",
        )

        already_there = result["already_in_destination"][0]
        self.assertEqual(already_there["id"], "message-2")

        allowed_tools = {
            "outlook_list_folders",
            "outlook_search_mail",
            "outlook_list_inbox",
        }
        called_tools = {
            call.args[0] for call in mocked_call.call_args_list
        }

        self.assertTrue(called_tools.issubset(allowed_tools))
        self.assertIn("outlook_list_folders", called_tools)
        self.assertIn("outlook_search_mail", called_tools)
        self.assertIn("outlook_list_inbox", called_tools)

    @patch.object(outlook.personal_outlook, "call_tool")
    def test_missing_destination_fails_without_search(self, mocked_call):
        mocked_call.return_value = json.dumps({
            "folders": [
                {
                    "id": self.inbox_id,
                    "name": "Inbox",
                    "path": "Inbox",
                    "total": 1,
                }
            ]
        })

        result = outlook.personal_outlook_action({
            "action": "preview_move",
            "destination_folder": "MissingFolder",
        })

        self.assertIn("Destination folder not found", result)

        called_tools = [
            call.args[0] for call in mocked_call.call_args_list
        ]
        self.assertEqual(called_tools, ["outlook_list_folders"])

    @patch.object(outlook.personal_outlook, "call_tool")
    def test_preview_never_calls_mutation_tools(self, mocked_call):
        mocked_call.side_effect = self.fake_call_tool

        outlook.personal_outlook_action({
            "action": "preview_move",
        })

        forbidden = {
            "outlook_move_message",
            "outlook_delete_message",
            "outlook_send_message",
            "outlook_create_folder",
            "outlook_rename_folder",
        }

        called_tools = {
            call.args[0] for call in mocked_call.call_args_list
        }

        self.assertTrue(forbidden.isdisjoint(called_tools))


if __name__ == "__main__":
    unittest.main()
