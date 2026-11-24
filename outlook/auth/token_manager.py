"""Persistent MSAL token cache (encrypted with DPAPI on Windows)."""
import sys

from msal_extensions import FilePersistence, PersistedTokenCache

from outlook.config import CACHE_DIRECTORY, CACHE_FILE


def create_token_cache():
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        from msal_extensions import FilePersistenceWithDataProtection
        persistence = FilePersistenceWithDataProtection(str(CACHE_FILE))
    else:
        # Non-Windows fallback so the module still works in dev/CI.
        persistence = FilePersistence(str(CACHE_FILE))

    return PersistedTokenCache(persistence)
