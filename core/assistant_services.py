"""Shared prompt, API-key, quota, and memory services for the assistant."""

import threading
from pathlib import Path

from memory.memory_manager import (
    extract_memory,
    should_extract_memory,
    update_memory,
)


_last_memory_input = ""
_memory_lock = threading.Lock()
_memory_running = False


def get_api_key() -> str:
    from api_keys import next_key
    return next_key()


def looks_like_quota(err: str) -> bool:
    error = (err or "").lower()
    return any(
        token in error
        for token in ("resource_exhausted", "429", "quota", "rate limit")
    )


def load_system_prompt(prompt_path: Path) -> str:
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are GHOST, a sharp and efficient AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â always call the appropriate tool."
        )


def update_memory_async(user_text: str, assistant_text: str) -> None:
    global _last_memory_input, _memory_running

    user_text = (user_text or "").strip()
    assistant_text = (assistant_text or "").strip()

    if len(user_text) < 5 or user_text == _last_memory_input:
        print("[Memory] Skipped: short or duplicate user text.")
        return

    with _memory_lock:
        if _memory_running:
            print("[Memory] Already extracting ? skipping this turn.")
            return
        _memory_running = True

    _last_memory_input = user_text

    try:
        print("[Memory] Automatic extraction started.")
        api_key = get_api_key()

        detected = should_extract_memory(user_text, assistant_text, api_key)
        print(f"[Memory] Detection result: {detected}")

        if not detected:
            print("[Memory] No memorable information detected.")
            return

        data = extract_memory(user_text, assistant_text, api_key)
        print(f"[Memory] Extraction result: {data}")

        if data:
            update_memory(data)
            print(f"[Memory] Automatically saved: {list(data.keys())}")
        else:
            print("[Memory] Extraction returned no data.")

    except Exception as error:
        if "429" not in str(error):
            print(f"[Memory] Automatic extraction error: {error}")
        else:
            print("[Memory] Gemini rate limit reached (429).")

    finally:
        with _memory_lock:
            _memory_running = False
