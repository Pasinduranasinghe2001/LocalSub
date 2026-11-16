"""Local transcript cache so interrupted jobs or extra languages never re-upload audio."""
import hashlib
import json
import os
import shutil

CACHE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~"),
    "LocalSub", "cache",
)


def file_key(path, stt_provider, stt_model, source_lang, chunk_minutes):
    st = os.stat(path)
    sig = f"{os.path.abspath(path).lower()}|{st.st_size}|{int(st.st_mtime)}|{stt_provider}|{stt_model}|{source_lang or 'auto'}|{chunk_minutes}"
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:24]


def _job_dir(key):
    return os.path.join(CACHE_DIR, key)


def load_chunk(key, idx):
    p = os.path.join(_job_dir(key), f"chunk_{idx:03}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_chunk(key, idx, data):
    d = _job_dir(key)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"chunk_{idx:03}.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, p)


def load_transcript(key):
    p = os.path.join(_job_dir(key), "transcript.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_transcript(key, detected, segments):
    d = _job_dir(key)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "transcript.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"detected": detected, "segments": segments}, f, ensure_ascii=False)
    os.replace(tmp, p)


def clear_all():
    if not os.path.exists(CACHE_DIR):
        return 0, 0
    files, total = 0, 0
    for root, _, names in os.walk(CACHE_DIR):
        for n in names:
            files += 1
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
    shutil.rmtree(CACHE_DIR, ignore_errors=True)
    return files, total
