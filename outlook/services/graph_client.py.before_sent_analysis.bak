import requests

from outlook.config import GRAPH_BASE_URL, REQUEST_TIMEOUT


class GraphAPIError(Exception):
    pass


class GraphClient:

    def __init__(self, access_token):
        self.access_token = access_token

    def request(self, method, endpoint, params=None,
                json_data=None, extra_headers=None):

        url = f"{GRAPH_BASE_URL}/{endpoint.lstrip('/')}"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        if extra_headers:
            headers.update(extra_headers)

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=REQUEST_TIMEOUT
            )

            if not response.ok:
                try:
                    error = response.json().get("error", {})
                    code = error.get("code", "Unknown")
                    message = error.get("message", response.text)
                except ValueError:
                    code = "Unknown"
                    message = response.text

                raise GraphAPIError(
                    f"HTTP {response.status_code} | "
                    f"{code} | {message[:1500]}"
                )

            if response.status_code == 204 or not response.content:
                return {}

            return response.json()

        except requests.exceptions.Timeout:
            raise GraphAPIError("Microsoft Graph request timed out.")

        except requests.exceptions.RequestException as error:
            raise GraphAPIError(f"Network error: {error}")

    def get(self, endpoint, params=None, extra_headers=None):
        return self.request(
            "GET", endpoint, params=params,
            extra_headers=extra_headers
        )

    def post(self, endpoint, data=None):
        return self.request("POST", endpoint, json_data=data)

    def patch(self, endpoint, data):
        return self.request("PATCH", endpoint, json_data=data)

    def delete(self, endpoint):
        return self.request("DELETE", endpoint)

    def get_profile(self):
        return self.get(
            "me",
            params={"$select": "id,displayName,mail,userPrincipalName"}
        )

    def get_recent_emails(self, limit=10):
        return self.get(
            "me/messages",
            params={
                "$top": limit,
                "$orderby": "receivedDateTime desc",
                "$select": (
                    "id,subject,from,toRecipients,receivedDateTime,"
                    "isRead,importance,bodyPreview,body,hasAttachments"
                )
            }
        )
