import re
from actions.outlook import outlook_action as o

def show(title, out):
    print(f"\n=== {title} ===\n{str(out)[:1200]}")

inbox = o({'action': 'read', 'limit': 1})
mid = re.search(r"Message ID: (\S+)", inbox).group(1)

show("thread", o({'action': 'thread', 'message_id': mid}))
show("filter by sender", o({'action': 'filter', 'sender': 'sefatahmed3674@gmail.com', 'limit': 3}))

d = o({'action': 'draft_reply', 'message_id': mid, 'local_only': True})
show("draft_reply (local, NOT sent)", d)
did = re.search(r"Draft ID: (\w+)", d).group(1)

show("revise_reply", o({'action': 'revise_reply', 'draft_id': did,
                        'instruction': 'make it shorter', 'local_only': True}))
show("send_reply with WRONG hash (must refuse)",
     o({'action': 'send_reply', 'draft_id': did, 'draft_hash': 'wrong'}))

show("flag", o({'action': 'flag', 'message_id': mid}))
show("unflag", o({'action': 'unflag', 'message_id': mid}))

drafts = o({'action': 'list_drafts', 'limit': 25})
m = re.search(r"Ghost v4 test\s+Message ID: (\S+)", drafts)
if m:
    show("delete_draft WITHOUT approval (must refuse)",
         o({'action': 'delete_draft', 'message_id': m.group(1)}))
    show("delete_draft WITH approval",
         o({'action': 'delete_draft', 'message_id': m.group(1), '_ghost_safety_approved': True}))
else:
    print("\n(no 'Ghost v4 test' draft found, skipping delete test)")

show("Bangla intelligence", o({'action': 'intelligence', 'limit': 3, 'language': 'Bangla'}))
