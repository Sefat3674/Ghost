from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

schema_marker = '    {\n        "name": "gmail",'

outlook_schema = '''    {
        "name": "outlook",
        "description": (
            "Read-only Microsoft Outlook operations. Use this tool for "
            "checking Outlook inbox emails, unread messages, searching emails, "
            "listing mail folders, viewing upcoming Outlook calendar events, "
            "searching or listing contacts, inspecting email attachments, "
            "and checking the connected Outlook profile. "
            "Supports English and Bangla voice requests. "
            "Actions: read, unread, search, folders, calendar, contacts, "
            "attachments, profile. This tool cannot send, delete, edit, "
            "reply to, or archive messages."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "read | unread | search | folders | calendar | "
                        "contacts | attachments | profile"
                    )
                },
                "query": {
                    "type": "STRING",
                    "description": (
                        "Search keyword for emails or contacts. "
                        "Required for search."
                    )
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum results (default 10, maximum 25)"
                },
                "message_id": {
                    "type": "STRING",
                    "description": "Outlook message ID for attachment listing"
                }
            },
            "required": []
        }
    },
'''

if '"name": "outlook"' not in source:
    if source.count(schema_marker) != 1:
        raise SystemExit("Could not uniquely locate Gmail tool schema. No schema changes made.")

    source = source.replace(schema_marker, outlook_schema + schema_marker, 1)

handler_marker = '            "gmail":             (_lazy("actions.gmail", "gmail_action", response=None, player=ui), 60),'

outlook_handler = (
    '            "outlook":           (_lazy("actions.outlook", "outlook_action", response=None, player=ui), 60),\n'
)

if '"outlook":           (_lazy("actions.outlook"' not in source:
    if source.count(handler_marker) != 1:
        raise SystemExit("Could not uniquely locate Gmail handler. No handler changes made.")

    source = source.replace(handler_marker, outlook_handler + handler_marker, 1)

path.write_text(source, encoding="utf-8")

print("Outlook tool schema and handler registered successfully.")
