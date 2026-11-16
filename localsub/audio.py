"""Extract audio from any video/audio file into small MP3 chunks for upload.

Uses PyAV (bundled FFmpeg) - no external ffmpeg install needed.
Mono 16 kHz 48 kbps MP3 = ~22 MB per hour, chunks stay well under the 25 MB API limit.
"""
import os
import time

import av

RATE = 16000


def duration_of(path):
    with av.open(path) as c:
        if c.duration:
            return c.duration / av.time_base
        s = next((s for s in c.streams if s.type == "audio"), None)
        if s is not None and s.duration and s.time_base:
            return float(s.duration * s.time_base)
    return 0.0


class _ChunkWriter:
    def __init__(self, path):
        self.path = path
        self.container = av.open(path, "w")
        self.stream = self.container.add_stream("libmp3lame", rate=RATE)
        self.stream.codec_context.layout = "mono"
        self.stream.bit_rate = 48000

    def write(self, frame):
        frame.pts = None
        for pkt in self.stream.encode(frame):
            self.container.mux(pkt)

    def close(self):
        for pkt in self.stream.encode(None):
            self.container.mux(pkt)
        self.container.close()


def extract_chunks(path, out_dir, chunk_seconds=600, progress=None, stop=None):
    """Returns list of (chunk_path, start_offset_seconds, chunk_duration)."""
    total = duration_of(path) or 1.0
    chunk_samples = int(chunk_seconds * RATE)
    chunks = []
    written_total = 0
    writer, chunk_start, in_chunk = None, 0, 0

    inp = av.open(path)
    try:
        astream = next((s for s in inp.streams if s.type == "audio"), None)
        if astream is None:
            raise ValueError("This file has no audio track.")
        astream.thread_type = "AUTO"
        resampler = av.AudioResampler(format="s16p", layout="mono", rate=RATE)

        def frames():
            for packet in inp.demux(astream):
                try:
                    for f in packet.decode():
                        yield f
                except av.error.InvalidDataError:
                    continue
            yield None  # flush resampler

        last_prog = 0.0
        for frame in frames():
            if stop is not None and stop.is_set():
                raise InterruptedError
            for rf in resampler.resample(frame):
                if writer is None:
                    p = os.path.join(out_dir, f"chunk_{len(chunks):03}.mp3")
                    writer = _ChunkWriter(p)
                    chunk_start, in_chunk = written_total, 0
                writer.write(rf)
                in_chunk += rf.samples
                written_total += rf.samples
                if in_chunk >= chunk_samples:
                    writer.close()
                    chunks.append((writer.path, chunk_start / RATE, in_chunk / RATE))
                    writer = None
            if progress and frame is not None and frame.time is not None:
                now = time.monotonic()
                if now - last_prog >= 0.2:
                    last_prog = now
                    progress(min(frame.time / total, 1.0))
        if writer is not None:
            writer.close()
            if in_chunk > RATE // 2:  # ignore < 0.5 s tail
                chunks.append((writer.path, chunk_start / RATE, in_chunk / RATE))
    finally:
        inp.close()
    if not chunks:
        raise ValueError("No audio could be decoded from this file.")
    return chunks
