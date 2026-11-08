"""Akkhor JWT authentication for GHOST. Tokens remain in memory only."""
from datetime import datetime, timezone
import json
import urllib.error
import urllib.request


class AkkhorAuthManager:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = None
        self.expires_at = None
        self.user_data = None

    def login(self, email: str, password: str) -> dict:
        url = f"{self.base_url}/api/Auth/login"
        payload = json.dumps({"email": email, "password": password}).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                result = json.loads(body) if body else {}
            token = result.get("token")
            expires = result.get("expiresAt")
            if not token or not expires:
                return {"success": False, "message": "Akkhor response did not contain token and expiresAt."}
            parsed = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            self.token = token
            self.expires_at = parsed.astimezone(timezone.utc)
            self.user_data = {
                "userId": result.get("userId"),
                "fullName": result.get("fullName"),
                "email": result.get("email"),
                "role": result.get("role"),
            }
            return {"success": True, "user": dict(self.user_data), "expiresAt": expires}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return {"success": False, "status_code": exc.code, "message": detail or str(exc)}
        except urllib.error.URLError as exc:
            return {"success": False, "message": f"Cannot reach Akkhor API: {exc.reason}"}
        except (ValueError, TypeError) as exc:
            return {"success": False, "message": f"Invalid login response: {exc}"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def is_authenticated(self) -> bool:
        return bool(self.token and self.expires_at and datetime.now(timezone.utc) < self.expires_at)

    def get_auth_headers(self) -> dict:
        if not self.is_authenticated():
            self.logout()
            raise RuntimeError("Akkhor session expired. Please log in again.")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def logout(self) -> None:
        self.token = None
        self.expires_at = None
        self.user_data = None
