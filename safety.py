"""
safety.py — centralized risk classification + confirmation gate.

Single source of truth for:
  * which tools are risky (LOW / MEDIUM / HIGH)
  * whether a specific call (tool + args) requires explicit user confirmation
  * a short human-readable description of what an action will do
  * sanitizing sensitive args before they reach logs / UI / remote bridge

The confirmation gate itself lives in main.py (_execute_tool / _dispatch_tool),
but every decision about risk lives HERE, so a tool can never be gated by
ad-hoc per-tool logic. Extend TOOL_RISK / _ACTION_RISK instead of scattering
checks across the codebase.
"""

import json
import secrets
import threading
import time
from enum import IntEnum
from typing import Any


class Risk(IntEnum):
    LOW = 0      # read-only / harmless — never requires confirmation
    MEDIUM = 1   # can change state, but reversible / low impact
    HIGH = 2     # destructive, irreversible, or arbitrary code — MUST confirm


# ── Per-tool base risk ────────────────────────────────────────────────────────
# Default risk for each tool when it has no action-specific override below.
TOOL_RISK = {
    # Read-only / informational
    "web_search":        Risk.LOW,
    "weather_report":    Risk.LOW,
    "system_status":     Risk.LOW,
    "recall_memory":     Risk.LOW,
    "read_pdf":          Risk.LOW,
    "pdf_qa":            Risk.LOW,
    "read_document":     Risk.LOW,
    "document_qa":       Risk.LOW,
    "monitor_alerts":    Risk.LOW,
    "pc_health":         Risk.LOW,
    "translate":         Risk.LOW,
    "flight_finder":     Risk.LOW,
    "youtube_video":     Risk.LOW,
    "daily_briefing":    Risk.LOW,
    "create_presentation": Risk.LOW,
    "create_spreadsheet": Risk.LOW,
    "google_auth_status": Risk.LOW,

    # Style / memory / personality — local, reversible
    "set_mode":          Risk.LOW,
    "set_voice":         Risk.LOW,
    "set_mood":          Risk.LOW,
    "save_memory":       Risk.LOW,

    # Informational system access
    "screen_process":    Risk.LOW,
    "notify":            Risk.LOW,
    "media_control":     Risk.MEDIUM,

    # State-changing but user-friendly
    "open_app":          Risk.MEDIUM,
    "reminder":          Risk.MEDIUM,
    "schedule":          Risk.MEDIUM,
    "wake_word":         Risk.MEDIUM,
    "clipboard":         Risk.MEDIUM,
    "browser_control":   Risk.MEDIUM,
    "computer_settings": Risk.MEDIUM,
    "computer_control":  Risk.MEDIUM,
    "vision_gesture":    Risk.MEDIUM,
    "vision_click":      Risk.MEDIUM,
    "screen_process":    Risk.LOW,
    "smart_home_control": Risk.MEDIUM,
    "api_add_key":       Risk.MEDIUM,
    "google_auth":       Risk.MEDIUM,

    # Communicate externally
    "send_message":      Risk.MEDIUM,
    "gmail":             Risk.MEDIUM,

    # Arbitrary / destructive
    "cmd_control":       Risk.HIGH,
    "desktop_control":   Risk.HIGH,
    "code_helper":       Risk.MEDIUM,
    "dev_agent":         Risk.MEDIUM,
    "agent_task":        Risk.MEDIUM,
    "file_controller":   Risk.MEDIUM,
    "task_manager":      Risk.MEDIUM,
    "game_updater":      Risk.HIGH,
    "autostart":         Risk.MEDIUM,
    "calendar":          Risk.MEDIUM,
    "drive":             Risk.MEDIUM,
}

