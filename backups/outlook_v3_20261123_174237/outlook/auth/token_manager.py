
from msal_extensions import (
    FilePersistenceWithDataProtection,
    PersistedTokenCache
)

from outlook.config import CACHE_DIRECTORY, CACHE_FILE


def create_token_cache():

    CACHE_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    persistence = FilePersistenceWithDataProtection(
        str(CACHE_FILE)
    )

    return PersistedTokenCache(persistence)
