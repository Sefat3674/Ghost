"""Assistant mode and voice preference normalization."""

VOICES = {
    "Achernar":      "mayin (Soft)",
    "Achird":        "do'stona (Friendly)",
    "Algenib":       "bo'g'iq (Gravelly)",
    "Algieba":       "silliq (Smooth)",
    "Alnilam":       "qat'iy (Firm)",
    "Aoede":         "engil ayol (Breezy)",
    "Autonoe":       "yorqin (Bright)",
    "Callirrhoe":    "erkin (Easy-going)",
    "Charon":        "chuqur erkak (Informative)",
    "Despina":       "silliq (Smooth)",
    "Enceladus":     "nafasli (Breathy)",
    "Erinome":       "aniq (Clear)",
    "Fenrir":        "qattiq erkak (Excitable)",
    "Gacrux":        "etuk (Mature)",
    "Iapetus":       "aniq (Clear)",
    "Kore":          "jonli ayol (Firm)",
    "Laomedeia":     "quvnoq (Upbeat)",
    "Leda":          "yoshlik (Youthful)",
    "Orus":          "qat'iy erkak (Firm)",
    "Puck":          "quvnoq erkak (Upbeat)",
    "Pulcherrima":   "dadil (Forward)",
    "Rasalgethi":    "ma'lumotli (Informative)",
    "Sadachbia":     "jonli (Lively)",
    "Sadaltager":    "bilimdon (Knowledgeable)",
    "Schedar":       "tinch (Even)",
    "Sulafat":       "iliq (Warm)",
    "Umbriel":       "erkin (Easy-going)",
    "Vindemiatrix":  "muloyim (Gentle)",
    "Zephyr":        "yorqin ayol (Bright)",
    "Zubenelgenubi": "oddiy (Casual)",
}
VOICE_NAMES = list(VOICES.keys())


def _normalize_mode(text) -> str:
    """Map user wording to a canonical mode id, or '' if unknown."""
    mode = (str(text or "").strip().lower()
            .replace("-", " ").replace("_", " "))
    aliases = {
        "normal": "normal", "default": "normal", "standard": "normal",
        "regular": "normal", "profonal": "normal", "professional": "normal",
        "romantic": "girlfriend", "romantic girlfriend": "girlfriend",
        "girlfriend": "girlfriend", "girl": "girlfriend",
        "crazy friend": "crazy_friend", "crazy_friend": "crazy_friend",
        "crazy": "crazy_friend", "funny friend": "crazy_friend",
        "friend": "friend", "friendly": "friend",
        "butler": "butler", "batman's butler": "butler", "butler mode": "butler",
        "alfred": "butler", "servant": "butler",
        "casual": "casual", "chill": "casual",
    }
    mode = aliases.get(mode, mode)
    valid_modes = {"normal", "girlfriend", "crazy_friend", "butler", "friend", "casual"}
    return mode if mode in valid_modes else ""


def _normalize_voice(text) -> str:
    """Map user wording to a canonical Gemini voice name, or '' if unknown."""
    voice = (str(text or "").strip().lower()
             .replace("-", " ").replace("_", " "))
    aliases = {
        "default": "Aoede", "auto": "Aoede", "standart": "Aoede",
        "normal": "Aoede", "classic": "Aoede",
        "aoede": "Aoede", "charon": "Charon", "fenrir": "Fenrir",
        "kore": "Kore", "puck": "Puck", "zephyr": "Zephyr",
        "ayol": "Aoede", "erkak": "Charon",
    }
    voice = aliases.get(voice, voice.title())
    return voice if voice in VOICE_NAMES else ""


def _get_style_from_memory(memory: dict | None) -> tuple[str, str]:
    """Return mode and mood stored in preferences."""
    if not memory:
        return ("normal", "calm")

    prefs = memory.get("preferences", {}) if isinstance(memory, dict) else {}
    mode_entry = prefs.get("assistant_mode")
    mood_entry = prefs.get("assistant_mood")

    mode = mode_entry.get("value") if isinstance(mode_entry, dict) else mode_entry
    mood = mood_entry.get("value") if isinstance(mood_entry, dict) else mood_entry

    mode = _normalize_mode(mode) or "normal"
    mood = str(mood or "").strip().lower() or "calm"
    if mood not in {"calm", "playful", "romantic", "strict"}:
        mood = "calm"

    return (mode, mood)


def _get_voice_from_memory(memory: dict | None) -> str:
    """Return the saved Gemini voice name, defaulting to Aoede."""
    prefs = memory.get("preferences", {}) if isinstance(memory, dict) else {}
    entry = prefs.get("assistant_voice")
    voice = entry.get("value") if isinstance(entry, dict) else entry
    return _normalize_voice(voice) or "Aoede"