# Personal Outlook MCP tools: explicit risk classification.
# All unlisted personal Outlook operations default to HIGH.
PERSONAL_OUTLOOK_READ_ONLY = {
    "outlook_auth_status",
    "outlook_list_inbox",
    "outlook_read_message",
    "outlook_read_messages",
    "outlook_search_mail",
    "outlook_list_folders",
    "outlook_list_inbox_delta",
    "outlook_list_events",
    "outlook_get_event",
    "outlook_find_event_by_key",
    "outlook_list_events_delta",
    "outlook_list_contacts",
    "outlook_search_contacts",
    "outlook_get_contact",
    "outlook_list_task_lists",
    "outlook_list_tasks",
    "outlook_get_task",
    "outlook_list_task_attachments",
    "outlook_list_drafts",
    "outlook_list_attachments",
    "outlook_list_thread",
    "outlook_whoami",
    "outlook_list_calendars",
    "outlook_list_categories",
    "outlook_get_mail_tips",
    "outlook_list_inbox_overrides",
}

PERSONAL_OUTLOOK_HIGH_RISK = {
    "outlook_send_message",
    "outlook_reply",
    "outlook_forward",
    "outlook_move_message",
    "outlook_delete_message",
    "outlook_copy_message",
    "outlook_categorize_message",
    "outlook_reclassify_message",
    "outlook_flag_message",
    "outlook_mark_read",
    "outlook_set_inbox_override",
    "outlook_delete_inbox_override",
    "outlook_create_event",
    "outlook_update_event",
    "outlook_delete_event",
    "outlook_rsvp",
    "outlook_attach_to_event",
    "outlook_remove_event_attachment",
    "outlook_create_contact",
    "outlook_update_contact",
    "outlook_delete_contact",
    "outlook_create_task",
    "outlook_update_task",
    "outlook_complete_task",
    "outlook_delete_task",
    "outlook_add_checklist_item",
    "outlook_update_checklist_item",
    "outlook_delete_checklist_item",
    "outlook_upload_task_attachment",
    "outlook_delete_task_attachment",
    "outlook_create_draft",
    "outlook_update_draft",
    "outlook_send_draft",
    "outlook_delete_draft",
    "outlook_send_with_attachments",
    "outlook_attach_to_draft",
    "outlook_remove_draft_attachment",
    "outlook_create_folder",
    "outlook_rename_folder",
    "outlook_delete_folder",
    "outlook_batch_triage",
}
# ── Action-specific risk overrides ────────────────────────────────────────────
# (tool_name, action) -> Risk. High-impact / irreversible actions are HIGH.
# `None` as the action key means "any other action" for that tool.
_ACTION_RISK = {
    "file_controller": {
        "delete": Risk.HIGH,
        "move": Risk.HIGH,
        "rename": Risk.MEDIUM,
        "organize": Risk.HIGH,
        "organize_desktop": Risk.HIGH,
        "undo_organize": Risk.MEDIUM,
        "write": Risk.MEDIUM,
        "unzip": Risk.HIGH,
        "zip": Risk.MEDIUM,
        None: Risk.MEDIUM,
    },
    "cmd_control": {
        None: Risk.HIGH,
    },
    "desktop_control": {
        None: Risk.HIGH,
    },
    "gmail": {
        "send": Risk.HIGH,
        "compose": Risk.HIGH,
        "delete": Risk.HIGH,
        None: Risk.LOW,
    },
    "outlook": {
        "send_reply": Risk.HIGH,
        "move_email": Risk.HIGH,
        "bulk_organize": Risk.HIGH,
        "delete_folder": Risk.HIGH,
        None: Risk.LOW,
    },
    "task_manager": {
        "kill": Risk.HIGH,
        "end": Risk.HIGH,
        "kill_process": Risk.HIGH,
        None: Risk.MEDIUM,
    },
    "autostart": {
        "enable": Risk.MEDIUM,
        "disable": Risk.MEDIUM,
        "add": Risk.MEDIUM,
        "remove": Risk.MEDIUM,
        "delete": Risk.MEDIUM,
        None: Risk.MEDIUM,
    },
    "code_helper": {
        "run": Risk.HIGH,
        "build": Risk.HIGH,
        "screen_debug": Risk.MEDIUM,
        None: Risk.MEDIUM,
    },
    "computer_settings": {
        "wifi_off": Risk.MEDIUM,
        "wifi_on": Risk.MEDIUM,
        "shutdown": Risk.HIGH,
        "restart": Risk.HIGH,
        "sleep": Risk.HIGH,
        "lock": Risk.MEDIUM,
        None: Risk.MEDIUM,
    },
    "calendar": {
        "delete": Risk.MEDIUM,
        "remove": Risk.MEDIUM,
        "cancel": Risk.MEDIUM,
        None: Risk.MEDIUM,
    },
    "drive": {
        "delete": Risk.HIGH,
        "remove": Risk.HIGH,
        None: Risk.MEDIUM,
    },
    "game_updater": {
        "update": Risk.HIGH,
        "close_game": Risk.MEDIUM,
        "quit_game": Risk.MEDIUM,
        None: Risk.HIGH,
    },
}

