"""Video/SRT -> parallel audio transcription -> parallel translation -> subtitle files."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import shutil
import tempfile
import threading

from . import api, audio, cache, languages, subtitles
from .settings import provider_cfg

BATCH = 60
SUB_EXTS = {".srt", ".vtt"}


def _fmt_mmss(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"


def _transcribe_one(idx, cpath, offset, dur, stt, lang_code, prompt, ckey, use_cache, stop):
    if stop.is_set():
        raise InterruptedError
    if use_cache and ckey:
        cached = cache.load_chunk(ckey, idx)
        if cached is not None:
            return idx, cached["language"], cached["segments"], True

    res = api.transcribe(stt, cpath, language=lang_code, prompt=prompt, stop=stop)
    segs = res["segments"]
    raw_segs = []
    if not segs and res["text"].strip():
        segs = [{"start": 0.0, "end": dur, "text": res["text"].strip()}]
    for s in segs:
        raw_segs.append({"start": s["start"] + offset, "end": min(s["end"], dur) + offset, "text": s["text"]})
    data = {"language": res["language"], "segments": raw_segs}
    if use_cache and ckey:
        cache.save_chunk(ckey, idx, data)
    return idx, res["language"], raw_segs, False


def _pick_language(chunk_langs, segments, source_lang):
    if source_lang:
        return source_lang
    weights = Counter()
    for raw_lang, segs in chunk_langs:
        norm = languages.normalize(raw_lang)
        if languages.is_common(norm):
            weights[norm] += max(len(segs), 1)
    if weights:
        return weights.most_common(1)[0][0]
    first = languages.normalize(chunk_langs[0][0]) if chunk_langs else "Unknown"
    if first == "Latin" and languages.looks_english(segments):
        return "English"
    return first


def export_partial(state):
    """Write whatever transcription parts or translation batches finished before an interruption."""
    if not state:
        return []
    out_dir = state["out_dir"]
    base = state["base"]
    fmt = state["fmt"]
    max_chars = state["max_chars"]
    written = []

    segs = list(state.get("segments") or [])
    if not segs and state.get("stt_results"):
        for item in state["stt_results"]:
            if item is not None:
                segs.extend(item[1])
    if not segs:
        return []

    detected = state.get("detected") or "Unknown"
    targets = state.get("targets") or []
    translated = state.get("translated") or {}
    batch_size = state.get("batch_size") or BATCH

    # Save partial original if Original was requested or no translation started yet
    if "Original" in targets or not translated:
        p = os.path.join(out_dir, f"{base}.partial.{languages.code(detected)}.{fmt}")
        subtitles.write(p, segs, fmt, max_chars)
        written.append(p)

    for target, batches in translated.items():
        partial_segs = []
        for b_idx, chunk_out in enumerate(batches):
            if chunk_out is None:
                continue
            start = b_idx * batch_size
            for s, t in zip(segs[start:start + len(chunk_out)], chunk_out):
                partial_segs.append(dict(s, text=t))
        if partial_segs:
            p = os.path.join(out_dir, f"{base}.partial.{languages.code(target)}.{fmt}")
            subtitles.write(p, partial_segs, fmt, max_chars)
            written.append(p)
    return written


def process_file(path, settings, targets, source_lang, log, progress, stop, partial_state=None):
    """
    Supports both video/audio files and existing .srt/.vtt subtitle files.
    Returns list of written subtitle paths.
    """
    stt = provider_cfg(settings, settings["stt_provider"])
    llm = dict(provider_cfg(settings, settings["translate_provider"]))
    fmt = settings.get("subtitle_format", "srt")
    max_chars = int(settings.get("max_line_chars", 42))
    workers = max(1, int(settings.get("parallel_workers", 4)))
    use_cache = bool(settings.get("use_cache", True))
    dual = bool(settings.get("dual_subtitles", False))
    style = settings.get("translation_style", "Conversational (Movie)")
    out_dir = settings.get("output_dir") or os.path.dirname(path)
    os.makedirs(out_dir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(path))

    if partial_state is not None:
        partial_state.update({
            "out_dir": out_dir, "base": base, "fmt": fmt, "max_chars": max_chars,
            "targets": list(targets), "segments": [], "stt_results": None,
            "detected": None, "translated": {}, "batch_size": BATCH,
        })

    segments, detected = [], None

    # ---- Shortcut: existing .srt / .vtt input (translation only, zero STT cost)
    if ext.lower() in SUB_EXTS:
        log("Step 1/2: Reading subtitle file...")
        progress("Reading subtitle file", 0.2)
        segments = subtitles.parse(path)
        if not segments:
            log("No subtitle lines found in this file.")
            return []
        detected = source_lang or ("English" if languages.looks_english(segments) else "Unknown")
        log(f"Loaded {len(segments)} lines ({detected}). Skipping speech-to-text.")
        progress("Loaded subtitles", 1.0)
    else:
        chunk_minutes = int(settings.get("chunk_minutes", 10))
        ckey = cache.file_key(path, settings["stt_provider"], stt.get("stt_model", ""), source_lang, chunk_minutes)
        cached_full = cache.load_transcript(ckey) if use_cache else None

        if cached_full and cached_full.get("segments"):
            segments = cached_full["segments"]
            detected = source_lang or cached_full.get("detected") or "Unknown"
            log(f"Loaded cached transcript ({len(segments)} lines, {detected}).")
            progress("Transcript cached", 1.0)
        else:
            tmp = tempfile.mkdtemp(prefix="localsub_")
            try:
                log("Step 1/3: Extracting audio track...")
                progress("Extracting audio", 0)
                chunks = audio.extract_chunks(
                    path, tmp, chunk_seconds=chunk_minutes * 60,
                    progress=lambda p: progress("Extracting audio", p), stop=stop)
                total_parts = len(chunks)
                log(f"Audio ready: {total_parts} part(s), {_fmt_mmss(chunks[-1][1] + chunks[-1][2])} total")

                log(f"Step 2/3: Transcribing via {settings['stt_provider']} ({min(workers, total_parts)}x parallel)...")
                explicit_code = languages.code(source_lang) if source_lang else None
                results = [None] * total_parts
                if partial_state is not None:
                    partial_state["stt_results"] = results
                done_count = 0
                hint_code = explicit_code

                if use_cache:
                    cached_n = sum(1 for i in range(total_parts) if cache.load_chunk(ckey, i) is not None)
                    if cached_n:
                        log(f"💾 Checkpoint found: {cached_n}/{total_parts} audio part(s) already saved — resuming from break point...")

                # If auto-detecting and >1 part, run part 1 first to detect language cleanly
                start_idx = 0
                if not explicit_code and total_parts > 1:
                    cpath0, off0, dur0 = chunks[0]
                    log(f"  Part 1/{total_parts} ({_fmt_mmss(off0)} - {_fmt_mmss(off0 + dur0)})...")
                    progress(f"Transcribing part 1/{total_parts}", 0.05)
                    idx, rlang, rsegs, was_cached = _transcribe_one(
                        0, cpath0, off0, dur0, stt, None, "", ckey, use_cache, stop)
                    results[0] = (rlang, rsegs)
                    done_count = 1
                    norm0 = languages.normalize(rlang)
                    if languages.is_common(norm0) and len(rsegs) >= 10:
                        hint_code = languages.code(norm0)
                        log(f"  Part 1/{total_parts} done ({len(rsegs)} lines, {norm0}{' - cached' if was_cached else ''})")
                    else:
                        log(f"  Part 1/{total_parts} done ({len(rsegs)} lines, auto-detecting on remaining parts)")
                    progress(f"Transcribing 1/{total_parts}", 1 / total_parts)
                    start_idx = 1

                if start_idx < total_parts:
                    with ThreadPoolExecutor(max_workers=min(workers, total_parts - start_idx)) as pool:
                        futs = {}
                        for i in range(start_idx, total_parts):
                            cpath, offset, dur = chunks[i]
                            futs[pool.submit(
                                _transcribe_one, i, cpath, offset, dur, stt, hint_code, "", ckey, use_cache, stop
                            )] = i
                        try:
                            for fut in as_completed(futs):
                                if stop.is_set():
                                    for f in futs:
                                        f.cancel()
                                    raise InterruptedError
                                idx, rlang, rsegs, was_cached = fut.result()
                                results[idx] = (rlang, rsegs)
                                done_count += 1
                                log(f"  Part {idx + 1}/{total_parts} done ({len(rsegs)} lines{' - cached' if was_cached else ''})")
                                progress(f"Transcribing ({done_count}/{total_parts})", done_count / total_parts)
                        except BaseException:
                            for f in futs:
                                f.cancel()
                            raise

                for _, rsegs in results:
                    segments.extend(rsegs)
                if not segments:
                    log("No speech found in this file.")
                    return []
                detected = _pick_language(results, segments, source_lang)
                log(f"Detected language: {detected} ({len(segments)} lines total)")
                if use_cache:
                    cache.save_transcript(ckey, detected, segments)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    if partial_state is not None:
        partial_state["segments"] = segments
        partial_state["detected"] = detected

    # ---- Step 3: Output + Parallel Translation
    log("Creating subtitle files...")
    written = []
    translate_targets = []
    for target in targets:
        if target == "Original" or target == detected:
            name = detected if target == "Original" else target
            if target != "Original" and "Original" in targets:
                continue
            p = os.path.join(out_dir, f"{base}.{languages.code(name)}.{fmt}")
            subtitles.write(p, segments, fmt, max_chars)
            written.append(p)
            log(f"Saved: {p}")
        else:
            translate_targets.append(target)

    if translate_targets:
        lines = [s["text"] for s in segments]
        primary_name = settings["translate_provider"]
        backup_name = settings.get("backup_translate_provider", "None")
        backup_cfg = (
            dict(provider_cfg(settings, backup_name))
            if backup_name and backup_name != "None" and backup_name != primary_name
            else None
        )
        has_backup = bool(backup_cfg and (backup_cfg.get("api_key") or "").strip())

        is_primary_groq = "groq.com" in (llm.get("base_url") or "").lower()
        batch_size = 15 if is_primary_groq else BATCH
        tr_workers = 1 if is_primary_groq else workers

        jobs = []
        translated_by_target = {}
        tkeys = {}
        cached_batches = 0
        total_batches = 0
        for target in translate_targets:
            tkey = cache.trans_key(lines, target, style, batch_size) if use_cache else None
            tkeys[target] = tkey
            n_batches = (len(lines) + batch_size - 1) // batch_size
            total_batches += n_batches
            translated_by_target[target] = [None] * n_batches
            for b_idx, start in enumerate(range(0, len(lines), batch_size)):
                hit = cache.load_trans_batch(tkey, b_idx) if tkey else None
                if isinstance(hit, list) and len(hit) == len(lines[start:start + batch_size]):
                    translated_by_target[target][b_idx] = hit
                    cached_batches += 1
                else:
                    jobs.append((target, b_idx, start))

        if partial_state is not None:
            partial_state["translated"] = translated_by_target
            partial_state["batch_size"] = batch_size

        if cached_batches:
            log(f"💾 Translation checkpoint: {cached_batches}/{total_batches} batch(es) already saved — resuming remaining {len(jobs)}...")

        state_lock = threading.Lock()
        groq_pace_lock = threading.Lock()
        active_state = {"is_backup": False, "name": primary_name, "cfg": dict(llm)}

        def call_provider(prov_cfg, prov_name, batch_lines, target, ctx, retries):
            is_groq = "groq.com" in (prov_cfg.get("base_url") or "").lower()
            sub_size = 15 if is_groq else len(batch_lines)
            max_tok = 700 if is_groq else None

            def run_slice(sub_lines, sub_ctx):
                local_cfg = dict(prov_cfg)
                try:
                    return api.translate_lines(local_cfg, sub_lines, target, detected, sub_ctx,
                                               max_tokens=max_tok, retries=retries, style=style, stop=stop)
                except api.ModelNotFoundError:
                    with state_lock:
                        if prov_cfg.get("llm_model") == local_cfg.get("llm_model"):
                            _, avail = api.list_models(prov_cfg, stop=stop)
                            picked = api.pick_best_llm(avail)
                            if not picked:
                                raise
                            log(f"⚠ [{prov_name}] Model '{prov_cfg['llm_model']}' unavailable; switched to '{picked}'")
                            prov_cfg["llm_model"] = picked
                    local_cfg["llm_model"] = prov_cfg["llm_model"]
                    return api.translate_lines(local_cfg, sub_lines, target, detected, sub_ctx,
                                               max_tokens=max_tok, retries=retries, style=style, stop=stop)

            if len(batch_lines) <= sub_size:
                if is_groq:
                    with groq_pace_lock:
                        return run_slice(batch_lines, ctx)
                return run_slice(batch_lines, ctx)

            merged = []
            with groq_pace_lock:
                for off in range(0, len(batch_lines), sub_size):
                    if stop.is_set():
                        raise InterruptedError
                    sub = batch_lines[off:off + sub_size]
                    sub_ctx = " | ".join(batch_lines[max(0, off - 3):off]) or ctx
                    merged.extend(run_slice(sub, sub_ctx))
            return merged

        def run_batch(target, b_idx, start):
            if stop.is_set():
                raise InterruptedError
            ctx = " | ".join(lines[max(0, start - 3):start])
            batch_lines = lines[start:start + batch_size]

            with state_lock:
                use_backup = active_state["is_backup"]
                cur_cfg = active_state["cfg"]
                cur_name = active_state["name"]

            try:
                out = call_provider(cur_cfg, cur_name, batch_lines, target, ctx,
                                    retries=2 if (has_backup and not use_backup) else 6)
            except (api.RateLimitError, api.ApiError) as err:
                if not has_backup or use_backup:
                    raise
                with state_lock:
                    if not active_state["is_backup"]:
                        active_state["is_backup"] = True
                        active_state["name"] = backup_name
                        active_state["cfg"] = backup_cfg
                        log(f"⚠ {primary_name} hit limit/error ({err}); continuing remaining batches with backup {backup_name}!")
                    cur_cfg = active_state["cfg"]
                    cur_name = active_state["name"]
                out = call_provider(cur_cfg, cur_name, batch_lines, target, ctx, retries=6)
            if use_cache and tkeys.get(target):
                cache.save_trans_batch(tkeys[target], b_idx, out)
            return target, b_idx, out

        if jobs:
            backup_note = f" (backup: {backup_name})" if has_backup else ""
            log(f"Translating {len(lines)} lines via {primary_name}{backup_note} across {len(translate_targets)} language(s) "
                f"({len(jobs)} remaining batches, {min(tr_workers, len(jobs))}x)...")
            done_jobs = cached_batches
            with ThreadPoolExecutor(max_workers=min(tr_workers, len(jobs))) as pool:
                futs = [pool.submit(run_batch, t, bi, st) for t, bi, st in jobs]
                try:
                    for fut in as_completed(futs):
                        if stop.is_set():
                            for f in futs:
                                f.cancel()
                            raise InterruptedError
                        target, b_idx, out = fut.result()
                        translated_by_target[target][b_idx] = out
                        done_jobs += 1
                        progress(f"Translating ({done_jobs}/{total_batches} batches)", done_jobs / total_batches)
                except BaseException:
                    for f in futs:
                        f.cancel()
                    raise

        for target in translate_targets:
            merged_texts = []
            for chunk_out in translated_by_target[target]:
                merged_texts.extend(chunk_out)
            tsegs = [dict(s, text=t) for s, t in zip(segments, merged_texts)]
            p = os.path.join(out_dir, f"{base}.{languages.code(target)}.{fmt}")
            subtitles.write(p, tsegs, fmt, max_chars)
            written.append(p)
            log(f"Saved: {p}")

            if dual:
                dp = os.path.join(out_dir, f"{base}.{languages.code(detected)}+{languages.code(target)}.{fmt}")
                subtitles.write_dual(dp, segments, tsegs, fmt, max_chars)
                written.append(dp)
                log(f"Saved (dual): {dp}")

    progress("Done", 1)
    return written
