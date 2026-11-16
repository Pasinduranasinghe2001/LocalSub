"""LocalSub desktop UI (CustomTkinter) - rich colored theme, parallel pipeline, DPAPI security."""
import os
import queue
import sys
import threading
import time
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import APP_NAME, APP_VERSION, api, cache, languages, pipeline, security
from . import settings as cfgmod

MEDIA_TYPES = [
    ("Videos, Audio & Subtitles",
     "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v *.ts *.3gp "
     "*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.opus *.srt *.vtt"),
    ("Video / Audio", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v *.ts *.3gp "
                      "*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.opus"),
    ("Subtitles (SRT / VTT)", "*.srt *.vtt"),
    ("All files", "*.*"),
]
UNICODE_FONT = "Nirmala UI"

# ---- Color Palette (light, dark) ----
C_BG = ("#f1f5f9", "#0f172a")
C_SIDE = ("#e2e8f0", "#0b1120")
C_CARD = ("#ffffff", "#1e293b")
C_BORDER = ("#cbd5e1", "#334155")
C_ROW = ("#f8fafc", "#0f172a")
C_MUTED = ("#475569", "#94a3b8")

B_BLUE = ("#2563eb", "#3b82f6")
B_BLUE_H = ("#1d4ed8", "#2563eb")
B_INDIGO = ("#4f46e5", "#6366f1")
B_INDIGO_H = ("#4338ca", "#4f46e5")
B_GREEN = ("#059669", "#10b981")
B_GREEN_H = ("#047857", "#059669")
B_CYAN = ("#0284c7", "#0ea5e9")
B_CYAN_H = ("#0369a1", "#0284c7")
B_VIOLET = ("#7c3aed", "#8b5cf6")
B_VIOLET_H = ("#6d28d9", "#7c3aed")
B_RED = ("#dc2626", "#ef4444")
B_RED_H = ("#b91c1c", "#dc2626")
B_SLATE = ("#64748b", "#334155")
B_SLATE_H = ("#475569", "#475569")


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