# Params that may carry the user's explicit "yes" — the model must set this to
# True after the user verbally approves a high-risk action.
CONFIRM_PARAM = "confirm"

# One-time token issued when a HIGH-risk call is blocked. The model must echo
# it back on the re-invocation; it is single-use and bound to the exact call.
CONFIRM_TOKEN_PARAM = "confirm_token"

# Message returned to the model when a high-risk tool is called WITHOUT the
# user's consent. The model must relay it, wait for an explicit yes, then
# re-invoke the tool with confirm=true.
CONFIRM_MESSAGE = (
    "⛔ This action requires your permission: {desc}. "
    "I must not run it without the user's explicit approval. "
    "Ask the user: 'May I {desc}?' and WAIT for an explicit yes or no. "
    "Only call this tool again with {param}=true after the user says yes."
)

# ── One-time confirmation tokens (technical enforcement) ─────────────────────
# confirm=true is NOT enough on its own: a HIGH-risk call must present a token
# that was issued by this module when the call was first blocked. The model
# cannot fabricate tokens (they are secrets), and each token is single-use and
# bound to the exact (tool, sanitized args) fingerprint of the blocked call.

_pending_tokens: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()
_TOKEN_TTL_SECONDS = 600


def _fingerprint(name: str, args: dict | None) -> str:
    """Canonical fingerprint of a blocked call, so a token can't be replayed
    against a different tool or different arguments."""
    safe = sanitize(name, args or {})
    return json.dumps({"name": name, "args": safe}, sort_keys=True, default=str)


def issue_confirmation_token(name: str, args: dict | None) -> str:
    """Issue a single-use token for this exact call, expiring after the TTL."""
    token = secrets.token_urlsafe(24)
    fingerprint = _fingerprint(name, args)
    created_at = time.monotonic()

    with _token_lock:
        _pending_tokens[token] = (fingerprint, created_at)

    return token


def redeem_confirmation_token(name: str, args: dict | None, token: str) -> bool:
    """Validate and consume a matching, unexpired, single-use token."""
    if not token:
        return False

    with _token_lock:
        entry = _pending_tokens.pop(token, None)

    if entry is None:
        return False

    expected_fingerprint, created_at = entry

    if time.monotonic() - created_at > _TOKEN_TTL_SECONDS:
        return False

    if expected_fingerprint != _fingerprint(name, args):
        return False

    return True


def classify(name: str, args: dict | None) -> Risk:
    """Return risk level for a concrete tool call."""
    args = args or {}

    if name == "personal_outlook":
        action = str(args.get("action", "")).lower().strip()

        if action == "list_tools":
            return Risk.LOW

        if action == "call":
            tool_name = str(args.get("tool_name", "")).strip()

            if tool_name in PERSONAL_OUTLOOK_READ_ONLY:
                return Risk.LOW

            # Mutations, downloads, and unknown tools fail closed.
            return Risk.HIGH

        # Unknown bridge actions also fail closed.
        return Risk.HIGH

    action = str(args.get("action", "")).lower().strip()
    overrides = _ACTION_RISK.get(name)

    if overrides is not None:
        risk = overrides.get(action, overrides.get(None))
        if risk is not None:
            return risk

    return TOOL_RISK.get(name, Risk.MEDIUM)


