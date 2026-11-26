"""Microsoft OAuth and per-user token operations for the backend."""
import hashlib
import hmac
import json
import re
import secrets
import threading
import uuid

import msal

from outlook.backend.token_store import TokenStore

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthenticationError(Exception):
    """A safe-to-display authentication or connection error."""


class OutlookAuthService:
    def __init__(self, settings, token_store=None, msal_factory=None):
        self.settings = settings
        self.store = token_store or TokenStore(
            settings.database_path, settings.encryption_key
        )
        self._msal_factory = msal_factory or msal.ConfidentialClientApplication
        self._owner_locks = {}
        self._owner_locks_guard = threading.Lock()

    def _owner_lock(self, owner_id):
        with self._owner_locks_guard:
            return self._owner_locks.setdefault(owner_id, threading.RLock())

    def _application(self, token_cache=None):
        return self._msal_factory(
            client_id=self.settings.client_id,
            client_credential=self.settings.client_secret,
            authority=self.settings.authority,
            token_cache=token_cache,
        )

    def start_connection(self, email):
        email = str(email or "").strip()
        if len(email) > 320 or not _EMAIL_RE.fullmatch(email):
            raise AuthenticationError("Enter a valid Microsoft account email address.")

        transaction_id = uuid.uuid4().hex
        transaction_secret = secrets.token_urlsafe(32)
        app = self._application()
        try:
            flow = app.initiate_auth_code_flow(
                scopes=list(self.settings.scopes),
                redirect_uri=self.settings.redirect_uri,
                login_hint=email,
                response_mode="form_post",
            )
        except Exception as exc:
            raise AuthenticationError(
                "Microsoft sign-in could not be started. Check the backend configuration."
            ) from exc

        if not isinstance(flow, dict) or not flow.get("auth_uri") or not flow.get("state"):
            raise AuthenticationError(
                "Microsoft sign-in could not be started. Check the Entra app registration."
            )

        self.store.create_oauth_transaction(
            transaction_id=transaction_id,
            secret=transaction_secret,
            state=flow["state"],
            flow=json.dumps(flow, separators=(",", ":")),
            ttl=self.settings.transaction_ttl_seconds,
        )
        return {
            "transaction_id": transaction_id,
            "transaction_secret": transaction_secret,
            "authorization_url": flow["auth_uri"],
        }

    def complete_connection(self, transaction_id, auth_response):
        state = auth_response.get("state")
        serialized_flow = self.store.load_oauth_flow(transaction_id, state)
        if serialized_flow is None:
            raise AuthenticationError(
                "Microsoft sign-in expired or could not be validated. Start again."
            )

        cache = msal.SerializableTokenCache()
        app = self._application(token_cache=cache)
        try:
            result = app.acquire_token_by_auth_code_flow(
                json.loads(serialized_flow), auth_response
            )
        except Exception as exc:
            self.store.fail_oauth_transaction(transaction_id)
            raise AuthenticationError(
                "Microsoft sign-in could not be completed. Start again."
            ) from exc

        if not isinstance(result, dict):
            self.store.fail_oauth_transaction(transaction_id)
            raise AuthenticationError(
                "Microsoft sign-in could not be completed. Start again."
            )
        claims = result.get("id_token_claims") or {}
        if not isinstance(claims, dict):
            claims = {}
        tenant_id = str(claims.get("tid") or "").strip()
        object_id = str(claims.get("oid") or "").strip()
        email = str(
            claims.get("preferred_username") or claims.get("email") or ""
        ).strip()
        if (
            "access_token" not in result
            or not tenant_id
            or not object_id
            or not _EMAIL_RE.fullmatch(email)
        ):
            self.store.fail_oauth_transaction(transaction_id)
            raise AuthenticationError(
                "Microsoft did not return a usable account identity. Start again."
            )

        owner_id = f"{tenant_id}:{object_id}"
        try:
            serialized_cache = cache.serialize()
            with self._owner_lock(owner_id):
                self.store.complete_oauth_transaction(
                    transaction_id=transaction_id,
                    owner_id=owner_id,
                    tenant_id=tenant_id,
                    object_id=object_id,
                    email=email,
                    serialized_cache=serialized_cache,
                )
        except Exception as exc:
            self.store.fail_oauth_transaction(transaction_id)
            raise AuthenticationError(
                "The Outlook connection could not be stored securely."
            ) from exc
        return email

    def poll_connection(self, transaction_id, transaction_secret):
        if not transaction_id or not transaction_secret:
            return {"status": "invalid"}
        return self.store.poll_oauth_transaction(
            transaction_id,
            transaction_secret,
            self.settings.session_ttl_seconds,
        )

    def _owner_for_session(self, session_token):
        owner_id = self.store.resolve_session(session_token)
        if owner_id is None:
            raise AuthenticationError("The Ghost session is invalid or expired.")
        return owner_id

    def get_account_status(self, session_token):
        owner_id = self._owner_for_session(session_token)
        with self._owner_lock(owner_id):
            account = self.store.get_account(owner_id)
            if account is None:
                raise AuthenticationError("No Outlook account is connected.")

            cache = msal.SerializableTokenCache()
            cache.deserialize(account["cache"])
            app = self._application(token_cache=cache)
            accounts = app.get_accounts()
            if not accounts:
                return {
                    "connected": False,
                    "email": account["email"],
                    "identity_id": self._identity_id(owner_id),
                    "requires_sign_in": True,
                }
            result = app.acquire_token_silent(
                scopes=list(self.settings.scopes),
                account=accounts[0],
            )
            if not result or "access_token" not in result:
                return {
                    "connected": False,
                    "email": account["email"],
                    "identity_id": self._identity_id(owner_id),
                    "requires_sign_in": True,
                }
            if cache.has_state_changed:
                self.store.update_cache(owner_id, cache.serialize())
            return {
                "connected": True,
                "email": account["email"],
                "identity_id": self._identity_id(owner_id),
                "requires_sign_in": False,
            }

    def _identity_id(self, owner_id):
        digest = hmac.new(
            self.settings.encryption_key,
            owner_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return digest[:32]

    def acquire_access_token(self, session_token):
        owner_id = self._owner_for_session(session_token)
        with self._owner_lock(owner_id):
            account_record = self.store.get_account(owner_id)
            if account_record is None:
                raise AuthenticationError("No Outlook account is connected.")

            cache = msal.SerializableTokenCache()
            cache.deserialize(account_record["cache"])
            app = self._application(token_cache=cache)
            accounts = app.get_accounts()
            if not accounts:
                raise AuthenticationError("Sign in to Outlook again to continue.")

            result = app.acquire_token_silent(
                scopes=list(self.settings.scopes),
                account=accounts[0],
            )
            if not result or "access_token" not in result:
                raise AuthenticationError("Sign in to Outlook again to continue.")
            if cache.has_state_changed:
                self.store.update_cache(owner_id, cache.serialize())
            return result["access_token"]

    def disconnect(self, session_token):
        owner_id = self._owner_for_session(session_token)
        with self._owner_lock(owner_id):
            self.store.disconnect(owner_id)
        return {"connected": False}
