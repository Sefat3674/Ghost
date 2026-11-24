"""Microsoft Graph client with retries, throttling, token refresh and paging."""
import time

import requests

from outlook.config import GRAPH_BASE_URL, MAX_RETRIES, REQUEST_TIMEOUT

_RETRY_STATUS = {429, 500, 502, 503, 504}


class GraphAPIError(Exception):
    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


class GraphClient:
    """
    GraphClient(access_token)                 - fixed token (legacy usage)
    GraphClient(token_provider=callable)      - re-fetches token on 401
    """

    def __init__(self, access_token=None, token_provider=None):
        self._provider = token_provider
        self.access_token = access_token or (token_provider() if token_provider else None)
        if not self.access_token:
            raise GraphAPIError("No Microsoft access token available.", status=401)
        self._session = requests.Session()

    # ------------------------------------------------------------------
    def _url(self, endpoint):
        if endpoint.startswith("http"):
            return endpoint
        return f"{GRAPH_BASE_URL}/{endpoint.lstrip('/')}"

    def _headers(self, extra=None, content_type="application/json"):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _error_from(response):
        try:
            err = response.json().get("error", {})
            code, message = err.get("code", "Unknown"), err.get("message", response.text)
        except ValueError:
            code, message = "Unknown", response.text
        return GraphAPIError(
            f"HTTP {response.status_code} | {code} | {message[:1500]}",
            status=response.status_code, code=code,
        )

    def _send(self, method, url, *, params=None, json_data=None, data=None,
              extra_headers=None, content_type="application/json", raw=False):
        refreshed = False
        method_upper = method.upper()
        retryable = method_upper == "GET"

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._session.request(
                    method=method_upper, url=url,
                    headers=self._headers(extra_headers, content_type),
                    params=params, json=json_data, data=data,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.exceptions.Timeout:
                if retryable and attempt < MAX_RETRIES:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise GraphAPIError("Microsoft Graph request timed out.")
            except requests.exceptions.RequestException as exc:
                if retryable and attempt < MAX_RETRIES:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise GraphAPIError(f"Network error: {exc}")

            if retryable and response.status_code == 401 and self._provider and not refreshed:
                token = self._provider()
                if token:
                    self.access_token, refreshed = token, True
                    continue

            if retryable and response.status_code in _RETRY_STATUS and attempt < MAX_RETRIES:
                try:
                    wait = float(response.headers.get("Retry-After", ""))
                except ValueError:
                    wait = min(2 ** attempt, 20)
                time.sleep(min(max(wait, 0.5), 60))
                continue

            if not response.ok:
                raise self._error_from(response)

            if raw:
                return response
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

        raise GraphAPIError("Microsoft Graph request failed after retries.")

    # ------------------------------------------------------------------
    def request(self, method, endpoint, params=None, json_data=None,
                extra_headers=None):
        return self._send(method, self._url(endpoint), params=params,
                          json_data=json_data, extra_headers=extra_headers)

    def get(self, endpoint, params=None, extra_headers=None):
        return self.request("GET", endpoint, params=params, extra_headers=extra_headers)

    def post(self, endpoint, data=None, extra_headers=None):
        return self.request("POST", endpoint, json_data=data, extra_headers=extra_headers)

    def patch(self, endpoint, data, extra_headers=None):
        return self.request("PATCH", endpoint, json_data=data, extra_headers=extra_headers)

    def delete(self, endpoint):
        return self.request("DELETE", endpoint)

    def get_bytes(self, endpoint):
        return self._send("GET", self._url(endpoint), raw=True,
                          content_type=None).content

    def put_chunk(self, upload_url, chunk, start, end, total):
        """Upload-session chunk. Upload URLs are pre-authorised: no bearer token."""
        response = self._session.put(
            upload_url, data=chunk, timeout=REQUEST_TIMEOUT * 4,
            headers={"Content-Length": str(len(chunk)),
                     "Content-Range": f"bytes {start}-{end}/{total}"},
        )
        if not response.ok:
            raise self._error_from(response)
        return response.json() if response.content else {}

    # ------------------------------------------------------------------
    def get_all(self, endpoint, params=None, extra_headers=None, max_items=200):
        """Follow @odata.nextLink until max_items is reached."""
        items, page = [], self.get(endpoint, params=params, extra_headers=extra_headers)
        while True:
            items.extend(page.get("value", []))
            if len(items) >= max_items:
                return items[:max_items]
            nxt = page.get("@odata.nextLink")
            if not nxt:
                return items
            page = self.get(nxt, extra_headers=extra_headers)

    def batch(self, requests_list):
        """
        requests_list: [{"method": "POST", "url": "/me/messages/ID/move",
                         "body": {...}}, ...]  (Graph allows 20 per call)
        Returns list of {"id", "status", "body"} in request order.
        """
        results = []
        for start in range(0, len(requests_list), 20):
            chunk = requests_list[start:start + 20]
            payload = {"requests": [
                {"id": str(i), "method": r["method"], "url": r["url"],
                 **({"body": r["body"], "headers": {"Content-Type": "application/json"}}
                    if r.get("body") is not None else {})}
                for i, r in enumerate(chunk)
            ]}
            resp = self.post("$batch", payload)
            ordered = sorted(resp.get("responses", []), key=lambda x: int(x["id"]))
            results.extend(ordered)
        return results

    # ---- legacy helpers kept for existing callers ---------------------
    def get_profile(self):
        return self.get("me", params={"$select": "id,displayName,mail,userPrincipalName"})

    def get_recent_emails(self, limit=10):
        return self.get("me/mailFolders/inbox/messages", params={
            "$top": limit, "$orderby": "receivedDateTime desc",
            "$select": ("id,conversationId,parentFolderId,subject,from,toRecipients,"
                        "receivedDateTime,isRead,importance,bodyPreview,body,hasAttachments"),
        })

    def get_recent_sent_emails(self, limit=20):
        return self.get("me/mailFolders/sentitems/messages", params={
            "$top": limit, "$orderby": "sentDateTime desc",
            "$select": "id,conversationId,subject,from,toRecipients,sentDateTime,bodyPreview",
        })
