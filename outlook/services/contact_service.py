"""Outlook contacts."""

_SELECT = ("id,displayName,givenName,surname,emailAddresses,businessPhones,"
           "mobilePhone,companyName,jobTitle")


class ContactService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def list_contacts(self, limit=50):
        return self.graph.get_all("me/contacts",
                                  params={"$top": min(limit, 50), "$select": _SELECT},
                                  max_items=limit)

    def search_contacts(self, search_text, limit=20):
        text = str(search_text or "").strip().replace('"', " ")
        if not text:
            return self.list_contacts(limit)
        return self.graph.get_all(
            "me/contacts",
            params={"$search": f'"{text}"', "$top": min(limit, 50), "$select": _SELECT},
            extra_headers={"ConsistencyLevel": "eventual"}, max_items=limit)

    def get_contact(self, contact_id):
        return self.graph.get(f"me/contacts/{contact_id}", params={"$select": _SELECT})

    def create_contact(self, given_name, surname="", email="", phone="", company=""):
        if not given_name:
            raise ValueError("Contact first name is required.")
        data = {"givenName": given_name, "surname": surname}
        if email:
            data["emailAddresses"] = [{"address": email,
                                       "name": f"{given_name} {surname}".strip()}]
        if phone:
            data["mobilePhone"] = phone
        if company:
            data["companyName"] = company
        return self.graph.post("me/contacts", data)

    def update_contact(self, contact_id, changes):
        return self.graph.patch(f"me/contacts/{contact_id}", changes)

    def delete_contact(self, contact_id):
        return self.graph.delete(f"me/contacts/{contact_id}")
