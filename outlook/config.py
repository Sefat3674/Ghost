"""Ghost Outlook configuration (environment driven)."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "common").strip()

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = "http://localhost"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# Mail.ReadWrite already includes Mail.Read, so the redundant scope is gone.
# MailboxSettings.ReadWrite is needed for auto-reply / timezone / categories.
# NOTE: adding a scope means the user signs in once more to consent.
SCOPES = [
    "User.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Contacts.ReadWrite",
    "MailboxSettings.ReadWrite",
]

_extra = os.getenv("OUTLOOK_EXTRA_SCOPES", "").strip()
if _extra:
    SCOPES += [s for s in _extra.replace(",", " ").split() if s not in SCOPES]

# Optional: pin a specific cached account when several are signed in.
PREFERRED_ACCOUNT = os.getenv("OUTLOOK_ACCOUNT", "").strip().lower()

CACHE_DIRECTORY = (
    Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Ghost" / "Outlook"
)
CACHE_FILE = CACHE_DIRECTORY / "token_cache.bin"
BACKEND_SESSION_FILE = CACHE_DIRECTORY / "backend_session.bin"
BACKEND_BASE_URL = os.getenv(
    "GHOST_OUTLOOK_BACKEND_URL", "http://127.0.0.1:8765"
).strip().rstrip("/")

EMAIL_LIMIT = 10
MAX_LIMIT = 50
REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
BODY_CHAR_LIMIT = 12000