# ======================================================================= Pages
class GeneratePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.files = []
        self.last_written = []
        self.last_partial = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="Generate Subtitles", font=ctk.CTkFont(size=24, weight="bold")
                     ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text="Drop any video or .srt file → auto-detect language → parallel fast subtitle output",
                     text_color=C_MUTED).grid(row=1, column=0, sticky="w")

        # ---------- 1. Videos / Subtitles
        fcard = ctk.CTkFrame(self, fg_color=C_CARD, border_width=1, border_color=C_BORDER, corner_radius=12)
        fcard.grid(row=1, column=0, sticky="ew")
        fcard.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(fcard, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        ctk.CTkLabel(top, text="1. Videos or Subtitle Files", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="Clear", width=72, fg_color=B_SLATE, hover_color=B_SLATE_H,
                      command=self.clear_files).pack(side="right")
        ctk.CTkButton(top, text="+ Add videos / SRT", width=155, fg_color=B_INDIGO, hover_color=B_INDIGO_H,
                      font=ctk.CTkFont(weight="bold"), command=self.add_files).pack(side="right", padx=8)
        self.flist = ctk.CTkScrollableFrame(fcard, height=112, fg_color=C_ROW, corner_radius=8)
        self.flist.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        self.flist.grid_columnconfigure(0, weight=1)
        self.empty_lbl = ctk.CTkLabel(
            self.flist,
            text="No files added yet. Click “+ Add videos / SRT” to choose movies, audio, or existing .srt files.",
            text_color=C_MUTED,
        )
        self.empty_lbl.grid(row=0, column=0, pady=34)

        # ---------- 2. Languages
        lcard = ctk.CTkFrame(self, fg_color=C_CARD, border_width=1, border_color=C_BORDER, corner_radius=12)
        lcard.grid(row=2, column=0, sticky="ew", pady=10)
        lcard.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(lcard, text="2. Languages", font=ctk.CTkFont(size=15, weight="bold")
                     ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 4))

        lang_top = ctk.CTkFrame(lcard, fg_color="transparent")
        lang_top.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(lang_top, text="Video / source language:").pack(side="left")
        self.src = ctk.CTkOptionMenu(
            lang_top, values=["Auto detect"] + list(languages.LANGUAGES), width=175,
            fg_color=B_BLUE, button_color=B_BLUE_H, button_hover_color=B_BLUE_H,
        )
        self.src.pack(side="left", padx=(10, 22))
        self.dual_var = ctk.BooleanVar(value=bool(app.settings.get("dual_subtitles", False)))
        ctk.CTkCheckBox(
            lang_top, text="Dual subtitles (Translated + Original together)",
            variable=self.dual_var, fg_color=B_VIOLET, hover_color=B_VIOLET_H,
        ).pack(side="left")

        ctk.CTkLabel(lcard, text="Subtitles in:").grid(row=2, column=0, sticky="nw", padx=14, pady=6)
        grid = ctk.CTkFrame(lcard, fg_color="transparent")
        grid.grid(row=2, column=1, sticky="w", pady=(6, 12))
        defaults = set(app.settings.get("default_targets", []))
        self.tvars = {}
        for i, name in enumerate(languages.TARGETS):
            v = ctk.BooleanVar(value=name in defaults)
            label = "Original (as spoken)" if name == "Original" else name
            ctk.CTkCheckBox(
                grid, text=label, variable=v, width=155,
                fg_color=B_BLUE, hover_color=B_BLUE_H,
            ).grid(row=i // 5, column=i % 5, sticky="w", padx=(0, 6), pady=3)
            self.tvars[name] = v

        # ---------- 3. Action bar
        ccard = ctk.CTkFrame(self, fg_color="transparent")
        ccard.grid(row=3, column=0, sticky="ew")
        ccard.grid_columnconfigure(2, weight=1)
        self.start_btn = ctk.CTkButton(
            ccard, text="▶  Generate Subtitles", height=42, width=190,
            fg_color=B_GREEN, hover_color=B_GREEN_H,
            font=ctk.CTkFont(size=15, weight="bold"), command=self.start,
        )
        self.start_btn.grid(row=0, column=0)
        self.stop_btn = ctk.CTkButton(
            ccard, text="■  Stop", height=42, width=100,
            fg_color=B_RED, hover_color=B_RED_H, state="disabled", command=self.app.stop.set,
        )
        self.stop_btn.grid(row=0, column=1, padx=8)
        ctk.CTkFrame(ccard, fg_color="transparent", height=1).grid(row=0, column=2, sticky="ew")
        self.save_part_btn = ctk.CTkButton(
            ccard, text="💾 Save partial", width=118, height=36,
            fg_color=B_VIOLET, hover_color=B_VIOLET_H, state="disabled", command=self.save_partial,
        )
        self.save_part_btn.grid(row=0, column=3, padx=(0, 6))
        self.open_srt_btn = ctk.CTkButton(
            ccard, text="📄 Open SRT", width=105, height=36,
            fg_color=B_CYAN, hover_color=B_CYAN_H, state="disabled", command=self.open_last_srt,
        )
        self.open_srt_btn.grid(row=0, column=4, padx=(0, 6))
        ctk.CTkButton(
            ccard, text="📂 Open folder", width=115, height=36,
            fg_color=B_SLATE, hover_color=B_SLATE_H, command=self.open_output,
        ).grid(row=0, column=5)

        # ---------- Progress + colored log
        prow = ctk.CTkFrame(self, fg_color="transparent")
        prow.grid(row=4, column=0, sticky="ew", pady=(10, 4))
        prow.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(prow, text="Ready", anchor="w", font=ctk.CTkFont(weight="bold"))
        self.status.grid(row=0, column=0, sticky="w")
        self.provider_lbl = ctk.CTkLabel(prow, text="", anchor="e")
        self.provider_lbl.grid(row=0, column=1, sticky="e")
        self.pb = ctk.CTkProgressBar(prow, progress_color=B_GREEN[1], height=10)
        self.pb.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        self.pb.set(0)

        self.logbox = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family=UNICODE_FONT, size=12),
            fg_color=C_CARD, border_width=1, border_color=C_BORDER, corner_radius=10,
        )
        self.logbox.grid(row=5, column=0, sticky="nsew")
        tb = self.logbox._textbox
        tb.tag_config("head", foreground="#38bdf8")
        tb.tag_config("step", foreground="#818cf8")
        tb.tag_config("ok", foreground="#22c55e")
        tb.tag_config("warn", foreground="#f59e0b")
        tb.tag_config("err", foreground="#f43f5e")
        self.refresh_provider_label()
        self.restore_session()

    def _add_path(self, p):
        if not os.path.exists(p) or any(f["path"] == p for f in self.files):
            return False
        self.empty_lbl.grid_forget()
        row = ctk.CTkFrame(self.flist, fg_color=C_CARD, border_width=1, border_color=C_BORDER, corner_radius=8)
        row.grid(row=len(self.files) + 1, column=0, sticky="ew", pady=2, padx=2)
        row.grid_columnconfigure(0, weight=1)
        icon = "📝" if os.path.splitext(p)[1].lower() in pipeline.SUB_EXTS else "🎬"
        ctk.CTkLabel(row, text=f"{icon}  {os.path.basename(p)}", anchor="w").grid(
            row=0, column=0, sticky="w", padx=10, pady=4)
        st = ctk.CTkLabel(row, text="Ready", text_color="#38bdf8", width=130)
        st.grid(row=0, column=1)
        item = {"path": p, "status": st, "row": row}
        ctk.CTkButton(row, text="✕", width=28, fg_color="transparent", hover_color=B_RED_H,
                      command=lambda it=item: self.remove(it)).grid(row=0, column=2, padx=4)
        self.files.append(item)
        return True

    def save_session(self):
        cache.save_session(
            [f["path"] for f in self.files],
            self.src.get(),
            [n for n, v in self.tvars.items() if v.get()],
            self.dual_var.get(),
        )

    def restore_session(self):
        sess = cache.load_session()
        if not sess:
            return
        if sess.get("source_lang") in (["Auto detect"] + list(languages.LANGUAGES)):
            self.src.set(sess["source_lang"])
        if "dual_subtitles" in sess:
            self.dual_var.set(bool(sess["dual_subtitles"]))
        if isinstance(sess.get("targets"), list):
            tset = set(sess["targets"])
            for n, v in self.tvars.items():
                v.set(n in tset)
        for p in sess.get("files", []):
            self._add_path(p)

    def refresh_provider_label(self):
        s = self.app.settings
        stt_ok = bool(cfgmod.provider_cfg(s, s["stt_provider"]).get("api_key"))
        tr_ok = bool(cfgmod.provider_cfg(s, s["translate_provider"]).get("api_key"))
        stt_tag = "" if stt_ok else " (no key)"
        tr_tag = "" if tr_ok else " (no key)"
        bk = s.get("backup_translate_provider", "None")
        bk_tag = f" → {bk}" if bk and bk != "None" and cfgmod.provider_cfg(s, bk).get("api_key") else ""
        w = s.get("parallel_workers", 4)
        self.provider_lbl.configure(
            text=f"Speech: {s['stt_provider']}{stt_tag}  •  Translate: {s['translate_provider']}{tr_tag}{bk_tag}  •  {w}x",
            text_color=C_MUTED if (stt_ok and tr_ok) else "#f59e0b",
        )

    def add_files(self):
        added = False
        for p in filedialog.askopenfilenames(title="Choose videos or subtitle files", filetypes=MEDIA_TYPES):
            if self._add_path(p):
                added = True
        if added:
            self.save_session()
        if added and not self.app.busy:
            s = self.app.settings
            has_key = bool(cfgmod.provider_cfg(s, s["stt_provider"]).get("api_key")) or bool(
                cfgmod.provider_cfg(s, s["translate_provider"]).get("api_key"))
            self.status.configure(
                text="Ready — click ▶ Generate Subtitles to start" if has_key
                else "Add your API key in Settings, then click ▶ Generate Subtitles"
            )

    def remove(self, item):
        if self.app.busy:
            return
        item["row"].destroy()
        self.files.remove(item)
        if not self.files:
            self.empty_lbl.grid(row=0, column=0, pady=34)
        self.save_session()

    def clear_files(self):
        for it in list(self.files):
            self.remove(it)

    def open_output(self):
        d = self.app.settings.get("output_dir") or (os.path.dirname(self.files[0]["path"]) if self.files else "")
        if d and os.path.isdir(d):
            os.startfile(d)

    def open_last_srt(self):
        for p in reversed(self.last_written):
            if os.path.exists(p):
                os.startfile(p)
                return

    def save_partial(self):
        if not self.last_partial:
            return
        out = pipeline.export_partial(self.last_partial)
        if not out:
            return messagebox.showinfo(APP_NAME, "No completed subtitle lines to export yet.")
        self.last_written.extend(out)
        self.open_srt_btn.configure(state="normal")
        for p in out:
            self.log(f"Saved (partial): {p}")
        messagebox.showinfo(APP_NAME, "Saved partial subtitles:\n\n" + "\n".join(out))

    def log(self, msg):
        tag = None
        m = msg.strip()
        if m.startswith("━━━") or m.startswith("💾"):
            tag = "head"
        elif m.startswith("Step "):
            tag = "step"
        elif m.startswith("Saved") or m.startswith("Finished"):
            tag = "ok"
        elif m.startswith("⚠"):
            tag = "warn"
        elif m.startswith("✖"):
            tag = "err"
        self.logbox.insert("end", msg + "\n", tag)
        self.logbox.see("end")

    def set_busy(self, busy):
        self.start_btn.configure(state="disabled" if busy else "normal")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def start(self):
        s = self.app.settings
        targets = [n for n, v in self.tvars.items() if v.get()]
        if not self.files:
            return messagebox.showwarning(APP_NAME, "Add at least one video or subtitle file first.")
        if not targets:
            return messagebox.showwarning(APP_NAME, "Select at least one subtitle language.")

        has_media = any(os.path.splitext(f["path"])[1].lower() not in pipeline.SUB_EXTS for f in self.files)
        if has_media and not cfgmod.provider_cfg(s, s["stt_provider"]).get("api_key"):
            if messagebox.askyesno(APP_NAME, f"No API key set for {s['stt_provider']}.\n\nOpen Settings now?"):
                self.app.show("settings")
            return
        need_tr = any(t != "Original" for t in targets)
        if need_tr and not cfgmod.provider_cfg(s, s["translate_provider"]).get("api_key"):
            if messagebox.askyesno(APP_NAME, f"No API key set for {s['translate_provider']} (translation)."
                                             f"\n\nOpen Settings now?"):
                self.app.show("settings")
            return

        s["dual_subtitles"] = bool(self.dual_var.get())
        src = None if self.src.get() == "Auto detect" else self.src.get()
        self.save_session()
        for f in self.files:
            f["status"].configure(text="Queued", text_color=C_MUTED)
        self.app.run_job(self.files, targets, src)


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(hdr, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(
            hdr,
            text="Paste an API key below (Groq or OpenAI for speech; Groq/Gemini/OpenAI for translation), test, and save.",
            text_color=C_MUTED, anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self.scroll = scroll
        s = app.settings
        self.work = {k: dict(v) for k, v in s["providers"].items()}
        self.current = None

        # ---------- 1. AI Services
        c1 = self._card(0, "AI Services")
        ctk.CTkLabel(c1, text="Speech-to-text (detect language + transcribe):").grid(
            row=1, column=0, sticky="w", padx=14, pady=6)
        self.stt = ctk.CTkOptionMenu(c1, values=cfgmod.STT_PROVIDERS, width=230, fg_color=B_BLUE)
        self.stt.set(s["stt_provider"])
        self.stt.grid(row=1, column=1, sticky="w", pady=6)
        ctk.CTkLabel(c1, text="Translation:").grid(row=2, column=0, sticky="w", padx=14, pady=6)
        self.tr = ctk.CTkOptionMenu(c1, values=cfgmod.LLM_PROVIDERS, width=230, fg_color=B_BLUE)
        self.tr.set(s["translate_provider"])
        self.tr.grid(row=2, column=1, sticky="w", pady=6)
        ctk.CTkLabel(c1, text="Backup translation (if primary hits limit):").grid(
            row=3, column=0, sticky="w", padx=14, pady=(6, 12))
        self.backup_tr = ctk.CTkOptionMenu(c1, values=cfgmod.BACKUP_PROVIDERS, width=230, fg_color=B_VIOLET)
        self.backup_tr.set(s.get("backup_translate_provider", "None"))
        self.backup_tr.grid(row=3, column=1, sticky="w", pady=(6, 12))

        # ---------- 2. API Keys
        c2 = self._card(1, "API Keys (plugins)")
        ctk.CTkLabel(c2, text="Provider:").grid(row=1, column=0, sticky="w", padx=14, pady=6)
        self.pick = ctk.CTkSegmentedButton(
            c2, values=list(cfgmod.PROVIDERS), selected_color=B_INDIGO[1], selected_hover_color=B_INDIGO_H[1],
            command=self.select_provider,
        )
        self.pick.grid(row=1, column=1, columnspan=2, sticky="w", pady=6, padx=(0, 14))

        self.key_var = ctk.StringVar()
        self.url_var = ctk.StringVar()
        self.stt_var = ctk.StringVar()
        self.llm_var = ctk.StringVar()
        ctk.CTkLabel(c2, text="API key:").grid(row=2, column=0, sticky="w", padx=14, pady=6)
        self.key_entry = ctk.CTkEntry(c2, textvariable=self.key_var, show="•", width=340,
                                      placeholder_text="paste your API key here")
        self.key_entry.grid(row=2, column=1, sticky="w", pady=6)
        kb = ctk.CTkFrame(c2, fg_color="transparent")
        kb.grid(row=2, column=2, sticky="w", padx=6)
        self.show_btn = ctk.CTkButton(kb, text="👁", width=34, fg_color=B_SLATE, command=self.toggle_show)
        self.show_btn.pack(side="left")
        self.getkey_btn = ctk.CTkButton(kb, text="Get key ↗", width=85, fg_color=B_INDIGO, hover_color=B_INDIGO_H,
                                        command=self.open_key_page)
        self.getkey_btn.pack(side="left", padx=6)
        self.key_badge = ctk.CTkLabel(kb, text="", width=90, anchor="w")
        self.key_badge.pack(side="left", padx=4)

        ctk.CTkLabel(c2, text="Base URL:").grid(row=3, column=0, sticky="w", padx=14, pady=6)
        ctk.CTkEntry(c2, textvariable=self.url_var, width=340).grid(row=3, column=1, sticky="w", pady=6)

        ctk.CTkLabel(c2, text="Speech model:").grid(row=4, column=0, sticky="w", padx=14, pady=6)
        self.stt_combo = ctk.CTkComboBox(c2, variable=self.stt_var, values=[], width=290)
        self.stt_combo.grid(row=4, column=1, sticky="w", pady=6)

        ctk.CTkLabel(c2, text="Translation model:").grid(row=5, column=0, sticky="w", padx=14, pady=6)
        self.llm_combo = ctk.CTkComboBox(c2, variable=self.llm_var, values=[], width=290)
        self.llm_combo.grid(row=5, column=1, sticky="w", pady=6)

        tb = ctk.CTkFrame(c2, fg_color="transparent")
        tb.grid(row=6, column=1, columnspan=2, sticky="w", pady=(6, 12))
        self.test_btn = ctk.CTkButton(tb, text="Test connection", width=135, fg_color=B_CYAN, hover_color=B_CYAN_H,
                                      command=self.test)
        self.test_btn.pack(side="left")
        self.models_btn = ctk.CTkButton(tb, text="↻ Load models", width=125, fg_color=B_VIOLET,
                                        hover_color=B_VIOLET_H, command=self.load_models)
        self.models_btn.pack(side="left", padx=(8, 0))
        self.test_lbl = ctk.CTkLabel(tb, text="", wraplength=330, justify="left")
        self.test_lbl.pack(side="left", padx=10)

        # ---------- 3. Output & Performance
        c3 = self._card(2, "Output & Speed")
        ctk.CTkLabel(c3, text="Save subtitles to:").grid(row=1, column=0, sticky="w", padx=14, pady=6)
        self.out_var = ctk.StringVar(value=s.get("output_dir", ""))
        ctk.CTkEntry(c3, textvariable=self.out_var, width=340,
                     placeholder_text="(same folder as the video)").grid(row=1, column=1, sticky="w")
        ctk.CTkButton(c3, text="Browse", width=80, fg_color=B_SLATE, command=self.browse).grid(
            row=1, column=2, padx=6, sticky="w")
        ctk.CTkLabel(c3, text="Format:").grid(row=2, column=0, sticky="w", padx=14, pady=6)
        self.fmt = ctk.CTkSegmentedButton(c3, values=["srt", "vtt"], selected_color=B_BLUE[1])
        self.fmt.set(s.get("subtitle_format", "srt"))
        self.fmt.grid(row=2, column=1, sticky="w")
        ctk.CTkLabel(c3, text="Max characters per line:").grid(row=3, column=0, sticky="w", padx=14, pady=6)
        self.maxc = ctk.CTkOptionMenu(c3, values=["0 (no wrap)", "32", "37", "42", "50"], width=130)
        self.maxc.set(str(s.get("max_line_chars", 42)))
        self.maxc.grid(row=3, column=1, sticky="w")
        ctk.CTkLabel(c3, text="Upload chunk size (minutes):").grid(row=4, column=0, sticky="w", padx=14, pady=6)
        self.chunk = ctk.CTkOptionMenu(c3, values=["5", "10", "15", "20"], width=130)
        self.chunk.set(str(s.get("chunk_minutes", 10)))
        self.chunk.grid(row=4, column=1, sticky="w")
        ctk.CTkLabel(c3, text="Parallel speed (workers):").grid(row=5, column=0, sticky="w", padx=14, pady=6)
        self.workers = ctk.CTkSegmentedButton(c3, values=["1", "2", "4", "6"], selected_color=B_GREEN[1])
        self.workers.set(str(s.get("parallel_workers", 4)))
        self.workers.grid(row=5, column=1, sticky="w")
        ctk.CTkLabel(c3, text="Transcript cache:").grid(row=6, column=0, sticky="w", padx=14, pady=6)
        cf = ctk.CTkFrame(c3, fg_color="transparent")
        cf.grid(row=6, column=1, columnspan=2, sticky="w", pady=6)
        self.cache_var = ctk.BooleanVar(value=bool(s.get("use_cache", True)))
        ctk.CTkCheckBox(cf, text="Reuse cached transcripts on retry / extra languages",
                        variable=self.cache_var).pack(side="left")
        ctk.CTkButton(cf, text="Clear cache", width=95, fg_color=B_SLATE, command=self.clear_cache).pack(
            side="left", padx=10)
        ctk.CTkLabel(c3, text="Translation style:").grid(row=7, column=0, sticky="w", padx=14, pady=(6, 12))
        self.style = ctk.CTkSegmentedButton(
            c3, values=["Conversational (Movie)", "Formal / Standard"], selected_color=B_BLUE[1]
        )
        self.style.set(s.get("translation_style", "Conversational (Movie)"))
        self.style.grid(row=7, column=1, columnspan=2, sticky="w", pady=(6, 12))

        # ---------- 4. Security & Appearance
        c4 = self._card(3, "Security & Appearance")
        ctk.CTkLabel(c4, text="Key storage:").grid(row=1, column=0, sticky="w", padx=14, pady=6)
        sec_f = ctk.CTkFrame(c4, fg_color="transparent")
        sec_f.grid(row=1, column=1, columnspan=2, sticky="w", pady=6)
        ctk.CTkLabel(sec_f, text="🔒 Protected with Windows DPAPI encryption • HTTPS required for cloud APIs",
                     text_color="#22c55e").pack(side="left")
        ctk.CTkButton(sec_f, text="🗑 Clear all keys", width=120, fg_color=B_RED, hover_color=B_RED_H,
                      command=self.wipe_keys).pack(side="left", padx=12)

        ctk.CTkLabel(c4, text="Theme:").grid(row=2, column=0, sticky="w", padx=14, pady=(6, 12))
        self.theme = ctk.CTkSegmentedButton(c4, values=["Dark", "Light", "System"],
                                            command=ctk.set_appearance_mode)
        self.theme.set(s.get("appearance", "Dark"))
        self.theme.grid(row=2, column=1, sticky="w", pady=(6, 12))

        ctk.CTkLabel(scroll, text=f"Settings file: {cfgmod.CONFIG_PATH}", text_color=C_MUTED
                     ).grid(row=4, column=0, sticky="w", pady=(4, 8))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="e", pady=(10, 0))
        self.saved_lbl = ctk.CTkLabel(bar, text="", text_color="#22c55e", font=ctk.CTkFont(weight="bold"))
        self.saved_lbl.pack(side="left", padx=10)
        ctk.CTkButton(bar, text="💾  Save settings", height=38, width=155,
                      fg_color=B_GREEN, hover_color=B_GREEN_H,
                      font=ctk.CTkFont(size=14, weight="bold"), command=self.save).pack(side="left")
        ctk.CTkButton(bar, text="Save & Go to Generate →", height=38, width=195,
                      fg_color=B_BLUE, hover_color=B_BLUE_H,
                      command=lambda: (self.save(), self.app.show("generate"))).pack(side="left", padx=(8, 0))

        self.pick.set(s["stt_provider"])
        self.select_provider(s["stt_provider"])

    def _card(self, row, title):
        c = ctk.CTkFrame(self.scroll, fg_color=C_CARD, border_width=1, border_color=C_BORDER, corner_radius=12)
        c.grid(row=row, column=0, sticky="ew", pady=6)
        ctk.CTkLabel(c, text=title, font=ctk.CTkFont(size=15, weight="bold")
                     ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(10, 2))
        return c

    def _store_current(self):
        if self.current:
            stt_val = self.stt_var.get().strip()
            if not cfgmod.PROVIDERS[self.current]["stt"]:
                stt_val = ""
            self.work[self.current].update(
                api_key=self.key_var.get().strip(),
                base_url=self.url_var.get().strip(),
                stt_model=stt_val,
                llm_model=self.llm_var.get().strip(),
            )

    def select_provider(self, name):
        self._store_current()
        self.current = name
        p = self.work[name]
        self.key_var.set(p.get("api_key", ""))
        self.url_var.set(p.get("base_url", ""))
        self.stt_var.set(p.get("stt_model", ""))
        self.llm_var.set(p.get("llm_model", ""))
        supports = cfgmod.PROVIDERS[name]["stt"]
        self.stt_combo.configure(state="normal" if supports else "disabled",
                                 values=[p.get("stt_model")] if p.get("stt_model") else [])
        self.llm_combo.configure(values=[p.get("llm_model")] if p.get("llm_model") else [])
        if not supports:
            self.stt_var.set("(translation only)")
        self.getkey_btn.configure(state="normal" if cfgmod.PROVIDERS[name]["key_url"] else "disabled")
        self.key_badge.configure(
            text="● Key saved" if p.get("api_key") else "○ No key",
            text_color="#22c55e" if p.get("api_key") else C_MUTED,
        )
        self.test_lbl.configure(text="")

    def toggle_show(self):
        self.key_entry.configure(show="" if self.key_entry.cget("show") else "•")

    def open_key_page(self):
        url = cfgmod.PROVIDERS[self.current]["key_url"]
        if url:
            webbrowser.open(url)

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.out_var.set(d)

    def test(self):
        self._store_current()
        cfg = dict(self.work[self.current])
        self.test_btn.configure(state="disabled")
        self.test_lbl.configure(text="Testing…", text_color=C_MUTED)

        def run():
            try:
                msg, color = api.test_connection(cfg), "#22c55e"
            except Exception as e:
                msg, color = f"✖ {security.redact(str(e), [cfg.get('api_key')])}", "#ef4444"
            self.after(0, lambda: (self.test_lbl.configure(text=msg, text_color=color),
                                   self.test_btn.configure(state="normal")))
        threading.Thread(target=run, daemon=True).start()

    def load_models(self):
        self._store_current()
        cfg = dict(self.work[self.current])
        prov = self.current
        self.models_btn.configure(state="disabled")
        self.test_lbl.configure(text="Fetching models…", text_color=C_MUTED)

        def run():
            try:
                stt_m, llm_m = api.list_models(cfg)

                def apply():
                    if self.current == prov:
                        if cfgmod.PROVIDERS[prov]["stt"] and stt_m:
                            self.stt_combo.configure(values=stt_m)
                            if self.stt_var.get() not in stt_m:
                                self.stt_var.set(stt_m[0])
                        if llm_m:
                            self.llm_combo.configure(values=llm_m)
                            if self.llm_var.get() not in llm_m:
                                self.llm_var.set(api.pick_best_llm(llm_m))
                        self.test_lbl.configure(text=f"Loaded {len(llm_m)} translation + {len(stt_m)} speech models ✔",
                                                text_color="#22c55e")
                    self.models_btn.configure(state="normal")
                self.after(0, apply)
            except Exception as e:
                err = security.redact(str(e), [cfg.get("api_key")])
                self.after(0, lambda: (self.test_lbl.configure(text=f"✖ {err}", text_color="#ef4444"),
                                       self.models_btn.configure(state="normal")))
        threading.Thread(target=run, daemon=True).start()

    def clear_cache(self):
        n, b = cache.clear_all()
        messagebox.showinfo(APP_NAME, f"Cleared {n} cached file(s) ({b / (1024 * 1024):.1f} MB).")

    def wipe_keys(self):
        if not messagebox.askyesno(APP_NAME, "Remove all saved API keys from this PC?"):
            return
        for p in self.work.values():
            p["api_key"] = ""
        self.key_var.set("")
        self.save()
        self.key_badge.configure(text="○ No key", text_color=C_MUTED)
        messagebox.showinfo(APP_NAME, "All saved API keys have been cleared.")

    def save(self):
        self._store_current()
        for name, p in self.work.items():
            if not cfgmod.PROVIDERS[name]["stt"]:
                p["stt_model"] = ""
            if p.get("base_url"):
                try:
                    security.validate_url(p["base_url"])
                except ValueError as e:
                    messagebox.showwarning(APP_NAME, f"{name}: {e}")
                    return
        if not self.work.get(self.stt.get(), {}).get("api_key"):
            for name in cfgmod.STT_PROVIDERS:
                if self.work.get(name, {}).get("api_key"):
                    self.stt.set(name)
                    break
        if not self.work.get(self.tr.get(), {}).get("api_key"):
            for name in cfgmod.LLM_PROVIDERS:
                if self.work.get(name, {}).get("api_key"):
                    self.tr.set(name)
                    break

        s = self.app.settings
        s["providers"] = self.work
        s["stt_provider"] = self.stt.get()
        s["translate_provider"] = self.tr.get()
        s["backup_translate_provider"] = self.backup_tr.get()
        s["output_dir"] = self.out_var.get().strip()
        s["subtitle_format"] = self.fmt.get()
        s["max_line_chars"] = int(self.maxc.get().split()[0])
        s["chunk_minutes"] = int(self.chunk.get())
        s["parallel_workers"] = int(self.workers.get())
        s["use_cache"] = bool(self.cache_var.get())
        s["translation_style"] = self.style.get()
        s["appearance"] = self.theme.get()
        gen = self.app.pages["generate"]
        s["dual_subtitles"] = bool(gen.dual_var.get())
        s["default_targets"] = [n for n, v in gen.tvars.items() if v.get()]
        cfgmod.save(s)
        self.work = {k: dict(v) for k, v in s["providers"].items()}
        self.key_badge.configure(
            text="● Key saved" if self.work[self.current].get("api_key") else "○ No key",
            text_color="#22c55e" if self.work[self.current].get("api_key") else C_MUTED,
        )
        gen.refresh_provider_label()
        self.saved_lbl.configure(text="Saved & Encrypted ✔")
        self.after(2500, lambda: self.saved_lbl.configure(text=""))


class AboutPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        card = ctk.CTkFrame(self, fg_color=C_CARD, border_width=1, border_color=C_BORDER, corner_radius=12)
        card.pack(fill="both", expand=True)
        ctk.CTkLabel(card, text=f"{APP_NAME}  v{APP_VERSION}", font=ctk.CTkFont(size=26, weight="bold")
                     ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(card, text="Fast parallel AI subtitle generator & translator for Windows",
                     text_color=C_MUTED).pack(anchor="w", padx=20)
        text = (
            "\nFeatures:\n"
            "  • Any video duration (30 min, 1 hr, 2 hr, 3 hr+) — splits audio locally and stitches timings.\n"
            "  • Parallel upload & parallel batch translation for fast output.\n"
            "  • Also translates existing .srt / .vtt files directly (no speech-to-text cost).\n"
            "  • Optional Dual Subtitles (Translated + Original together in one file).\n"
            "  • Resume cache: interrupted jobs continue from completed parts instead of starting over.\n"
            "  • Security: API keys are encrypted on disk with Windows DPAPI and require HTTPS.\n\n"
            "Recommended setup in Settings:\n"
            "  • Groq (free tier available): fast Whisper speech-to-text + Qwen translation.\n"
            "  • Google Gemini: strong Sinhala & Tamil translation.\n"
            "  • OpenAI (paid): whisper-1 + gpt-4o-mini with a single key."
        )
        ctk.CTkLabel(card, text=text, justify="left", anchor="w",
                     font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=12)


# ======================================================================= App
class App(ctk.CTk):
    def __init__(self):
        self.settings = cfgmod.load()
        ctk.set_appearance_mode(self.settings.get("appearance", "Dark"))
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.configure(fg_color=C_BG)
        self.title(f"{APP_NAME} – AI Subtitle Generator")
        self.geometry("1120x780")
        self.minsize(960, 640)
        try:
            self.iconbitmap(resource_path(os.path.join("assets", "icon.ico")))
        except Exception:
            pass

        self.q = queue.Queue()
        self.stop = threading.Event()
        self.busy = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=C_SIDE)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_rowconfigure(5, weight=1)
        ctk.CTkLabel(side, text="🎞 " + APP_NAME, font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=("#1e3a8a", "#60a5fa")).grid(row=0, column=0, padx=20, pady=(24, 2))
        ctk.CTkLabel(side, text="AI Subtitle Generator", text_color=C_MUTED).grid(row=1, column=0, pady=(0, 24))
        self.nav = {}
        for i, (key, label) in enumerate([("generate", "🎬  Generate"), ("settings", "⚙  Settings"),
                                          ("about", "ℹ  About")]):
            b = ctk.CTkButton(side, text=label, anchor="w", height=42, width=176, corner_radius=10,
                              fg_color="transparent", text_color=("gray15", "gray90"),
                              hover_color=("gray80", "#1e293b"), command=lambda k=key: self.show(k))
            b.grid(row=2 + i, column=0, padx=16, pady=4)
            self.nav[key] = b
        ctk.CTkLabel(side, text=f"v{APP_VERSION} • 🔒 DPAPI", text_color=C_MUTED).grid(row=6, column=0, pady=14)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=1, sticky="nsew", padx=22, pady=18)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.pages = {
            "generate": GeneratePage(body, self),
            "settings": SettingsPage(body, self),
            "about": AboutPage(body, self),
        }

        first_run = not any(p.get("api_key") for p in self.settings["providers"].values())
        self.show("settings" if first_run else "generate")
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def show(self, key):
        for k, p in self.pages.items():
            if k == key:
                p.grid(row=0, column=0, sticky="nsew")
            else:
                p.grid_remove()
        for k, b in self.nav.items():
            b.configure(fg_color=B_BLUE if k == key else "transparent",
                        text_color="white" if k == key else ("gray15", "gray90"))

    def run_job(self, files, targets, src):
        self.busy = True
        self.stop.clear()
        page = self.pages["generate"]
        page.set_busy(True)
        page.last_written.clear()
        page.last_partial = None
        page.open_srt_btn.configure(state="disabled")
        page.save_part_btn.configure(state="disabled")
        settings = dict(self.settings)

        def worker():
            ok = 0
            all_written = []
            last_partial = None
            for n, item in enumerate(files, 1):
                if self.stop.is_set():
                    break
                name = os.path.basename(item["path"])
                self.q.put(("file", item, "Working…", "#f59e0b"))
                self.q.put(("log", f"\n━━━ [{n}/{len(files)}] {name} ━━━"))
                t0 = time.time()
                pstate = {}

                def prog(stage, frac, n=n):
                    self.q.put(("progress", f"[{n}/{len(files)}] {stage}…", frac))

                def has_partial_progress(st):
                    if st.get("segments"):
                        return True
                    return any(x is not None for x in (st.get("stt_results") or []))

                try:
                    out = pipeline.process_file(item["path"], settings, targets, src,
                                                lambda m: self.q.put(("log", m)), prog, self.stop,
                                                partial_state=pstate)
                    all_written.extend(out)
                    self.q.put(("file", item, f"Done ✔ ({len(out)})", "#22c55e"))
                    self.q.put(("log", f"Finished in {time.time() - t0:.1f} s"))
                    ok += 1
                except InterruptedError:
                    if has_partial_progress(pstate):
                        last_partial = pstate
                        self.q.put(("file", item, "Paused (saved)", "#f59e0b"))
                        self.q.put(("log", "💾 Stopped — completed parts/batches are saved. Click ▶ Generate Subtitles to resume, or 💾 Save partial."))
                    else:
                        self.q.put(("file", item, "Stopped", C_MUTED))
                        self.q.put(("log", "Stopped by user."))
                    break
                except Exception as e:
                    if has_partial_progress(pstate):
                        last_partial = pstate
                        self.q.put(("file", item, "Paused (saved)", "#f59e0b"))
                        self.q.put(("log", f"✖ Error: {e}"))
                        self.q.put(("log", "💾 Checkpoint saved! Click ▶ Generate Subtitles to resume from this break point (or click 💾 Save partial)."))
                    else:
                        self.q.put(("file", item, "Failed ✖", "#f43f5e"))
                        self.q.put(("log", f"✖ Error: {e}"))
            self.q.put(("done", ok, len(files), all_written, last_partial))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        page = self.pages["generate"]
        latest_progress = None
        try:
            for _ in range(100):
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    page.log(msg[1])
                elif kind == "progress":
                    latest_progress = (msg[1], msg[2])
                elif kind == "file":
                    msg[1]["status"].configure(text=msg[2], text_color=msg[3])
                elif kind == "done":
                    self.busy = False
                    page.set_busy(False)
                    page.last_written = msg[3]
                    page.last_partial = msg[4]
                    if msg[3]:
                        page.open_srt_btn.configure(state="normal")
                    if msg[4]:
                        page.save_part_btn.configure(state="normal")
                    page.status.configure(text=f"Finished: {msg[1]}/{msg[2]} file(s) completed")
                    page.pb.set(1 if msg[1] else 0)
        except queue.Empty:
            pass
        if latest_progress is not None:
            page.status.configure(text=latest_progress[0])
            page.pb.set(max(0.0, min(1.0, latest_progress[1])))
        self.after(100, self._poll)

    def on_close(self):
        if self.busy and not messagebox.askyesno(APP_NAME, "A job is running. Quit anyway?"):
            return
        self.pages["generate"].save_session()
        self.stop.set()
        self.destroy()


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LocalSub.App")
        except Exception:
            pass
    App().mainloop()
