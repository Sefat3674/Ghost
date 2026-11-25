class FolderService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def list_folders(self):
        response = self.graph.get(
            "me/mailFolders",
            params={
                "$top": 100,
                "$select": "id,displayName,totalItemCount,unreadItemCount"
            }
        )
        return response.get("value", [])

    def create_folder(self, name):
        if not name or not name.strip():
            raise ValueError("Folder name is required.")

        return self.graph.post(
            "me/mailFolders",
            {"displayName": name.strip()}
        )

    def rename_folder(self, folder_id, new_name):
        return self.graph.patch(
            f"me/mailFolders/{folder_id}",
            {"displayName": new_name}
        )

    def delete_folder(self, folder_id):
        return self.graph.delete(
            f"me/mailFolders/{folder_id}"
        )

    def get_folder_messages(self, folder_id, limit=20):
        response = self.graph.get(
            f"me/mailFolders/{folder_id}/messages",
            params={
                "$top": limit,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,receivedDateTime,isRead"
            }
        )
        return response.get("value", [])
