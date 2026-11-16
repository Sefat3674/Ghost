import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
TENANT_ID = os.getenv("MICROSOFT_TENANT_ID", "consumers").strip()

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = "http://localhost"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

SCOPES = [
    "User.Read",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Contacts.ReadWrite"
]

CACHE_DIRECTORY = (
    Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    / "Ghost" / "Outlook"
)
CACHE_FILE = CACHE_DIRECTORY / "token_cache.bin"

EMAIL_LIMIT = 10
REQUEST_TIMEOUT = 30
