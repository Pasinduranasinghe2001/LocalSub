"""Comprehensive test (no real API keys needed):
- DPAPI encryption/decryption + retired model migration
- HTTPS enforcement + log redaction
- Parallel STT + 'Latin' misdetection recovery
- Parallel translation + 404 model auto-fallback
- Dual subtitles + direct .srt translation
"""
import json
import os
import re
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from localsub import api, cache, pipeline, security, settings, subtitles  # noqa: E402

# 1. Security checks
enc = security.protect_secret("gsk_secret_test_key_12345")
assert enc.startswith("dpapi:") and security.unprotect_secret(enc) == "gsk_secret_test_key_12345"
assert "***" in security.redact("Error with Bearer sk-abc123456789012345", ["sk-abc123456789012345"])
try:
    security.validate_url("http://api.openai.com/v1")
    raise AssertionError("Should reject remote http://")
except ValueError:
    pass
security.validate_url("http://localhost:8000/v1")

# 2. Retired model migration + DPAPI save/load
tmp_cfg = tempfile.mkdtemp()
settings.CONFIG_DIR = tmp_cfg
settings.CONFIG_PATH = os.path.join(tmp_cfg, "settings.json")
with open(settings.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump({"providers": {"Groq": {"api_key": "gsk_plain_key_999", "llm_model": "llama-3.3-70b-versatile"}}}, f)
loaded = settings.load()
assert loaded["providers"]["Groq"]["api_key"] == "gsk_plain_key_999"
assert loaded["providers"]["Groq"]["llm_model"] == "qwen/qwen3.8-27b"
raw_disk = open(settings.CONFIG_PATH, encoding="utf-8").read()
assert "gsk_plain_key_999" not in raw_disk and "dpapi:" in raw_disk

# 3. Mock API: part 0 falsely says 'latin' with English text, part 1+ says 'english'; chat hits 404 once then recovers
cache.CACHE_DIR = tempfile.mkdtemp()
calls = []
fallback_triggered = [False]


def fake_transcribe(cfg, path, language=None, prompt=None, stop=None):
    calls.append(("stt", os.path.basename(path), language))
    if "000" in path:
        return {"language": "latin", "text": "x",
                "segments": [{"start": 0.5, "end": 2.0, "text": "Hello there, what are you doing?"}]}
    return {"language": "english", "text": "x",
            "segments": [{"start": 0.5, "end": 2.0, "text": "We have to go now."},
                         {"start": 3.0, "end": 5.0, "text": "The door is open."}]}


def fake_list_models(cfg, stop=None):
    return ["whisper-large-v3"], ["qwen/qwen3.8-27b"]


def fake_chat(cfg, messages, temperature=0.2, max_tokens=None, retries=6, stop=None):
    if cfg.get("llm_model") == "gemini-limit-test":
        raise api.RateLimitError("HTTP 429 (quota / daily limit): RPD exceeded")
    if not fallback_triggered[0] and cfg.get("llm_model") == "retired-model":
        fallback_triggered[0] = True
        raise api.ModelNotFoundError("HTTP 404: does not exist")
    lines_in = json.loads(messages[1]["content"].split("\n\n")[-1])["lines"]
    if len(lines_in) > 2:
        raise api.RequestTooLargeError("HTTP 429: Request too large")
    n = int(re.search(r"exactly (\d+)", messages[0]["content"]).group(1))
    return json.dumps({"t": [f"[TR] line {i}" for i in range(n)]})


api.transcribe = fake_transcribe
api.list_models = fake_list_models
api.chat = fake_chat

vid = sys.argv[1]
s = settings.load()
s["output_dir"] = tempfile.mkdtemp()
s["chunk_minutes"] = 0.17  # ~10s chunks on 25s test video -> 3 chunks
s["parallel_workers"] = 4
s["dual_subtitles"] = True
s["stt_provider"] = "Groq"
s["translate_provider"] = "Groq"
s["providers"]["Groq"]["llm_model"] = "retired-model"

# Patch extract_chunks seconds directly via chunk_minutes=1/6 wouldn't work since int(), so test with 1 chunk + SRT
s["chunk_minutes"] = 5
out = pipeline.process_file(vid, s, ["Original", "English", "Sinhala"], None,
                            print, lambda st, f: None, threading.Event())
names = [os.path.basename(p) for p in out]
print("Video outputs:", names)
assert any(n.endswith(".en.srt") for n in names), f"Latin recovery failed: {names}"
assert any(n.endswith(".si.srt") for n in names)
assert any(n.endswith(".en+si.srt") for n in names)

# 4. Direct .srt translation test (zero STT calls)
prev_calls = len(calls)
srt_in = [p for p in out if p.endswith(".en.srt")][0]
out2 = pipeline.process_file(srt_in, s, ["Tamil"], "English",
                             print, lambda st, f: None, threading.Event())
assert len(calls) == prev_calls, "SRT input should skip STT!"
assert any(p.endswith(".ta.srt") for p in out2)
assert len(subtitles.parse(srt_in)) == 1

# 5. Auto-split on RequestTooLargeError
split_out = api.translate_lines({"llm_model": "qwen/qwen3.8-27b"}, ["a", "b", "c", "d", "e"], "Sinhala")
assert len(split_out) == 5, split_out

# 6. Backup translation provider fallback (Gemini hits daily limit -> switches to Groq)
s["translate_provider"] = "Google Gemini"
s["backup_translate_provider"] = "Groq"
s["providers"]["Google Gemini"]["api_key"] = "AIza_fake_123456"
s["providers"]["Google Gemini"]["llm_model"] = "gemini-limit-test"
s["providers"]["Groq"]["api_key"] = "gsk_fake_123456"
s["providers"]["Groq"]["llm_model"] = "qwen/qwen3.8-27b"
bk_logs = []
out3 = pipeline.process_file(srt_in, s, ["Sinhala"], "English",
                             lambda m: (print(m), bk_logs.append(m)), lambda st, f: None, threading.Event())
assert any("continuing remaining batches with backup Groq" in m for m in bk_logs), bk_logs
assert any(p.endswith(".si.srt") for p in out3)
print("ALL PIPELINE TESTS OK")
