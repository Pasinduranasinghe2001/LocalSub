"""Self-test without API keys: makes a test video, extracts audio chunks, writes subtitles."""
import os
import sys
import tempfile

import av
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from localsub import audio, subtitles, languages  # noqa: E402

tmp = tempfile.mkdtemp()
vid = os.path.join(tmp, "test.mp4")

# 25 s video with 44.1kHz stereo AAC tone
c = av.open(vid, "w")
vs = c.add_stream("libx264" if "libx264" in av.codecs_available else "mpeg4", rate=10)
vs.width, vs.height, vs.pix_fmt = 64, 64, "yuv420p"
a_s = c.add_stream("aac", rate=44100)
a_s.codec_context.layout = "stereo"
for i in range(250):
    f = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), np.uint8), format="rgb24")
    for p in vs.encode(f):
        c.mux(p)
t = 0
sr, n = 44100, 1024
total = 25 * sr
while t < total:
    x = np.sin(2 * np.pi * 440 * (np.arange(t, t + n) / sr)).astype(np.float32) * 0.3
    fr = av.AudioFrame.from_ndarray(np.stack([x, x]), format="fltp", layout="stereo")
    fr.sample_rate = sr
    fr.pts = t
    for p in a_s.encode(fr):
        c.mux(p)
    t += n
for s in (vs, a_s):
    for p in s.encode(None):
        c.mux(p)
c.close()

print("duration", round(audio.duration_of(vid), 1))
chunks = audio.extract_chunks(vid, tmp, chunk_seconds=10)
for p, off, d in chunks:
    print(os.path.basename(p), off, round(d, 2), os.path.getsize(p), "bytes", round(audio.duration_of(p), 2))
assert len(chunks) == 3 and abs(chunks[1][1] - 10) < 0.2

srt = os.path.join(tmp, "x.srt")
subtitles.write(srt, [{"start": 1.5, "end": 3.25, "text": "ආයුබෝවන් ලෝකය - this is a long sinhala line to wrap nicely"}])
print(open(srt, encoding="utf-8-sig").read())
print(languages.normalize("sinhala"), languages.normalize("english"), languages.normalize("ta"))
print("SELFTEST OK")
