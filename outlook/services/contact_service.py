class ContactService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def list_contacts(self, limit=50):
        response = self.graph.get(
            "me/contacts",
            params={
                "$top": limit,
                "$select": (
                    "id,displayName,givenName,surname,"
                    "emailAddresses,businessPhones,mobilePhone"
                )
            }
        )
        return response.get("value", [])

    def search_contacts(self, search_text, limit=20):
        response = self.graph.get(
            "me/contacts",
            params={
                "$search": f'"{search_text}"',
                "$top": limit,
                "$select": "id,displayName,emailAddresses"
            },
            extra_headers={
                "ConsistencyLevel": "eventual"
            }
        )
        return response.get("value", [])

    def create_contact(
        self,
        given_name,
        surname="",
        email=""
    ):
        data = {
            "givenName": given_name,
            "surname": surname
        }

        if email:
            data["emailAddresses"] = [
                {
                    "address": email,
                    "name": f"{given_name} {surname}".strip()
                }
            ]

        return self.graph.post("me/contacts", data)

    def update_contact(self, contact_id, changes):
        return self.graph.patch(
            f"me/contacts/{contact_id}",
            changes
        )

    def delete_contact(self, contact_id):
        return self.graph.delete(
            f"me/contacts/{contact_id}"
        )
