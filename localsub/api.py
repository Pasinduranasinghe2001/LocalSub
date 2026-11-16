"""OpenAI-compatible API client (OpenAI, Groq, Gemini, OpenRouter, DeepSeek, custom)."""
import json
import os
import random
import re
import socket
import threading
import time

import requests
import urllib3.util.connection as _urllib3_conn

from . import security

_IPV4_LOCK = threading.Lock()
_FORCE_IPV4 = False
_ORIG_GETADDRINFO = socket.getaddrinfo
_DNS_LOCK = threading.Lock()
_DNS_CACHE = {}  # host -> (expires_monotonic, [ip, ...])
_SKIP_LLM = ("whisper", "transcribe", "tts", "orpheus", "guard", "embed", "moderation", "dall-e", "sora", "audio")
_PREF_LLM = ("qwen/qwen3.8", "qwen", "gpt-4o-mini", "gemini-2.5-flash", "gemini", "deepseek-chat", "gpt-oss", "llama")


def _doh_resolve(host):
    now = time.monotonic()
    with _DNS_LOCK:
        hit = _DNS_CACHE.get(host)
        if hit and hit[0] > now:
            return hit[1]
    try:
        r = requests.get(f"https://8.8.8.8/resolve?name={host}&type=A", timeout=5, verify=True)
        ips = [a["data"] for a in r.json().get("Answer", []) if a.get("type") == 1 and a.get("data")]
        if ips:
            with _DNS_LOCK:
                _DNS_CACHE[host] = (now + 300.0, ips)
            return ips
    except Exception:
        pass
    return []


def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _ORIG_GETADDRINFO(host, port, family, type, proto, flags)
    except socket.gaierror:
        if isinstance(host, str) and host not in ("8.8.8.8", "localhost") and not host.replace(".", "").isdigit():
            ips = _doh_resolve(host)
            if ips:
                p = int(port or 0)
                return [(socket.AF_INET, type or socket.SOCK_STREAM, proto or socket.IPPROTO_TCP, "", (ip, p)) for ip in ips]
        raise


socket.getaddrinfo = _resilient_getaddrinfo


class ApiError(Exception):
    pass


class ModelNotFoundError(ApiError):
    pass


class RequestTooLargeError(ApiError):
    pass


class RateLimitError(ApiError):
    pass


def _enable_ipv4_fallback():
    global _FORCE_IPV4
    with _IPV4_LOCK:
        if not _FORCE_IPV4:
            _FORCE_IPV4 = True
            _urllib3_conn.allowed_gai_family = lambda: socket.AF_INET


def _url(cfg, path):
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise ApiError("Base URL is empty - check Settings.")
    try:
        security.validate_url(base)
    except ValueError as e:
        raise ApiError(str(e))
    return base + path


def _headers(cfg):
    key = (cfg.get("api_key") or "").strip()
    if not key:
        raise ApiError("API key is missing - open Settings and paste your key.")
    return {
        "Authorization": f"Bearer {key}",
        "User-Agent": "LocalSub/1.1",
        "Connection": "close",
    }


def _error_text(r):
    try:
        j = r.json()
        e = j.get("error") if isinstance(j, dict) else None
        if isinstance(e, dict):
            return e.get("message") or json.dumps(e)
        if isinstance(j, list) and j and isinstance(j[0], dict) and "error" in j[0]:
            return j[0]["error"].get("message", str(j[0]))
        return str(e or j)[:400]
    except Exception:
        return r.text[:400]


def _sleep(seconds, stop):
    if stop is None:
        time.sleep(seconds)
    elif stop.wait(seconds):
        raise InterruptedError


def _retry_wait(r, attempt):
    try:
        wait = float(r.headers.get("retry-after", 0))
    except ValueError:
        wait = 0
    if not wait:
        m = re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|s|m)?", r.text, re.I)
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or "s").lower()
            wait = val / 1000.0 if unit == "ms" else (val * 60.0 if unit == "m" else val)
    return min(65.0, max(wait + 0.5, 2 ** (attempt + 1) + random.uniform(0, 1.0)))


def _request(method, url, cfg, retries=6, timeout=600, stop=None, **kw):
    headers = _headers(cfg)
    secret = cfg.get("api_key") or ""
    net_fails = 0
    for attempt in range(retries):
        if stop is not None and stop.is_set():
            raise InterruptedError
        try:
            r = requests.request(method, url, headers=headers, timeout=timeout, verify=True, **kw)
        except requests.RequestException as e:
            net_fails += 1
            if net_fails >= 2:
                _enable_ipv4_fallback()
            if attempt == retries - 1:
                raise ApiError(security.redact(f"Network error: {e}", [secret]))
            _sleep(min(20.0, (1.5 * (2 ** attempt)) + random.uniform(0, 0.8)), stop)
            continue

        if r.status_code >= 400:
            msg = security.redact(_error_text(r), [secret])
            low = msg.lower()
            if r.status_code in (413, 429) and ("request too large" in low or "exceed the enforced limit" in low):
                raise RequestTooLargeError(f"HTTP {r.status_code}: {msg}")
            if r.status_code in (402, 429) and (
                "insufficient_quota" in low or "per day" in low or "daily" in low
                or ("billing" in low and "try again" not in low)
            ):
                raise RateLimitError(f"HTTP {r.status_code} (quota / daily limit): {msg}")
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                _sleep(_retry_wait(r, attempt), stop)
                continue
            hint = ""
            if r.status_code == 401:
                hint = " (invalid API key)"
            elif r.status_code == 429:
                hint = " (rate limit / no credit left)"
            err = f"HTTP {r.status_code}{hint}: {msg}"
            if r.status_code == 429:
                raise RateLimitError(err)
            if r.status_code == 404 or "does not exist" in low:
                raise ModelNotFoundError(err)
            raise ApiError(err)
        return r
    raise ApiError("Request failed")


