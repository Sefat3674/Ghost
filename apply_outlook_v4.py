"""
Wire Outlook v4 into Ghost's main.py (tool schema + approval hook) and safety.py
(risk levels). Backs up both files first. Safe to run twice.

Usage (from the Ghost project root):   python apply_outlook_v4.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()

NEW_SET = ('{"move_email", "bulk_organize", "delete_folder", "send_email", "reply", '
           '"forward", "send_draft", "delete_draft", "delete_email", "permanent_delete", '
           '"attach_file", "update_event", "delete_event", "respond_event", '
           '"delete_contact", "set_auto_reply", "create_event"}')
OLD_SET = '{"move_email", "bulk_organize", "delete_folder"}'

HIGH = ["send_email", "reply", "forward", "send_draft", "delete_draft", "delete_email",
        "permanent_delete", "attach_file", "update_event", "delete_event",
        "respond_event", "delete_contact", "set_auto_reply", "create_event"]

OLD_DESC = ('"draft_grouped_reply, show_draft, revise_reply, send_reply."')
NEW_DESC = ('"draft_grouped_reply, show_draft, revise_reply, send_reply, filter, thread, '
            'create_draft, update_draft, list_drafts, send_draft, delete_draft, send_email, '
            'reply, forward, mark_read, mark_unread, flag, unflag, complete_flag, '
            'set_importance, set_categories, archive, delete_email, permanent_delete, event, '
            'create_event, update_event, delete_event, respond_event, free_slots, '
            'create_contact, update_contact, delete_contact, download_attachment, '
            'attach_file, categories, create_category, auto_reply, set_auto_reply, '
            'login, logout, status. Anything that sends, deletes or changes data needs '
            'confirm=True after the user approves the exact details."')

OLD_ENUM_TAIL = '"revise_reply | send_reply"'
NEW_ENUM_TAIL = ('"revise_reply | send_reply | filter | thread | create_draft | update_draft | '
                 'list_drafts | send_draft | delete_draft | send_email | reply | forward | '
                 'mark_read | mark_unread | flag | unflag | complete_flag | set_importance | '
                 'set_categories | archive | delete_email | permanent_delete | event | '
                 'create_event | update_event | delete_event | respond_event | free_slots | '
                 'create_contact | update_contact | delete_contact | download_attachment | '
                 'attach_file | categories | create_category | auto_reply | set_auto_reply | '
                 'login | logout | status"')

ANCHOR = '''                "local_only": {
                    "type": "BOOLEAN",
                    "description": "Use the local grouped-reply generator instead of Gemini."
                }
'''


def prop(name, typ, desc):
    return (f'                "{name}": {{\n                    "type": "{typ}",\n'
            f'                    "description": {desc!r}\n                }}')


EXTRA_PROPS = [
    ("to", "STRING", "Recipient email address(es), comma separated (send_email, create_draft, forward)."),
    ("cc", "STRING", "Cc address(es), comma separated."),
    ("bcc", "STRING", "Bcc address(es), comma separated."),
    ("subject", "STRING", "Email or event subject."),
    ("body", "STRING", "Email or event body text."),
    ("comment", "STRING", "Reply/forward text for reply and forward, or response note for respond_event."),
    ("html", "BOOLEAN", "Treat body as HTML."),
    ("reply_all", "BOOLEAN", "Reply to everyone on the thread."),
    ("folder", "STRING", "Folder name or well-known name: inbox, sent, drafts, deleted, junk, archive."),
    ("conversation_id", "STRING", "Conversation ID for thread."),
    ("sender", "STRING", "Sender address for filter."),
    ("since", "STRING", "ISO-8601 start datetime for filter."),
    ("until", "STRING", "ISO-8601 end datetime for filter."),
    ("unread_only", "BOOLEAN", "Only unread messages (filter)."),
    ("importance", "STRING", "low | normal | high."),
    ("categories", "STRING", "Comma separated category names for set_categories."),
    ("event_id", "STRING", "Calendar event ID."),
    ("start", "STRING", "ISO-8601 start datetime (events, calendar range, auto-reply)."),
    ("end", "STRING", "ISO-8601 end datetime."),
    ("timezone", "STRING", "IANA/Windows timezone name, e.g. Asia/Dhaka."),
    ("attendees", "STRING", "Attendee emails, comma separated. Sends invitations."),
    ("location", "STRING", "Event location."),
    ("online_meeting", "BOOLEAN", "Add a Teams meeting (work/school accounts)."),
    ("response", "STRING", "accept | tentative | decline for respond_event."),
    ("days", "INTEGER", "Days ahead for calendar or free_slots."),
    ("duration_minutes", "INTEGER", "Meeting length for free_slots."),
    ("contact_id", "STRING", "Contact ID."),
    ("given_name", "STRING", "Contact first name."),
    ("surname", "STRING", "Contact last name."),
    ("email", "STRING", "Contact email address."),
    ("attachment_id", "STRING", "Attachment ID for download_attachment."),
    ("file_path", "STRING", "Local file to attach to a draft (attach_file)."),
    ("parent_folder", "STRING", "Parent folder name for create_folder."),
    ("message", "STRING", "Auto-reply message text."),
    ("enabled", "BOOLEAN", "Turn automatic replies on or off."),
]


def patch(path, edits):
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new, count in edits:
        if new in text and old not in text:
            continue
        found = text.count(old)
        if found != count:
            sys.exit(f"{path.name}: expected {count} match(es) for {old[:50]!r}, found {found}. "
                     "Nothing written.")
        text = text.replace(old, new)
    if text != original:
        shutil.copy2(path, path.with_name(path.name + ".before_outlook_v4.bak"))
        path.write_text(text, encoding="utf-8")
        print(f"patched {path.name}")
    else:
        print(f"{path.name}: already up to date")


main_py, safety_py = ROOT / "main.py", ROOT / "safety.py"
for f in (main_py, safety_py):
    if not f.exists():
        sys.exit(f"{f} not found. Run this from the Ghost project root.")

props_block = ",\n".join(prop(*p) for p in EXTRA_PROPS)
text_main = main_py.read_text(encoding="utf-8")
if '"parent_folder"' in text_main:
    props_edit = []
else:
    props_edit = [(ANCHOR, ANCHOR.rstrip("\n") + ",\n" + props_block + "\n", 1)]

patch(main_py, [(OLD_SET, NEW_SET, 2), (OLD_DESC, NEW_DESC, 1),
                (OLD_ENUM_TAIL, NEW_ENUM_TAIL, 1)] + props_edit)

risk_old = '        "delete_folder": Risk.HIGH,\n        None: Risk.LOW,\n    },\n    "task_manager"'
risk_new = ('        "delete_folder": Risk.HIGH,\n'
            + "".join(f'        "{a}": Risk.HIGH,\n' for a in HIGH)
            + '        None: Risk.LOW,\n    },\n    "task_manager"')
patch(safety_py, [(risk_old, risk_new, 1)])
print("Done. Now run:  python -m py_compile main.py safety.py actions/outlook.py")
