
import msal

from outlook.config import (
    CLIENT_ID,
    AUTHORITY,
    SCOPES
)

from outlook.auth.token_manager import create_token_cache


class MicrosoftAuthenticationError(Exception):
    pass


class MicrosoftAuth:

    def __init__(self):

        if not CLIENT_ID:
            raise MicrosoftAuthenticationError(
                "MICROSOFT_CLIENT_ID is missing. "
                "Configure your .env file first."
            )

        self.cache = create_token_cache()

        self.app = msal.PublicClientApplication(
            client_id=CLIENT_ID,
            authority=AUTHORITY,
            token_cache=self.cache
        )

    def get_accounts(self):

        return self.app.get_accounts()

    def login(self):

        result = self.app.acquire_token_interactive(
            scopes=SCOPES,
            prompt="select_account"
        )

        if "access_token" not in result:

            raise MicrosoftAuthenticationError(
                result.get(
                    "error_description",
                    result.get("error", "Microsoft login failed")
                )
            )

        return result

    def get_access_token(self):

        accounts = self.get_accounts()

        if not accounts:
            return None

        result = self.app.acquire_token_silent(
            scopes=SCOPES,
            account=accounts[0]
        )

        if result and "access_token" in result:
            return result["access_token"]

        return None

    def logout(self):

        accounts = self.get_accounts()

        for account in accounts:
            self.app.remove_account(account)

        return True

    def is_authenticated(self):

        return self.get_access_token() is not None
