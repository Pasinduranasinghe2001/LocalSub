"""Local checkpoint cache & session queue persistence for instant resume from breakpoints."""
import hashlib
import json
import os
import shutil

CACHE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~"),
    "LocalSub", "cache",
)
SESSION_PATH = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "LocalSub", "session.json",
)


def file_key(path, stt_provider, stt_model, source_lang, chunk_minutes):
    st = os.stat(path)
    sig = (
        f"{os.path.abspath(path).lower()}|{st.st_size}|{int(st.st_mtime)}"
        f"|{stt_provider}|{stt_model}|{source_lang or 'auto'}|{chunk_minutes}"
    )
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:24]


def trans_key(lines, target, style, batch_size):
    h = hashlib.sha256()
    h.update(f"{target}|{style}|{batch_size}|{len(lines)}|".encode("utf-8"))
    for ln in lines:
        h.update(ln.encode("utf-8", errors="ignore"))
        h.update(b"\n")
    return "tr_" + h.hexdigest()[:24]


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


def load_trans_batch(tkey, batch_idx):
    p = os.path.join(_job_dir(tkey), f"batch_{batch_idx:04}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_trans_batch(tkey, batch_idx, texts):
    d = _job_dir(tkey)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"batch_{batch_idx:04}.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(texts, f, ensure_ascii=False)
    os.replace(tmp, p)


def save_session(files, source_lang, targets, dual_subtitles):
    try:
        os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
        tmp = SESSION_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "files": list(files),
                "source_lang": source_lang,
                "targets": list(targets),
                "dual_subtitles": bool(dual_subtitles),
            }, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SESSION_PATH)
    except Exception:
        pass


def load_session():
    try:
        with open(SESSION_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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
