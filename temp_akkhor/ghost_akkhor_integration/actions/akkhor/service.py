"""Shared Akkhor service used by the GHOST UI and Gemini tools."""
import json
from pathlib import Path

from .auth_manager import AkkhorAuthManager
from .akkhor_client import AkkhorClient

DEFAULT_CONFIG = {
    "base_url": "https://localhost:50268",
    "timeout": 30,
    "endpoints": {
        "assignments": "/api/assignments",
        "submissions": "/api/assignment-submissions",
        "students": "/api/users"
    }
}


class AkkhorService:
    def __init__(self, project_dir=None):
        self.project_dir = Path(project_dir or Path(__file__).resolve().parents[2])
        self.config_path = self.project_dir / "config" / "akkhor_config.json"
        self.config = self._load_config()
        self.auth = AkkhorAuthManager(self.config["base_url"], self.config.get("timeout", 30))
        self.client = AkkhorClient(self.config["base_url"], self.auth, self.config.get("timeout", 30))

    def _load_config(self):
        data = {}
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        merged = dict(DEFAULT_CONFIG)
        merged.update({k: v for k, v in data.items() if k != "endpoints"})
        merged["endpoints"] = dict(DEFAULT_CONFIG["endpoints"])
        if isinstance(data.get("endpoints"), dict):
            merged["endpoints"].update(data["endpoints"])
        merged["base_url"] = str(merged.get("base_url") or DEFAULT_CONFIG["base_url"]).rstrip("/")
        return merged

    def login(self, email, password):
        result = self.auth.login(email, password)
        return result

    def logout(self):
        self.auth.logout()

    def status(self):
        user = self.auth.user_data or {}
        return {
            "connected": self.auth.is_authenticated(),
            "base_url": self.config["base_url"],
            "user": {"fullName": user.get("fullName"), "email": user.get("email"), "role": user.get("role")}
        }

    def get_resource(self, resource):
        if resource not in self.config["endpoints"]:
            return {"success": False, "message": f"Unknown Akkhor resource: {resource}"}
        if not self.auth.is_authenticated():
            return {"success": False, "message": "Not connected. Sign in from the GHOST Akkhor panel first."}
        return self.client.get(self.config["endpoints"][resource])

    def tool_action(self, args):
        action = str(args.get("action", "status")).strip().lower()
        if action in ("status", "connection", "connect"):
            state = self.status()
            if state["connected"]:
                u = state["user"]
                return f"Akkhor connected as {u.get('fullName') or u.get('email')}. Role: {u.get('role') or 'not supplied by API'}"
            return "Akkhor is not connected. Open the Akkhor panel in GHOST and sign in."
        mapping = {"assignments": "assignments", "submissions": "submissions", "students": "students"}
        if action not in mapping:
            return "Unsupported action. Use status, assignments, submissions, or students."
        result = self.get_resource(mapping[action])
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
