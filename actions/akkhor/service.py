
"""Shared Akkhor service used by GHOST UI and Gemini tools."""

import json
from pathlib import Path
from urllib.parse import quote

from .auth_manager import AkkhorAuthManager
from .akkhor_client import AkkhorClient


DEFAULT_CONFIG = {
    "base_url": "https://localhost:50268",
    "timeout": 30,

    "endpoints": {
        "login": "/api/Auth/login",
        "me": "/api/Auth/me",

        "classes": "/api/student-enrollments/classes",
        "enrollments": "/api/student-enrollments",
        "students": "/api/student-enrollments/students",
        "assignments": "/api/student-assignments",
        "submissions": "/api/assignment-submissions",

        "class_courses": (
            "/api/student-enrollments/classes/{classId}/courses"
        ),
        "class_sections": (
            "/api/student-enrollments/classes/{classId}/sections"
        ),

        # User Management
        "users": "/api/users",
        "user_details": "/api/users/{id}",
        "user_roles": "/api/users/roles",
        "assign_role": "/api/users/assign-role",
        "reset_password": "/api/users/{id}/reset-password",
        "user_status": "/api/users/{id}/status",
        "user_assigned_roles": "/api/users/{id}/roles"
    }
}


class AkkhorService:

    def __init__(self, project_dir=None):

        self.project_dir = Path(
            project_dir or Path(__file__).resolve().parents[2]
        )

        self.config_path = (
            self.project_dir / "config" / "akkhor_config.json"
        )

        self.config = self._load_config()

        self.auth = AkkhorAuthManager(
            self.config["base_url"],
            self.config.get("timeout", 30)
        )

        self.client = AkkhorClient(
            self.config["base_url"],
            self.auth,
            self.config.get("timeout", 30)
        )

    # --------------------------------------------------
    # CONFIGURATION
    # --------------------------------------------------

    def _load_config(self):

        data = {}

        try:
            if self.config_path.exists():
                data = json.loads(
                    self.config_path.read_text(encoding="utf-8")
                )

        except (json.JSONDecodeError, OSError) as error:
            print(f"[AKKHOR] Config loading error: {error}")

        merged = dict(DEFAULT_CONFIG)

        merged.update({
            key: value
            for key, value in data.items()
            if key != "endpoints"
        })

        merged["endpoints"] = dict(
            DEFAULT_CONFIG["endpoints"]
        )

        if isinstance(data.get("endpoints"), dict):
            merged["endpoints"].update(data["endpoints"])

        merged["base_url"] = str(
            merged.get("base_url") or DEFAULT_CONFIG["base_url"]
        ).rstrip("/")

        return merged

    def _endpoint(self, name, **values):

        endpoint = self.config["endpoints"].get(name)

        if not endpoint:
            return None

        for key, value in values.items():
            endpoint = endpoint.replace(
                "{" + key + "}",
                quote(str(value), safe="")
            )

        if "{" in endpoint or "}" in endpoint:
            return None

        return endpoint

    def _check_auth(self):

        if not self.auth.is_authenticated():
            return {
                "success": False,
                "message": (
                    "Not connected. Sign in from the "
                    "GHOST Akkhor panel first."
                )
            }

        return None

    def _call(self, method, endpoint, payload=None):

        auth_error = self._check_auth()

        if auth_error:
            return auth_error

        if not endpoint:
            return {
                "success": False,
                "message": "API endpoint configuration is missing."
            }

        if method == "GET":
            return self.client.get(endpoint)

        if method == "POST":
            return self.client.post(endpoint, payload)

        if method == "PUT":
            return self.client.put(endpoint, payload)

        if method == "DELETE":
            return self.client.delete(endpoint)

        return {
            "success": False,
            "message": "Unsupported HTTP method."
        }

    # --------------------------------------------------
    # AUTHENTICATION
    # --------------------------------------------------

    def login(self, email, password):
        return self.auth.login(email, password)

    def logout(self):
        self.auth.logout()

    def status(self):

        user = self.auth.user_data or {}

        return {
            "connected": self.auth.is_authenticated(),
            "base_url": self.config["base_url"],
            "user": {
                "fullName": user.get("fullName"),
                "email": user.get("email"),
                "role": user.get("role")
            }
        }

    # --------------------------------------------------
    # EXISTING RESOURCES
    # --------------------------------------------------

    def get_resource(self, resource):

        endpoint = self._endpoint(resource)

        if not endpoint:
            return {
                "success": False,
                "message": f"Unknown Akkhor resource: {resource}"
            }

        return self._call("GET", endpoint)

    def get_class_resource(self, resource, class_id):

        if resource not in ("class_courses", "class_sections"):
            return {
                "success": False,
                "message": "Unsupported class resource."
            }

        if not class_id:
            return {
                "success": False,
                "message": "A class ID is required."
            }

        endpoint = self._endpoint(
            resource,
            classId=class_id
        )

        return self._call("GET", endpoint)

    # --------------------------------------------------
    # USER MANAGEMENT
    # --------------------------------------------------

    def get_users(self):
        return self._call(
            "GET",
            self._endpoint("users")
        )

    def create_user(self, full_name, email, password, role):

        if not all([full_name, email, password, role]):
            return {
                "success": False,
                "message": (
                    "fullName, email, password and role are required."
                )
            }

        payload = {
            "fullName": full_name,
            "email": email,
            "password": password,
            "role": role
        }

        return self._call(
            "POST",
            self._endpoint("users"),
            payload
        )

    def get_user(self, user_id):

        if not user_id:
            return {
                "success": False,
                "message": "User ID is required."
            }

        return self._call(
            "GET",
            self._endpoint("user_details", id=user_id)
        )

    def update_user(
        self,
        user_id,
        full_name,
        email,
        phone_number="",
        is_active=True,
        role=""
    ):

        if not user_id or not full_name or not email:
            return {
                "success": False,
                "message": "User ID, full name and email are required."
            }

        payload = {
            "fullName": full_name,
            "email": email,
            "phoneNumber": phone_number,
            "isActive": is_active,
            "role": role
        }

        return self._call(
            "PUT",
            self._endpoint("user_details", id=user_id),
            payload
        )

    def delete_user(self, user_id):

        if not user_id:
            return {
                "success": False,
                "message": "User ID is required."
            }

        return self._call(
            "DELETE",
            self._endpoint("user_details", id=user_id)
        )

    def get_roles(self):
        return self._call(
            "GET",
            self._endpoint("user_roles")
        )

    def assign_role(self, user_id, role):

        if not user_id or not role:
            return {
                "success": False,
                "message": "User ID and role are required."
            }

        return self._call(
            "PUT",
            self._endpoint("assign_role"),
            {
                "userId": user_id,
                "role": role
            }
        )

    def reset_password(self, user_id, new_password):

        if not user_id or not new_password:
            return {
                "success": False,
                "message": "User ID and new password are required."
            }

        return self._call(
            "PUT",
            self._endpoint("reset_password", id=user_id),
            new_password
        )

    def set_user_status(self, user_id, is_active):

        if not user_id or not isinstance(is_active, bool):
            return {
                "success": False,
                "message": "User ID and boolean status are required."
            }

        return self._call(
            "PUT",
            self._endpoint("user_status", id=user_id),
            is_active
        )

    def get_user_roles(self, user_id):

        if not user_id:
            return {
                "success": False,
                "message": "User ID is required."
            }

        return self._call(
            "GET",
            self._endpoint("user_assigned_roles", id=user_id)
        )

    # --------------------------------------------------
    # GEMINI TOOL ACTION
    # --------------------------------------------------

    def tool_action(self, args):

        args = args or {}

        action = str(
            args.get("action", "status")
        ).strip().lower()

        # Connection status
        if action in ("status", "connection", "connect"):

            state = self.status()

            if state["connected"]:
                user = state["user"]

                return (
                    "Akkhor connected successfully. "
                    f"User: {user.get('fullName') or user.get('email')}. "
                    f"Role: {user.get('role') or 'Not supplied by API'}."
                )

            return (
                "Akkhor is not connected. "
                "Open the GHOST Akkhor panel and sign in."
            )

        # Class resources
        if action in ("class_courses", "class_sections"):

            result = self.get_class_resource(
                action,
                args.get("classId")
            )

        # Existing general resources
        elif action in (
            "classes",
            "enrollments",
            "students",
            "assignments",
            "submissions"
        ):

            result = self.get_resource(action)

        # User Management
        elif action == "users":
            result = self.get_users()

        elif action == "create_user":

            result = self.create_user(
                args.get("fullName"),
                args.get("email"),
                args.get("password"),
                args.get("role")
            )

        elif action == "get_user":

            result = self.get_user(args.get("userId"))

        elif action == "update_user":

            result = self.update_user(
                args.get("userId"),
                args.get("fullName"),
                args.get("email"),
                args.get("phoneNumber", ""),
                args.get("isActive", True),
                args.get("role", "")
            )

        elif action == "delete_user":

            if args.get("confirm") is not True:
                return (
                    "User deletion requires explicit confirmation. "
                    "Ask the user to confirm before retrying."
                )

            result = self.delete_user(args.get("userId"))

        elif action == "roles":
            result = self.get_roles()

        elif action == "assign_role":

            if args.get("confirm") is not True:
                return (
                    "Role assignment requires explicit confirmation. "
                    "Ask the user to confirm before retrying."
                )

            result = self.assign_role(
                args.get("userId"),
                args.get("role")
            )

        elif action == "reset_password":

            if args.get("confirm") is not True:
                return (
                    "Password reset requires explicit confirmation. "
                    "Ask the user to confirm before retrying."
                )

            result = self.reset_password(
                args.get("userId"),
                args.get("newPassword")
            )

        elif action == "set_status":

            if args.get("confirm") is not True:
                return (
                    "Changing account status requires explicit "
                    "confirmation. Ask the user to confirm first."
                )

            result = self.set_user_status(
                args.get("userId"),
                args.get("isActive")
            )

        elif action == "user_roles":

            result = self.get_user_roles(
                args.get("userId")
            )

        else:

            return (
                "Unsupported Akkhor action. Available actions: "
                "status, classes, enrollments, students, assignments, "
                "submissions, class_courses, class_sections, users, "
                "create_user, get_user, update_user, delete_user, "
                "roles, assign_role, reset_password, set_status, "
                "user_roles."
            )

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            default=str
        )
