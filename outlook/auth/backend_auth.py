"""Desktop client for Ghost's self-hosted Outlook authentication backend."""
import json
import os
import sys
import time
import webbrowser
from urllib.parse import urlparse

import requests

from outlook.config import BACKEND_BASE_URL, BACKEND_SESSION_FILE, CACHE_DIRECTORY


class OutlookBackendError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class BackendAuth:
    uses_backend = True

    def __init__(
        self,
        backend_url=None,
        persistence=None,
        http_session=None,
        browser_open=None,
        poll_interval=1,
        connection_timeout=600,
    ):
        self.backend_url = self._validate_backend_url(
            backend_url or BACKEND_BASE_URL
        )
        if persistence is None:
            if sys.platform != "win32":
                raise OutlookBackendError(
                    "Secure Outlook session storage requires Windows DPAPI."
                )
            from msal_extensions import FilePersistenceWithDataProtection

            CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
            persistence = FilePersistenceWithDataProtection(
                str(BACKEND_SESSION_FILE)
            )
        self._persistence = persistence
        self._http = http_session or requests
        self._browser_open = browser_open or webbrowser.open
        self._poll_interval = poll_interval
        self._connection_timeout = connection_timeout

    @staticmethod
    def _validate_backend_url(value):
        parsed = urlparse(str(value or "").strip())
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme != "https"
                and parsed.hostname not in {"localhost", "127.0.0.1"}
            )
        ):
            raise OutlookBackendError(
                "GHOST_OUTLOOK_BACKEND_URL must use HTTPS, except for localhost development."
            )
        return str(value).strip().rstrip("/")

    def _load_session(self):
        location = self._persistence.get_location()
        if not os.path.isfile(location):
            return None
        stored = self._persistence.load()
        if not stored:
            return None
        try:
            session = json.loads(stored)
        except (TypeError, ValueError) as exc:
            raise OutlookBackendError(
                "The saved Outlook session could not be read securely."
            ) from exc
        if (
            not isinstance(session, dict)
            or not session.get("session_token")
            or not session.get("email")
            or not session.get("identity_id")
        ):
            raise OutlookBackendError(
                "The saved Outlook session is invalid. Disconnect and connect again."
            )
        return session

    def _save_session(self, session):
        self._persistence.save(json.dumps(session, separators=(",", ":")))

    def _clear_session(self):
        self._persistence.save("")

    def _request(self, method, path, *, payload=None, session_token=None):
        headers = {}
        if session_token:
            headers["Authorization"] = f"Bearer {session_token}"
        try:
            response = self._http.request(
                method,
                f"{self.backend_url}{path}",
                json=payload,
                headers=headers,
                timeout=15,
            )
        except requests.exceptions.Timeout as exc:
            raise OutlookBackendError("The Outlook backend request timed out.") from exc
        except requests.exceptions.RequestException as exc:
            raise OutlookBackendError(
                "Could not connect to the configured Outlook backend."
            ) from exc

        if not response.ok:
            message = "The Outlook backend rejected the request."
            try:
                body = response.json()
                detail = body.get("detail")
                if isinstance(detail, str) and detail:
                    message = detail
            except (TypeError, ValueError):
                pass
            raise OutlookBackendError(message, status=response.status_code)
        try:
            result = response.json()
        except ValueError as exc:
            raise OutlookBackendError(
                "The Outlook backend returned an invalid response."
            ) from exc
        if not isinstance(result, dict):
            raise OutlookBackendError(
                "The Outlook backend returned an invalid response."
            )
        return result

    def login(self, email):
        email = str(email or "").strip()
        if not email:
            raise OutlookBackendError(
                "Provide your Microsoft account email to connect Outlook."
            )
        current = self._load_session()
        if current and current.get("email", "").casefold() != email.casefold():
            raise OutlookBackendError(
                "Disconnect the currently connected Outlook account before connecting a different account."
            )

        transaction = self._request(
            "POST",
            "/auth/start",
            payload={"email": email},
        )
        transaction_id = transaction.get("transaction_id")
        transaction_secret = transaction.get("transaction_secret")
        authorization_url = transaction.get("authorization_url")
        parsed_url = urlparse(str(authorization_url or ""))
        if (
            not transaction_id
            or not transaction_secret
            or parsed_url.scheme != "https"
            or parsed_url.hostname != "login.microsoftonline.com"
        ):
            raise OutlookBackendError(
                "The Outlook backend returned an invalid Microsoft sign-in request."
            )
        if not self._browser_open(authorization_url):
            raise OutlookBackendError(
                "Ghost could not open Microsoft's sign-in page."
            )

        deadline = time.monotonic() + self._connection_timeout
        while time.monotonic() < deadline:
            result = self._request(
                "POST",
                "/auth/poll",
                payload={
                    "transaction_id": transaction_id,
                    "transaction_secret": transaction_secret,
                },
            )
            if result.get("status") == "complete":
                token = result.get("session_token")
                if not token:
                    raise OutlookBackendError(
                        "The Outlook backend did not issue a valid Ghost session."
                    )
                status = self._request(
                    "GET",
                    "/account/status",
                    session_token=token,
                )
                if (
                    not status.get("connected")
                    or not status.get("email")
                    or not status.get("identity_id")
                ):
                    raise OutlookBackendError(
                        "Microsoft sign-in completed, but the Outlook account could not be verified."
                    )
                self._save_session({
                    "session_token": token,
                    "email": status["email"],
                    "identity_id": status["identity_id"],
                })
                return status["email"]
            if result.get("status") == "failed":
                raise OutlookBackendError(
                    "Microsoft sign-in did not complete. Start again."
                )
            if result.get("status") != "pending":
                raise OutlookBackendError(
                    "The Outlook backend returned an invalid sign-in status."
                )
            time.sleep(self._poll_interval)

        raise OutlookBackendError(
            "Microsoft sign-in timed out. Start the connection again."
        )

    def get_account_status(self):
        session = self._load_session()
        if not session:
            return {
                "connected": False,
                "email": None,
                "identity_id": None,
                "requires_sign_in": True,
            }
        try:
            status = self._request(
                "GET",
                "/account/status",
                session_token=session["session_token"],
            )
        except OutlookBackendError as exc:
            if exc.status == 401:
                self._clear_session()
                return {
                    "connected": False,
                    "email": None,
                    "identity_id": None,
                    "requires_sign_in": True,
                }
            raise
        return status

    def get_account_name(self):
        status = self.get_account_status()
        return status.get("email") if status.get("connected") else None

    def get_cached_account_context(self):
        session = self._load_session()
        if not session:
            return None
        return {
            "email": session.get("email"),
            "identity_id": session.get("identity_id"),
        }

    def get_identity_id(self):
        session = self._load_session()
        return session.get("identity_id") if session else None

    def get_access_token(self):
        raise OutlookBackendError(
            "Microsoft Graph access tokens are only available inside the Outlook backend."
        )

    def is_authenticated(self):
        return bool(self.get_account_status().get("connected"))

    def logout(self):
        session = self._load_session()
        if not session:
            return True
        try:
            self._request(
                "DELETE",
                "/account",
                session_token=session["session_token"],
            )
        except OutlookBackendError as exc:
            if exc.status != 401:
                raise
        self._clear_session()
        return True

    def graph_request(
        self,
        method,
        endpoint,
        *,
        params=None,
        json_data=None,
        extra_headers=None,
        content_type="application/json",
        raw=False,
    ):
        session = self._load_session()
        if not session:
            raise OutlookBackendError(
                "Connect an Outlook account before using Microsoft Graph."
            )
        return self._http.request(
            "POST",
            f"{self.backend_url}/graph/request",
            json={
                "method": method,
                "endpoint": endpoint,
                "params": params,
                "body": json_data,
                "headers": extra_headers,
                "content_type": content_type,
                "raw": raw,
            },
            headers={"Authorization": f"Bearer {session['session_token']}"},
            timeout=60,
        )
