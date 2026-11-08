"""Small authenticated HTTP client for the Akkhor ASP.NET Core API."""
import json
import urllib.error
import urllib.request


class AkkhorClient:
    def __init__(self, base_url: str, auth_manager, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.auth = auth_manager
        self.timeout = timeout

    def request(self, method: str, endpoint: str, payload=None):
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + endpoint,
            data=data,
            headers=self.auth.get_auth_headers(),
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                try:
                    body = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    body = raw
                return {"success": True, "status_code": response.status, "data": body}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                detail = raw
            return {"success": False, "status_code": exc.code, "message": detail or str(exc)}
        except urllib.error.URLError as exc:
            return {"success": False, "message": f"Network error: {exc.reason}"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def get(self, endpoint: str):
        return self.request("GET", endpoint)
