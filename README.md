# LocalSub – AI Subtitle Generator & Translator (Windows)

Add any video, audio, or `.srt` / `.vtt` file → LocalSub **auto-detects the spoken language**, transcribes in parallel, and generates natural subtitles in **Sinhala, English, Tamil, Hindi, and 15+ more languages** using **your own API keys** (Groq, Google Gemini, OpenAI, OpenRouter, DeepSeek, or custom OpenAI-compatible server).

## Download / Install (Windows 10 / 11 – no Python or extra software needed)
- **Windows Installer (recommended):** [Download `LocalSub-Setup.exe`](https://github.com/Pasinduranasinghe2001/LocalSub/releases/latest/download/LocalSub-Setup.exe) (Start Menu + optional Desktop shortcut + Uninstaller)
- **Portable `.exe` (no install):** [Download `LocalSub.exe`](https://github.com/Pasinduranasinghe2001/LocalSub/releases/latest/download/LocalSub.exe)
- **All releases:** [Releases page](https://github.com/Pasinduranasinghe2001/LocalSub/releases)

## Key Features
- **Any video duration (30 min, 1 hr, 2 hr, 3 hr+):** extracts audio locally via bundled FFmpeg (`PyAV`) into small MP3 chunks and stitches timestamps continuously.
- **Fast parallel execution:** transcribes audio parts and translates subtitle batches concurrently (`1x / 2x / 4x / 6x` workers).
- **Backup translation provider:** if your primary translator (e.g. Google Gemini) hits a daily limit mid-movie, automatically continues remaining batches with your backup provider (e.g. Groq or OpenRouter).
- **Natural Conversational Sinhala (Movie) mode:** produces everyday spoken Sinhala subtitles instead of stiff literary wording (or switch to *Formal / Standard* in Settings).
- **Direct `.srt` / `.vtt` translation:** drop an existing subtitle file to translate with zero speech-to-text cost.
- **Dual (bilingual) subtitles:** optional combined `Translated + Original` output (e.g. `movie.en+si.srt`).
- **Resume cache:** completed parts are cached locally so interrupted jobs continue where they stopped.
- **Security:** API keys are encrypted locally on Windows using **DPAPI** (`CryptProtectData`), remote endpoints enforce **HTTPS**, and secrets are redacted from logs.

## Quick Start
1. Open **LocalSub** → **Settings**.
2. Paste an API key (e.g. **Groq** for fast speech-to-text, **Google Gemini** for Sinhala/Tamil translation, or **OpenAI** for both).
3. Click **Test connection** (and **↻ Load models** if needed) → **Save & Go to Generate →**.
4. Click **+ Add videos / SRT**, choose your movie or subtitle file, tick target languages, and click **▶ Generate Subtitles**.

## Supported Providers
| Provider | Speech-to-text | Translation | Notes |
|---|---|---|---|
| **Groq** | ✅ | ✅ | Fast Whisper (`whisper-large-v3`); free tier has 2 hr/hr audio & 1,000 OTPM limits |
| **Google Gemini** | – | ✅ | Great Sinhala & Tamil quality; high free-tier TPM |
| **OpenAI** | ✅ | ✅ | Paid (`whisper-1` + `gpt-4o-mini`), one key for everything |
| **OpenRouter / DeepSeek / Custom URL** | Custom only | ✅ | OpenAI-compatible REST endpoints |

## Run from Source & Build `.exe`
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python LocalSub.py
```
Build portable `dist\LocalSub.exe` and `installer\LocalSub-Setup.exe` (requires [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer):
```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```
