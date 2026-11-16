import os
import re
import textwrap

_TS_RE = re.compile(
    r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})[,.](\d{3})"
)


def _ts(t, sep=","):
    ms = max(0, int(round(t * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def _parse_ts(h, m, s, ms):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _wrap(text, width):
    text = " ".join(text.split())
    if width <= 0 or len(text) <= width:
        return text
    lines = textwrap.wrap(text, width=max(width, len(text) // 2 + 1))
    return "\n".join(lines[:3])


def parse(path):
    """Parse an existing .srt or .vtt file into [{start, end, text}]."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read().replace("\r\n", "\n")
    blocks = re.split(r"\n{2,}", raw.strip())
    segs = []
    for blk in blocks:
        lines = [ln.strip() for ln in blk.split("\n") if ln.strip()]
        for idx, ln in enumerate(lines):
            m = _TS_RE.search(ln)
            if m:
                start = _parse_ts(*m.groups()[:4])
                end = _parse_ts(*m.groups()[4:])
                txt = " ".join(lines[idx + 1:])
                txt = re.sub(r"<[^>]+>", "", txt).strip()
                if txt:
                    segs.append({"start": start, "end": end, "text": txt})
                break
    return segs


def write(path, segments, fmt="srt", max_chars=42):
    """segments: list of dicts {start, end, text}"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig" if fmt == "srt" else "utf-8") as f:
        if fmt == "vtt":
            f.write("WEBVTT\n\n")
        for i, s in enumerate(segments, 1):
            sep = "." if fmt == "vtt" else ","
            if fmt == "srt":
                f.write(f"{i}\n")
            f.write(f"{_ts(s['start'], sep)} --> {_ts(s['end'], sep)}\n{_wrap(s['text'], max_chars)}\n\n")
    os.replace(tmp, path)


def write_dual(path, primary, secondary, fmt="srt", max_chars=42):
    """Write bilingual subtitles: translated line on top, original below."""
    merged = [
        {"start": a["start"], "end": a["end"], "text": f"{_wrap(a['text'], max_chars)}\n{_wrap(b['text'], max_chars)}"}
        for a, b in zip(secondary, primary)
    ]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig" if fmt == "srt" else "utf-8") as f:
        if fmt == "vtt":
            f.write("WEBVTT\n\n")
        for i, s in enumerate(merged, 1):
            sep = "." if fmt == "vtt" else ","
            if fmt == "srt":
                f.write(f"{i}\n")
            f.write(f"{_ts(s['start'], sep)} --> {_ts(s['end'], sep)}\n{s['text']}\n\n")
    os.replace(tmp, path)
