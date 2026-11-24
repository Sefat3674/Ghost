"""Mail folder operations with name/path/well-known resolution."""

WELL_KNOWN = {
    "inbox": "inbox", "drafts": "drafts", "draft": "drafts",
    "sent": "sentitems", "sentitems": "sentitems", "sent items": "sentitems",
    "deleted": "deleteditems", "deleteditems": "deleteditems",
    "deleted items": "deleteditems", "trash": "deleteditems", "bin": "deleteditems",
    "junk": "junkemail", "junkemail": "junkemail", "junk email": "junkemail",
    "spam": "junkemail", "archive": "archive", "outbox": "outbox",
}

_FOLDER_SELECT = "id,displayName,parentFolderId,childFolderCount,totalItemCount,unreadItemCount"


class FolderService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def list_folders(self, include_children=False):
        folders = self.graph.get_all(
            "me/mailFolders", params={"$top": 100, "$select": _FOLDER_SELECT},
            max_items=500)
        if not include_children:
            return folders
        result = list(folders)
        queue = [f for f in folders if f.get("childFolderCount")]
        depth = 0
        while queue and depth < 4:
            nxt = []
            for parent in queue:
                kids = self.graph.get_all(
                    f"me/mailFolders/{parent['id']}/childFolders",
                    params={"$top": 100, "$select": _FOLDER_SELECT}, max_items=500)
                for kid in kids:
                    kid["_path"] = f"{parent.get('_path', parent.get('displayName'))}/{kid.get('displayName')}"
                    result.append(kid)
                    if kid.get("childFolderCount"):
                        nxt.append(kid)
            queue, depth = nxt, depth + 1
        return result

    def resolve(self, name_or_id):
        """Return (folder_id_or_wellknown_name, display_name) or (None, None)."""
        text = str(name_or_id or "").strip()
        if not text:
            return None, None
        key = text.casefold()
        if key in WELL_KNOWN:
            return WELL_KNOWN[key], text
        for folder in self.list_folders(include_children=True):
            path = folder.get("_path") or folder.get("displayName", "")
            if text == folder.get("id"):
                return folder["id"], folder.get("displayName")
            if key in (str(folder.get("displayName", "")).casefold(), path.casefold()):
                return folder["id"], folder.get("displayName")
        return None, None

    def create_folder(self, name, parent=None):
        if not name or not name.strip():
            raise ValueError("Folder name is required.")
        if parent:
            parent_id, _ = self.resolve(parent)
            if not parent_id:
                raise ValueError(f"Parent folder '{parent}' was not found.")
            return self.graph.post(f"me/mailFolders/{parent_id}/childFolders",
                                   {"displayName": name.strip()})
        return self.graph.post("me/mailFolders", {"displayName": name.strip()})

    def rename_folder(self, folder_id, new_name):
        return self.graph.patch(f"me/mailFolders/{folder_id}", {"displayName": new_name})

    def delete_folder(self, folder_id):
        return self.graph.delete(f"me/mailFolders/{folder_id}")

    def get_folder_messages(self, folder, limit=20):
        folder_id, _ = self.resolve(folder)
        folder_id = folder_id or folder
        return self.graph.get_all(
            f"me/mailFolders/{folder_id}/messages",
            params={"$top": min(limit, 50), "$orderby": "receivedDateTime desc",
                    "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview"},
            max_items=limit)