def needs_confirmation(name: str, args: dict | None, confirm: bool = False,
                       confirm_token: str = "") -> bool:
    """True if this call must not run until the user confirms.

    confirm=true alone does NOT bypass the gate: a valid one-time token issued
    for THIS exact call must be presented too (technical enforcement). This
    stops the model from fabricating a "user said yes" on its own.
    """
    if classify(name, args) != Risk.HIGH:
        return False
    if confirm and redeem_confirmation_token(name, args, confirm_token):
        return False
    return True


def describe(name: str, args: dict | None) -> str:
    """Short human-readable description of what an action will do."""
    args = args or {}
    action = str(args.get("action", "")).lower().strip()

    if name == "personal_outlook":
        tool_name = str(args.get("tool_name", "unknown Outlook operation"))
        return f"perform Personal Outlook operation: {tool_name}"

    if name == "file_controller":
        target = args.get("name") or args.get("path") or "item"
        verbs = {
            "delete": f"delete {target}",
            "move": f"move {target}",
            "rename": f"rename {target}",
            "write": f"write to {target}",
            "unzip": f"extract archive to {args.get('destination', 'target folder')}",
            "organize": f"organize files in {args.get('scope', 'desktop')}",
            "organize_desktop": "organize desktop files",
        }
        return verbs.get(action, f"{action} {target}")

    if name == "cmd_control":
        cmd = args.get("command") or args.get("cmd") or args.get("text") or ""
        return f"run the command: {cmd[:80]}"

    if name == "desktop_control":
        script = args.get("script") or args.get("code") or args.get("text") or ""
        return f"run this code on the desktop: {script[:80]}"

    if name == "gmail" and action in ("send", "compose"):
        return f"send an email to {args.get('to', args.get('recipient', 'recipient'))}"

    if name == "task_manager" and action in ("kill", "end", "kill_process"):
        return f"kill the process {args.get('process', args.get('name', 'unknown'))}"

    if name == "code_helper" and action in ("run", "build"):
        return f"{action} code for {args.get('file_path', args.get('description', 'the task'))}"

    if name in ("game_updater",):
        return f"update the game {args.get('game', '')}"

    if name == "computer_settings" and action in ("shutdown", "restart", "sleep"):
        return f"{action} the computer"

    if name == "drive" and action in ("delete", "remove"):
        return f"delete {args.get('file_id', args.get('name', 'a file'))} from Drive"

    if name == "smart_home_control":
        return f"{action} the {args.get('device', 'smart home device')}"

    # Fallback: tool name + first couple of args
    brief = " ".join(str(v) for v in args.values())[:60]
    return f"{name} ({brief})" if brief else name


# ── Secret redaction for logs / UI / remote ──────────────────────────────────
_SECRET_KEYS = {
    "api_key", "api_key_id", "apikey", "token", "access_token", "auth_token",
    "password", "passwd", "secret", "client_secret", "code", "key",
}


def sanitize(name: str, args: dict | None) -> dict:
    """Return args with sensitive values masked, safe for logging/UI/remote."""
    if not args:
        return {}
    safe = {}
    for k, v in args.items():
        lk = str(k).lower()
        if lk in _SECRET_KEYS or "token" in lk or "key" in lk or "secret" in lk:
            safe[k] = "***"
        elif isinstance(v, dict):
            safe[k] = sanitize(name, v)
        elif isinstance(v, list):
            safe[k] = [sanitize(name, {"i": x})["i"] if isinstance(x, dict) else x for x in v]
        else:
            safe[k] = v
    return safe