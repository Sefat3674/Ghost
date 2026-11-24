"""Microsoft identity platform sign-in for Ghost (MSAL public client)."""
import threading

import msal

from outlook.config import AUTHORITY, CLIENT_ID, PREFERRED_ACCOUNT, SCOPES
from outlook.auth.token_manager import create_token_cache


class MicrosoftAuthenticationError(Exception):
    pass


class MicrosoftAuth:
    """Thread-safe wrapper. Use get_auth() to share one instance."""

    def __init__(self):
        if not CLIENT_ID:
            raise MicrosoftAuthenticationError(
                "MICROSOFT_CLIENT_ID is missing. Configure your .env file first."
            )
        self._lock = threading.RLock()
        self.cache = create_token_cache()
        self.app = msal.PublicClientApplication(
            client_id=CLIENT_ID, authority=AUTHORITY, token_cache=self.cache
        )

    # ------------------------------------------------------------------
    def get_accounts(self):
        with self._lock:
            return self.app.get_accounts()

    def _pick_account(self):
        accounts = self.get_accounts()
        if not accounts:
            return None
        if PREFERRED_ACCOUNT:
            for acc in accounts:
                if acc.get("username", "").lower() == PREFERRED_ACCOUNT:
                    return acc
        return accounts[0]

    def get_account_name(self):
        acc = self._pick_account()
        return acc.get("username") if acc else None

    # ------------------------------------------------------------------
    def login(self):
        with self._lock:
            result = self.app.acquire_token_interactive(
                scopes=SCOPES, prompt="select_account"
            )
        if "access_token" not in result:
            raise MicrosoftAuthenticationError(
                result.get("error_description",
                           result.get("error", "Microsoft login failed"))
            )
        return result

    def get_access_token(self):
        """Silent refresh. Returns None when the user must sign in again."""
        with self._lock:
            account = self._pick_account()
            if not account:
                return None
            result = self.app.acquire_token_silent(scopes=SCOPES, account=account)
        if result and "access_token" in result:
            return result["access_token"]
        return None

    def logout(self):
        with self._lock:
            for account in self.get_accounts():
                self.app.remove_account(account)
        return True

    def is_authenticated(self):
        return self.get_access_token() is not None


_instance = None
_instance_lock = threading.Lock()


def get_auth():
    """Shared MicrosoftAuth instance (avoids rebuilding the cache per call)."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MicrosoftAuth()
        return _instance
