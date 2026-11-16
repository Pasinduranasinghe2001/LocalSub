"""Persistent settings stored in %APPDATA%\\LocalSub\\settings.json"""
import copy
import json
import os

from . import APP_NAME, security

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")

# All providers speak the OpenAI-compatible REST API.
#   stt = supports /audio/transcriptions (speech-to-text with timestamps)
PROVIDERS = {
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "stt_model": "whisper-1",
        "llm_model": "gpt-4o-mini",
        "stt": True,
        "key_url": "https://platform.openai.com/api-keys",
    },
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "stt_model": "whisper-large-v3",
        "llm_model": "qwen/qwen3.8-27b",
        "stt": True,
        "key_url": "https://console.groq.com/keys",
    },
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "stt_model": "",
        "llm_model": "gemini-2.5-flash",
        "stt": False,
        "key_url": "https://aistudio.google.com/apikey",
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "stt_model": "",
        "llm_model": "openai/gpt-4o-mini",
        "stt": False,
        "key_url": "https://openrouter.ai/keys",
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "stt_model": "",
        "llm_model": "deepseek-chat",
        "stt": False,
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    "Custom URL": {
        "base_url": "http://localhost:8000/v1",
        "stt_model": "whisper-1",
        "llm_model": "",
        "stt": True,
        "key_url": "",
    },
}

STT_PROVIDERS = [n for n, p in PROVIDERS.items() if p["stt"]]
LLM_PROVIDERS = list(PROVIDERS)
BACKUP_PROVIDERS = ["None"] + LLM_PROVIDERS

DEFAULTS = {
    "stt_provider": "OpenAI",
    "translate_provider": "OpenAI",
    "backup_translate_provider": "None",
    "providers": {
        name: {
            "api_key": "",
            "base_url": p["base_url"],
            "stt_model": p["stt_model"],
            "llm_model": p["llm_model"],
        }
        for name, p in PROVIDERS.items()
    },
    "output_dir": "",
    "subtitle_format": "srt",
    "chunk_minutes": 10,
    "max_line_chars": 42,
    "parallel_workers": 4,
    "dual_subtitles": False,
    "use_cache": True,
    "translation_style": "Conversational (Movie)",
    "default_targets": ["Original", "English", "Sinhala"],
    "appearance": "Dark",
}

RETIRED_MODELS = {
    ("Groq", "llama-3.3-70b-versatile"): "qwen/qwen3.8-27b",
    ("Groq", "llama-3.1-70b-versatile"): "qwen/qwen3.8-27b",
    ("Groq", "mixtral-8x7b-32768"): "qwen/qwen3.8-27b",
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return copy.deepcopy(DEFAULTS)

    out = _merge(DEFAULTS, raw)
    changed = False
    for name, cfg in out.get("providers", {}).items():
        k = (cfg.get("api_key") or "").strip()
        if k and not k.startswith("dpapi:"):
            changed = True
        cfg["api_key"] = security.unprotect_secret(k)
        repl = RETIRED_MODELS.get((name, cfg.get("llm_model")))
        if repl:
            cfg["llm_model"] = repl
            changed = True
    if changed:
        try:
            save(out)
        except Exception:
            pass
    return out


def save(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    disk = copy.deepcopy(data)
    for cfg in disk.get("providers", {}).values():
        cfg["api_key"] = security.protect_secret(cfg.get("api_key", ""))
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(disk, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)


def provider_cfg(data, name):
    return data["providers"].get(name) or copy.deepcopy(DEFAULTS["providers"][name])
