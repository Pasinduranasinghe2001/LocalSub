# Display name -> ISO-639-1 code (Whisper uses these codes)
LANGUAGES = {
    "English": "en", "Sinhala": "si", "Tamil": "ta", "Hindi": "hi",
    "Malayalam": "ml", "Telugu": "te", "Kannada": "kn", "Bengali": "bn",
    "Urdu": "ur", "Marathi": "mr", "Gujarati": "gu", "Punjabi": "pa", "Nepali": "ne",
    "Japanese": "ja", "Korean": "ko", "Chinese": "zh", "Thai": "th",
    "Vietnamese": "vi", "Indonesian": "id", "Malay": "ms", "Filipino": "tl",
    "Arabic": "ar", "Persian": "fa", "Turkish": "tr", "Hebrew": "he",
    "French": "fr", "Spanish": "es", "Portuguese": "pt", "German": "de",
    "Italian": "it", "Dutch": "nl", "Russian": "ru", "Ukrainian": "uk",
    "Polish": "pl", "Greek": "el", "Swedish": "sv",
}

# Shown as checkboxes on the main screen (main languages first)
TARGETS = ["Original", "English", "Sinhala", "Tamil", "Hindi", "Malayalam", "Telugu",
           "Japanese", "Korean", "Chinese", "Arabic", "French", "Spanish", "German",
           "Russian", "Thai", "Indonesian", "Bengali", "Urdu", "Portuguese"]

_BY_LOWER = {k.lower(): k for k in LANGUAGES}
_BY_CODE = {v: k for k, v in LANGUAGES.items()}
_ALIASES = {"sinhalese": "Sinhala", "mandarin": "Chinese", "tagalog": "Filipino"}
_EN_WORDS = {"the", "and", "you", "that", "this", "what", "are", "was", "have", "not", "with", "for"}


def normalize(detected: str) -> str:
    """Whisper API returns 'english' / 'en' etc. -> 'English'."""
    if not detected:
        return "Unknown"
    d = detected.strip().lower()
    return _BY_LOWER.get(d) or _BY_CODE.get(d) or _ALIASES.get(d) or detected.strip().title()


def is_common(name: str) -> bool:
    return name in LANGUAGES


def looks_english(segments) -> bool:
    sample = " ".join(s.get("text", "") for s in segments[:20]).lower().split()
    hits = sum(1 for w in sample if w.strip(".,!?\"'") in _EN_WORDS)
    return hits >= 3


def code(name: str) -> str:
    return LANGUAGES.get(name, name[:3].lower())
