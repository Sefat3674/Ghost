from datetime import datetime, timedelta, timezone

from outlook.auth.microsoft_auth import MicrosoftAuth
from outlook.services.graph_client import GraphClient
from outlook.services.folder_service import FolderService
from outlook.services.contact_service import ContactService
from outlook.services.calendar_service import CalendarService
from outlook.services.attachment_service import AttachmentService


def show_result(title, result):
    print(f"\n{title}")
    print("-" * 55)

    if isinstance(result, dict):
        items = result.get("value", [])
        if isinstance(items, list):
            print(f"Found: {len(items)}")
            for item in items[:10]:
                print(
                    " -",
                    item.get("displayName")
                    or item.get("name")
                    or item.get("subject")
                    or item.get("emailAddress", {}).get("name", "Item")
                )
        else:
            print(result)
    elif isinstance(result, list):
        print(f"Found: {len(result)}")
        for item in result[:10]:
            print(item)
    else:
        print(result)


def run_test(name, callback):
    try:
        result = callback()
        show_result(name, result)
    except Exception as error:
        print(f"\n[ERROR] {name}: {type(error).__name__}: {error}")


print("=" * 55)
print("       GHOST OUTLOOK SERVICE TEST")
print("=" * 55)

auth = MicrosoftAuth()
token = auth.get_access_token()

if not token:
    print("Authentication required. Opening Microsoft login...")
    login_result = auth.login()
    token = login_result["access_token"]

graph = GraphClient(token)

# 1. Mail folders
folder_service = FolderService(graph)
run_test(
    "1. OUTLOOK MAIL FOLDERS",
    folder_service.list_folders
)

# 2. Contacts
contact_service = ContactService(graph)
run_test(
    "2. OUTLOOK CONTACTS",
    contact_service.list_contacts
)

# 3. Calendar events (today and next 7 days)
calendar_service = CalendarService(graph)

start = datetime.now(timezone.utc)
end = start + timedelta(days=7)

start_text = start.isoformat().replace("+00:00", "Z")
end_text = end.isoformat().replace("+00:00", "Z")

run_test(
    "3. CALENDAR EVENTS (NEXT 7 DAYS)",
    lambda: calendar_service.get_events(start_text, end_text, limit=20)
)

# 4. Attachments: inspect recent messages and find one with attachments
def test_attachments():
    messages = graph.get(
        "me/messages",
        params={
            "$top": 10,
            "$select": "id,subject,hasAttachments"
        }
    )

    items = messages.get("value", []) if isinstance(messages, dict) else messages

    if not items:
        return "No recent emails found."

    for message in items:
        if message.get("hasAttachments"):
            print("Email:", message.get("subject", "(No subject)"))
            return AttachmentService(graph).list_attachments(message["id"])

    return "No attachments found in the latest 10 emails."


run_test(
    "4. EMAIL ATTACHMENTS",
    test_attachments
)

print("\n" + "=" * 55)
print("       OUTLOOK SERVICE TEST FINISHED")
print("=" * 55)