def list_models(cfg, stop=None):
    """Returns (stt_models, llm_models) sorted from the provider's /models endpoint."""
    r = _request("GET", _url(cfg, "/models"), cfg, retries=3, timeout=30, stop=stop)
    ids = sorted({str(m.get("id", "")).strip() for m in r.json().get("data", []) if m.get("id")})
    stt = [m for m in ids if "whisper" in m.lower() or "transcribe" in m.lower()]
    llm = [m for m in ids if not any(bad in m.lower() for bad in _SKIP_LLM)]
    return stt, llm


def pick_best_llm(models):
    for pref in _PREF_LLM:
        for m in models:
            if pref in m.lower():
                return m
    return models[0] if models else ""


def test_connection(cfg):
    base = (cfg.get("base_url") or "").lower()
    if "openrouter.ai" in base:
        _request("GET", _url(cfg, "/auth/key"), cfg, retries=3, timeout=30)
        return "Connected ✔ (OpenRouter key verified)"
    stt, llm = list_models(cfg)
    total = len(set(stt) | set(llm))
    return f"Connected ✔ ({total} models available)" if total else "Connected ✔"


# ---------------------------------------------------------------- speech-to-text
def transcribe(cfg, file_path, language=None, prompt=None, stop=None):
    """Returns dict: {language, segments:[{start,end,text}], text}"""
    with open(file_path, "rb") as f:
        audio = f.read()
    data = {
        "model": cfg.get("stt_model") or "whisper-1",
        "response_format": "verbose_json",
        "timestamp_granularities[]": "segment",
        "temperature": "0",
    }
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt[-400:]
    r = _request("POST", _url(cfg, "/audio/transcriptions"), cfg, stop=stop,
                 data=data, files={"file": (os.path.basename(file_path), audio, "audio/mpeg")})
    try:
        j = r.json()
    except ValueError:
        raise ApiError("Unexpected response from transcription API.")
    segs = [
        {"start": float(s["start"]), "end": float(s["end"]), "text": s.get("text", "").strip()}
        for s in (j.get("segments") or []) if s.get("text", "").strip()
    ]
    return {"language": j.get("language", ""), "segments": segs, "text": j.get("text", "")}


# ---------------------------------------------------------------- translation
def chat(cfg, messages, temperature=0.2, max_tokens=None, retries=6, stop=None):
    body = {"model": cfg.get("llm_model"), "messages": messages, "temperature": temperature}
    if max_tokens:
        body["max_tokens"] = int(max_tokens)
    r = _request("POST", _url(cfg, "/chat/completions"), cfg, retries=retries, stop=stop, json=body)
    try:
        return r.json()["choices"][0]["message"]["content"] or ""
    except Exception:
        raise ApiError("Unexpected response from translation API: " + r.text[:300])


def _parse_list(text, n):
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    arr = obj.get("t") if isinstance(obj, dict) else obj
    if isinstance(arr, list) and len(arr) == n:
        return [str(x) for x in arr]
    return None


def translate_lines(cfg, lines, target, source=None, context="", max_tokens=None, retries=6,
                    style="Conversational (Movie)", stop=None):
    n = len(lines)
    src = f" from {source}" if source and source != "Unknown" else ""
    conversational = not style or "conversational" in style.lower()
    if conversational:
        tone = (
            "Use natural, everyday spoken movie-subtitle language (conversational, simple, "
            "easy to read — NOT formal textbook, archaic, or stiff dictionary words). "
            "Pick the most natural word that fits the exact scene and emotion."
        )
        if target.strip().lower() == "sinhala":
            tone += (
                " For Sinhala: write natural, everyday spoken Sri Lankan movie subtitles (සරල කටවහර) "
                "instead of stiff textbook/news language, while keeping exact meaning and accurate "
                "pronouns (e.g. ඔහු, ඇය, ඔවුන්, ඔයා, අපි)."
            )
    else:
        tone = "Use clear, accurate, standard written phrasing appropriate for documentaries or lectures."
    system = (
        f"You are a professional film subtitle translator. Translate each subtitle line{src} "
        f"into {target}, written in the native {target} script. {tone} Keep it concise and "
        f"easy to read as subtitles. Keep character/place names accurate. Never merge, split, skip or "
        f"reorder lines. Reply ONLY with JSON: {{\"t\": [ ...exactly {n} translated strings... ]}}"
    )
    user = json.dumps({"lines": lines}, ensure_ascii=False)
    if context:
        user = f"Previous lines for context (do not translate): {context}\n\n{user}"
    try:
        for _ in range(2):
            out = _parse_list(chat(cfg, [{"role": "system", "content": system},
                                         {"role": "user", "content": user}],
                                   max_tokens=max_tokens, retries=retries, stop=stop), n)
            if out:
                return out
    except RequestTooLargeError:
        if n > 1:
            mid = n // 2
            return (
                translate_lines(cfg, lines[:mid], target, source, context,
                                max_tokens=max_tokens, retries=retries, style=style, stop=stop)
                + translate_lines(cfg, lines[mid:], target, source, " | ".join(lines[:mid][-3:]),
                                  max_tokens=max_tokens, retries=retries, style=style, stop=stop)
            )
        raise
    # Fallback: line by line (slower but always aligned)
    res = []
    for line in lines:
        if stop is not None and stop.is_set():
            raise InterruptedError
        txt = chat(cfg, [
            {"role": "system", "content": f"Translate the subtitle line{src} into {target}. {tone} "
                                          f"Reply with the translation only."},
            {"role": "user", "content": line}], max_tokens=max_tokens, retries=retries, stop=stop)
        res.append(txt.strip().strip('"'))
    return res
