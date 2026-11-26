import base64
import json
import requests
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from outlook.backend.auth_service import AuthenticationError, OutlookAuthService
from outlook.backend.config import BackendSettings
from outlook.backend.graph_proxy import validate_graph_request
from outlook.services.graph_client import GraphAPIError, GraphClient
from outlook.config import SCOPES
from safety import _fingerprint, sanitize
from outlook.auth.backend_auth import BackendAuth, OutlookBackendError


_ENCRYPTION_KEY = b"mock-only-encryption-key-32bytes"


class FakeTokenCache:
    def __init__(self):
        self.payload = ""
        self.has_state_changed = False

    def deserialize(self, payload):
        self.payload = payload

    def serialize(self):
        return self.payload


class FakePersistence:
    def __init__(self, path):
        self.path = Path(path)

    def get_location(self):
        return str(self.path)

    def save(self, content):
        self.path.write_text(content, encoding="utf-8")

    def load(self):
        return self.path.read_text(encoding="utf-8")


class FakeHTTPResponse:
    def __init__(self, body, status=200):
        self._body = body
        self.status_code = status
        self.ok = 200 <= status < 300
        self.content = json.dumps(body).encode("utf-8") if body else b""

    def json(self):
        return self._body


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class FakeMSALApplication:
    next_state = 0
    last_flow = None
    instances = []
    silent_result = {"access_token": "mock-refreshed-access-token"}
    silent_calls = []

    def __init__(self, client_id, client_credential, authority, token_cache=None):
        self.client_id = client_id
        self.client_credential = client_credential
        self.authority = authority
        self.token_cache = token_cache or FakeTokenCache()
        type(self).instances.append(self)

    def initiate_auth_code_flow(
        self, scopes, redirect_uri, login_hint, response_mode
    ):
        type(self).next_state += 1
        state = f"mock-state-{type(self).next_state}"
        type(self).last_flow = {
            "state": state,
            "auth_uri": f"https://login.microsoftonline.com/authorize?state={state}",
            "code_verifier": "mock-pkce-verifier",
            "redirect_uri": redirect_uri,
            "response_mode": response_mode,
        }
        self.scopes = scopes
        self.login_hint = login_hint
        self.response_mode = response_mode
        return type(self).last_flow

    def acquire_token_by_auth_code_flow(self, flow, auth_response):
        identity = auth_response.get("identity")
        if identity is None:
            identity = json.loads(auth_response["mock_identity"])
        self.token_cache.payload = json.dumps({
            "email": identity["email"],
            "access_marker": "mock-access-token-never-returned",
            "refresh_marker": "mock-refresh-token-never-returned",
        })
        self.token_cache.has_state_changed = True
        return {
            "access_token": "mock-access-token-never-returned",
            "id_token_claims": {
                "tid": identity["tid"],
                "oid": identity["oid"],
                "preferred_username": identity["email"],
            },
        }

    def get_accounts(self):
        if not self.token_cache.payload:
            return []
        account = json.loads(self.token_cache.payload)
        return [{"username": account["email"]}]

    def acquire_token_silent(self, scopes, account):
        type(self).silent_calls.append((scopes, account))
        return type(self).silent_result


class OutlookBackendAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.settings = BackendSettings(
            client_id="mock-client-id",
            client_secret="mock-client-secret",
            tenant_id="common",
            redirect_uri="https://ghost.example.test/auth/callback",
            database_path=Path(self.temp_directory.name) / "tokens.sqlite3",
            encryption_key=_ENCRYPTION_KEY,
            scopes=tuple(SCOPES),
            transaction_ttl_seconds=600,
            session_ttl_seconds=3600,
        )
        FakeMSALApplication.next_state = 0
        FakeMSALApplication.last_flow = None
        FakeMSALApplication.instances = []
        FakeMSALApplication.silent_result = {
            "access_token": "mock-refreshed-access-token"
        }
        FakeMSALApplication.silent_calls = []
        self.cache_patch = patch(
            "outlook.backend.auth_service.msal.SerializableTokenCache",
            FakeTokenCache,
        )
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.service = OutlookAuthService(
            self.settings,
            msal_factory=FakeMSALApplication,
        )

    def _connect(self, email, tenant_id, object_id):
        started = self.service.start_connection(email)
        self.service.complete_connection(
            started["transaction_id"],
            {
                "state": FakeMSALApplication.last_flow["state"],
                "code": "mock-authorization-code",
                "identity": {
                    "email": email,
                    "tid": tenant_id,
                    "oid": object_id,
                },
            },
        )
        completed = self.service.poll_connection(
            started["transaction_id"],
            started["transaction_secret"],
        )
        self.assertEqual(completed["status"], "complete")
        return completed["session_token"]

    def test_personal_and_work_accounts_use_common_authority(self):
        personal_session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        work_session = self._connect(
            "employee@contoso.example", "business-tenant", "work-object"
        )
        self.assertEqual(
            [app.authority for app in FakeMSALApplication.instances],
            [
                "https://login.microsoftonline.com/common",
                "https://login.microsoftonline.com/common",
                "https://login.microsoftonline.com/common",
                "https://login.microsoftonline.com/common",
            ],
        )
        self.assertTrue(
            all(
                app.response_mode == "form_post"
                for app in FakeMSALApplication.instances
                if hasattr(app, "response_mode")
            )
        )
        self.assertTrue(self.service.get_account_status(personal_session)["connected"])
        self.assertTrue(self.service.get_account_status(work_session)["connected"])

    def test_email_hint_is_used_without_treating_it_as_identity_proof(self):
        started = self.service.start_connection("person@hotmail.com")
        self.assertEqual(
            FakeMSALApplication.instances[-1].login_hint,
            "person@hotmail.com",
        )
        self.service.complete_connection(
            started["transaction_id"],
            {
                "state": FakeMSALApplication.last_flow["state"],
                "code": "mock-authorization-code",
                "identity": {
                    "email": "verified@outlook.com",
                    "tid": "consumer-tenant",
                    "oid": "verified-object",
                },
            },
        )
        completed = self.service.poll_connection(
            started["transaction_id"],
            started["transaction_secret"],
        )
        self.assertEqual(completed["email"], "verified@outlook.com")

    def test_multiple_users_have_isolated_encrypted_caches_and_sessions(self):
        personal_session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        work_session = self._connect(
            "employee@contoso.example", "business-tenant", "work-object"
        )

        self.assertEqual(
            self.service.get_account_status(personal_session)["email"],
            "person@outlook.com",
        )
        self.assertEqual(
            self.service.get_account_status(work_session)["email"],
            "employee@contoso.example",
        )
        self.assertNotEqual(
            self.service.store.resolve_session(personal_session),
            self.service.store.resolve_session(work_session),
        )

        raw_database = Path(self.settings.database_path).read_bytes()
        self.assertNotIn(b"mock-access-token-never-returned", raw_database)
        self.assertNotIn(b"mock-refresh-token-never-returned", raw_database)

    def test_access_token_refresh_stays_server_side(self):
        session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        token = self.service.acquire_access_token(session)
        self.assertEqual(token, "mock-refreshed-access-token")
        self.assertEqual(
            FakeMSALApplication.silent_calls[0][0],
            list(self.settings.scopes),
        )
        status = self.service.get_account_status(session)
        self.assertNotIn("access_token", status)
        self.assertNotIn("refresh_token", status)

    def test_expired_session_is_rejected(self):
        session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        with patch("outlook.backend.token_store.time.time", return_value=10**12):
            with self.assertRaisesRegex(
                AuthenticationError, "invalid or expired"
            ):
                self.service.get_account_status(session)

    def test_expired_or_revoked_microsoft_token_requires_sign_in(self):
        session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        FakeMSALApplication.silent_result = None
        status = self.service.get_account_status(session)
        self.assertFalse(status["connected"])
        self.assertTrue(status["requires_sign_in"])

    def test_disconnect_removes_only_the_authenticated_users_account(self):
        personal_session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        work_session = self._connect(
            "employee@contoso.example", "business-tenant", "work-object"
        )

        self.service.disconnect(personal_session)
        with self.assertRaisesRegex(AuthenticationError, "invalid or expired"):
            self.service.get_account_status(personal_session)
        self.assertEqual(
            self.service.get_account_status(work_session)["email"],
            "employee@contoso.example",
        )

    def test_api_does_not_allow_requesting_another_users_account(self):
        personal_session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        work_session = self._connect(
            "employee@contoso.example", "business-tenant", "work-object"
        )
        from outlook.backend.api import create_app

        client = TestClient(create_app(self.settings, self.service))
        response = client.get(
            "/account/status?owner_id=consumer-tenant%3Apersonal-object",
            headers={"Authorization": f"Bearer {work_session}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "employee@contoso.example")
        self.assertNotEqual(
            response.json()["email"],
            self.service.get_account_status(personal_session)["email"],
        )
        disconnected = client.delete(
            "/account?owner_id=consumer-tenant%3Apersonal-object",
            headers={"Authorization": f"Bearer {work_session}"},
        )
        self.assertEqual(disconnected.status_code, 200)
        self.assertEqual(
            self.service.get_account_status(personal_session)["email"],
            "person@outlook.com",
        )

    def test_api_callback_and_status_never_return_graph_tokens(self):
        from outlook.backend.api import create_app

        client = TestClient(create_app(self.settings, self.service))
        started = client.post(
            "/auth/start",
            json={"email": "person@outlook.com"},
        )
        self.assertEqual(started.status_code, 200)
        transaction = started.json()
        callback = client.post(
            "/auth/callback",
            content=urlencode({
                "state": FakeMSALApplication.last_flow["state"],
                "code": "mock-authorization-code",
                "mock_identity": json.dumps({
                    "email": "person@outlook.com",
                    "tid": "consumer-tenant",
                    "oid": "personal-object",
                }),
            }),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(callback.status_code, 200)

        completed = client.post(
            "/auth/poll",
            json={
                "transaction_id": transaction["transaction_id"],
                "transaction_secret": transaction["transaction_secret"],
            },
        )
        session = completed.json()["session_token"]
        status = client.get(
            "/account/status",
            headers={"Authorization": f"Bearer {session}"},
        )
        self.assertEqual(status.json()["email"], "person@outlook.com")
        self.assertNotIn("access_token", status.text)
        self.assertNotIn("refresh_token", status.text)

    def test_desktop_connect_opens_microsoft_and_persists_only_ghost_session(self):
        http = FakeHTTP([
            FakeHTTPResponse({
                "transaction_id": "mock-transaction",
                "transaction_secret": "mock-transaction-secret",
                "authorization_url": (
                    "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
                ),
            }),
            FakeHTTPResponse({"status": "complete", "session_token": "ghost-session"}),
            FakeHTTPResponse({
                "connected": True,
                "email": "person@outlook.com",
                "identity_id": "mock-owner-id",
                "requires_sign_in": False,
            }),
        ])
        browser_urls = []
        persistence_path = Path(self.temp_directory.name) / "desktop-session.json"
        auth = BackendAuth(
            backend_url="https://ghost.example.test",
            persistence=FakePersistence(persistence_path),
            http_session=http,
            browser_open=lambda url: browser_urls.append(url) or True,
            poll_interval=0,
            connection_timeout=1,
        )

        self.assertEqual(auth.login("person@outlook.com"), "person@outlook.com")
        self.assertEqual(len(browser_urls), 1)
        self.assertEqual(
            browser_urls[0],
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        )
        self.assertEqual(auth.get_cached_account_context(), {
            "email": "person@outlook.com",
            "identity_id": "mock-owner-id",
        })
        stored = persistence_path.read_text(encoding="utf-8")
        self.assertIn("ghost-session", stored)
        self.assertNotIn("mock-access-token", stored)
        self.assertNotIn("mock-refresh-token", stored)
        self.assertEqual(http.calls[0][2]["json"], {"email": "person@outlook.com"})
        self.assertEqual(
            http.calls[2][2]["headers"]["Authorization"],
            "Bearer ghost-session",
        )
        with self.assertRaisesRegex(
            OutlookBackendError, "only available inside the Outlook backend"
        ):
            auth.get_access_token()

    def test_desktop_requires_disconnect_before_switching_accounts(self):
        persistence_path = Path(self.temp_directory.name) / "desktop-session.json"
        persistence = FakePersistence(persistence_path)
        persistence.save(json.dumps({
            "session_token": "mock-old-session",
            "email": "first@outlook.com",
            "identity_id": "mock-old-owner",
        }))
        http = FakeHTTP([])
        auth = BackendAuth(
            backend_url="https://ghost.example.test",
            persistence=persistence,
            http_session=http,
            browser_open=lambda _url: True,
        )
        with self.assertRaisesRegex(OutlookBackendError, "Disconnect the currently"):
            auth.login("second@outlook.com")
        self.assertEqual(http.calls, [])

    def test_graph_proxy_binds_calls_to_the_signed_in_mailbox(self):
        session = self._connect(
            "person@outlook.com", "consumer-tenant", "personal-object"
        )
        from outlook.backend.api import create_app

        calls = []

        class FakeGraphClient:
            def __init__(self, token_provider):
                self.token_provider = token_provider

            def _url(self, endpoint):
                return endpoint

            def _send(self, method, url, **kwargs):
                calls.append((method, url, self.token_provider(), kwargs))
                return {"value": []}

        client = TestClient(create_app(self.settings, self.service))
        with patch("outlook.backend.api.GraphClient", FakeGraphClient):
            valid = client.post(
                "/graph/request",
                json={
                    "method": "GET",
                    "endpoint": "https://graph.microsoft.com/v1.0/me/messages",
                },
                headers={"Authorization": f"Bearer {session}"},
            )
            blocked = client.post(
                "/graph/request",
                json={
                    "method": "GET",
                    "endpoint": "https://graph.microsoft.com/v1.0/users/victim/messages",
                },
                headers={"Authorization": f"Bearer {session}"},
            )

        self.assertEqual(valid.status_code, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], "mock-refreshed-access-token")
        self.assertEqual(blocked.status_code, 400)
        self.assertNotIn("access_token", valid.text)

    def test_graph_target_validation_rejects_cross_user_and_credential_headers(self):
        validate_graph_request(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages?$top=5",
        )
        with self.assertRaisesRegex(ValueError, "signed-in user's"):
            validate_graph_request(
                "GET",
                "https://graph.microsoft.com/v1.0/users/another-user/messages",
            )
        with self.assertRaisesRegex(ValueError, "Authentication and transport"):
            validate_graph_request(
                "GET",
                "me/messages",
                headers={"Authorization": "Bearer forged"},
            )

    def test_graph_client_uses_backend_without_receiving_graph_tokens(self):
        transport = Mock()
        transport.graph_request.return_value = FakeHTTPResponse(
            {"value": [{"id": "mock-message"}]}
        )
        graph = GraphClient(backend_transport=transport)

        result = graph.get("me/messages")

        self.assertEqual(result["value"][0]["id"], "mock-message")
        self.assertIsNone(graph.access_token)
        request = transport.graph_request.call_args
        self.assertEqual(request.args[:2], (
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages",
        ))

    def test_graph_backend_timeout_does_not_retry_mutations(self):
        transport = Mock()
        transport.graph_request.side_effect = requests.exceptions.Timeout(
            "mock uncertain request"
        )
        graph = GraphClient(backend_transport=transport)
        with self.assertRaises(GraphAPIError):
            graph.post("me/sendMail", {"message": {}})
        transport.graph_request.assert_called_once()

    def test_approval_fingerprint_is_mailbox_scoped_but_log_redacted(self):
        base = {
            "action": "send_email",
            "to": "recipient@example.test",
            "subject": "Mock only",
            "body": "No real email",
        }
        account_a = {**base, "_ghost_outlook_identity": "mock-account-a"}
        account_b = {**base, "_ghost_outlook_identity": "mock-account-b"}
        self.assertNotEqual(
            _fingerprint("outlook", account_a),
            _fingerprint("outlook", account_b),
        )
        self.assertEqual(
            sanitize("outlook", account_a)["_ghost_outlook_identity"],
            "***",
        )

    def test_main_binds_approval_to_verified_identity_not_model_input(self):
        import main
        from outlook import config

        with tempfile.TemporaryDirectory() as directory:
            session_file = Path(directory) / "session.bin"
            session_file.write_bytes(b"mock DPAPI session marker")
            auth = Mock()
            auth.get_cached_account_context.return_value = {
                "email": "person@outlook.com",
                "identity_id": "verified-owner-id",
            }
            args = {
                "action": "send_email",
                "to": "recipient@example.test",
                "_ghost_outlook_identity": "forged-by-model",
            }
            with patch.object(config, "BACKEND_SESSION_FILE", session_file), patch(
                "outlook.auth.microsoft_auth.get_auth",
                return_value=auth,
            ):
                error = main._bind_outlook_approval_identity("outlook", args)

        self.assertIsNone(error)
        self.assertEqual(args["_ghost_outlook_identity"], "verified-owner-id")

    def test_bad_state_and_untrusted_email_identity_are_rejected(self):
        started = self.service.start_connection("person@outlook.com")
        with self.assertRaisesRegex(
            AuthenticationError, "expired or could not be validated"
        ):
            self.service.complete_connection(
                started["transaction_id"],
                {
                    "state": "forged-state",
                    "code": "mock-authorization-code",
                    "identity": {
                        "email": "person@outlook.com",
                        "tid": "consumer-tenant",
                        "oid": "personal-object",
                    },
                },
            )

    def test_settings_require_a_strong_server_encryption_key_and_https_redirect(self):
        key = base64.urlsafe_b64encode(_ENCRYPTION_KEY).decode("ascii")
        env = {
            "MICROSOFT_CLIENT_ID": "mock-client-id",
            "MICROSOFT_CLIENT_SECRET": "mock-client-secret",
            "GHOST_OUTLOOK_REDIRECT_URI": "https://ghost.example.test/auth/callback",
            "GHOST_OUTLOOK_ENCRYPTION_KEY": key,
            "MICROSOFT_TENANT_ID": "common",
        }
        with patch.dict("os.environ", env, clear=True):
            configured = BackendSettings.from_env()
        self.assertEqual(configured.tenant_id, "common")
        self.assertEqual(configured.authority, "https://login.microsoftonline.com/common")
        self.assertEqual(configured.encryption_key, _ENCRYPTION_KEY)

        env["GHOST_OUTLOOK_REDIRECT_URI"] = "http://example.test/auth/callback"
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(ValueError, "must be HTTPS"):
                BackendSettings.from_env()


if __name__ == "__main__":
    unittest.main()
