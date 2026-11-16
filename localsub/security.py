"""Security helpers: Windows DPAPI key encryption, HTTPS enforcement, log redaction."""
import base64
import ctypes
import re
import sys
from urllib.parse import urlparse

_DPAPI_PREFIX = "dpapi:"
_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[^\s\"']+", re.I),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"\b(gsk_[A-Za-z0-9_\-]{12,})"),
    re.compile(r"\b(AIza[A-Za-z0-9_\-]{16,})"),
    re.compile(r"\b(sk-or-v1-[A-Za-z0-9_\-]{12,})"),
]


if sys.platform == "win32":
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32


def protect_secret(text: str) -> str:
    text = (text or "").strip()
    if not text or text.startswith(_DPAPI_PREFIX) or sys.platform != "win32":
        return text
    raw = text.encode("utf-8")
    in_b = _DATA_BLOB(len(raw), ctypes.create_string_buffer(raw, len(raw)))
    out_b = _DATA_BLOB()
    if not _crypt32.CryptProtectData(ctypes.byref(in_b), "LocalSub", None, None, None, 0, ctypes.byref(out_b)):
        return text
    try:
        blob = ctypes.string_at(out_b.pbData, out_b.cbData)
        return _DPAPI_PREFIX + base64.b64encode(blob).decode("ascii")
    finally:
        _kernel32.LocalFree(out_b.pbData)


def unprotect_secret(value: str) -> str:
    value = (value or "").strip()
    if not value.startswith(_DPAPI_PREFIX) or sys.platform != "win32":
        return value
    try:
        raw = base64.b64decode(value[len(_DPAPI_PREFIX):])
        in_b = _DATA_BLOB(len(raw), ctypes.create_string_buffer(raw, len(raw)))
        out_b = _DATA_BLOB()
        if not _crypt32.CryptUnprotectData(ctypes.byref(in_b), None, None, None, None, 0, ctypes.byref(out_b)):
            return ""
        try:
            return ctypes.string_at(out_b.pbData, out_b.cbData).decode("utf-8")
        finally:
            _kernel32.LocalFree(out_b.pbData)
    except Exception:
        return ""


def validate_url(url: str):
    """Require HTTPS for remote servers; allow HTTP only for localhost/127.0.0.1."""
    p = urlparse((url or "").strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("Base URL must start with https:// (or http://localhost).")
    host = (p.hostname or "").lower()
    if p.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Insecure http:// URL is only allowed for localhost. Use https:// for remote APIs.")


def redact(text: str, secrets=()) -> str:
    out = str(text or "")
    for sec in secrets:
        s = (sec or "").strip()
        if len(s) >= 6:
            out = out.replace(s, s[:4] + "…***")
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(1)[:6] + "***" if m.lastindex else "***", out)
    return out
