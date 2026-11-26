"""Configuration for the self-hosted Outlook authentication backend."""
import base64
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from outlook.config import SCOPES


@dataclass(frozen=True)
class BackendSettings:
    client_id: str
    client_secret: str = field(repr=False)
    tenant_id: str = "common"
    redirect_uri: str = ""
    database_path: Path = Path("data/outlook_backend.sqlite3")
    encryption_key: bytes = field(default=b"", repr=False)
    scopes: tuple[str, ...] = tuple(SCOPES)
    transaction_ttl_seconds: int = 600
    session_ttl_seconds: int = 2592000

    @property
    def authority(self):
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @classmethod
    def from_env(cls):
        required = (
            "MICROSOFT_CLIENT_ID",
            "MICROSOFT_CLIENT_SECRET",
            "GHOST_OUTLOOK_REDIRECT_URI",
            "GHOST_OUTLOOK_ENCRYPTION_KEY",
        )
        missing = [name for name in required if not os.getenv(name, "").strip()]
        if missing:
            raise ValueError(
                "Missing required Outlook backend configuration: "
                + ", ".join(missing)
            )

        redirect_uri = os.environ["GHOST_OUTLOOK_REDIRECT_URI"].strip()
        parsed_redirect = urlparse(redirect_uri)
        if (
            parsed_redirect.scheme not in {"https", "http"}
            or not parsed_redirect.netloc
            or parsed_redirect.username
            or parsed_redirect.password
            or parsed_redirect.query
            or parsed_redirect.fragment
            or parsed_redirect.path != "/auth/callback"
            or (
                parsed_redirect.scheme != "https"
                and parsed_redirect.hostname not in {"localhost", "127.0.0.1"}
            )
        ):
            raise ValueError(
                "GHOST_OUTLOOK_REDIRECT_URI must be HTTPS, except for localhost development."
            )

        encoded_key = os.environ["GHOST_OUTLOOK_ENCRYPTION_KEY"].strip()
        try:
            key = base64.urlsafe_b64decode(
                encoded_key + "=" * (-len(encoded_key) % 4)
            )
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError(
                "GHOST_OUTLOOK_ENCRYPTION_KEY must be URL-safe base64 for 32 random bytes."
            ) from exc
        if len(key) != 32:
            raise ValueError(
                "GHOST_OUTLOOK_ENCRYPTION_KEY must be URL-safe base64 for 32 random bytes."
            )

        database_path = Path(
            os.getenv(
                "GHOST_OUTLOOK_DB_PATH",
                str(Path("data") / "outlook_backend.sqlite3"),
            )
        ).expanduser()

        return cls(
            client_id=os.environ["MICROSOFT_CLIENT_ID"].strip(),
            client_secret=os.environ["MICROSOFT_CLIENT_SECRET"],
            tenant_id=os.getenv("MICROSOFT_TENANT_ID", "common").strip() or "common",
            redirect_uri=redirect_uri,
            database_path=database_path,
            encryption_key=key,
        )
